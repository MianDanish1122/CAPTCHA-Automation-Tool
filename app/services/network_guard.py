"""
Egress guard for every Playwright browsing context used by the crawler and batch scanner.

Why this exists
---------------
Validating a URL once, before `page.goto`, is not enough:
  * HTTP redirects can lead to private / metadata addresses,
  * subresources (img/script/fetch/XHR/iframes) are requested by the page itself,
  * DNS can change between our check and Chromium's own lookup (DNS rebinding / TOCTOU).

How it works
------------
`NetworkGuard.install()` routes *every* request made inside a browser context through
`_handle()`, which for each request (navigation, redirect hop, or subresource):

  1. rejects non-HTTP(S) schemes,
  2. validates the URL with `SecurityGuard.validate_target_url` (scheme, port, credentials,
     domain allow-list, IP policy) and every redirect hop with `validate_redirect_url`,
  3. resolves the hostname *once* and validates ALL resulting addresses,
  4. performs the HTTP request itself with httpx, connecting **directly to the validated IP**
     (TLS SNI + certificate verification still use the original hostname), and hands the
     response to Chromium with `route.fulfill()`.

Because Chromium never performs its own DNS lookup or opens its own socket for guarded
traffic, there is no second resolution an attacker could re-point (DNS-rebinding safe).
Redirects are followed by the guard itself, hop by hop, with full validation and pinning
(Chromium follows a fulfilled 3xx internally without routing the next hop, so redirect
responses are never handed to it). TLS certificate validation is ON unless the explicit
development-only `SCAN_ALLOW_INVALID_CERTS` flag is set. Service workers and WebSockets
are blocked because they would bypass request routing.
"""
import asyncio
import logging
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings
from app.services.security_guard import SecurityGuard
from app.services.provider_hosts import is_provider_resource

logger = logging.getLogger(__name__)

_DROP_REQUEST_HEADERS = {
    "host", "content-length", "accept-encoding", "connection", "transfer-encoding",
    "proxy-authorization", "proxy-connection", "keep-alive", "upgrade", "te",
}
MAX_REDIRECT_HOPS = 10
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_DROP_RESPONSE_HEADERS = {
    "content-encoding", "content-length", "transfer-encoding", "connection", "keep-alive",
}


class NetworkGuard:
    def __init__(
        self,
        *,
        allow_loopback: bool = False,
        block_all_network: bool = False,
        label: str = "scan",
        provider_resources: bool = False,
        read_only: bool = False,
    ):
        self.allow_loopback = bool(allow_loopback and settings.can_allow_loopback)
        self.block_all_network = block_all_network
        # Narrow policy: allow GET/HEAD to the CAPTCHA providers' widget hosts (provider_hosts.py)
        self.provider_resources = provider_resources
        # No-transmission policy: abort every request whose method is not GET/HEAD
        self.read_only = read_only
        # Lockdown: once set, EVERY request (any method, any host) is aborted. Used while filling forms.
        self.locked = False
        self.provider_requests: list[str] = []
        self.label = label
        self.blocked: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.allowed_count = 0
        # original request URL -> final URL after (validated) redirects
        self.final_urls: dict[str, str] = {}
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ lifecycle
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=not settings.SCAN_ALLOW_INVALID_CERTS,
                follow_redirects=False,
                trust_env=False,  # never inherit proxy env vars: connections must be direct and pinned
                timeout=httpx.Timeout(settings.REQUEST_TIMEOUT_MS / 1000.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None

    async def install(self, context) -> None:
        await context.route("**/*", self._handle)
        # WebSockets bypass route(); refuse them outright.
        try:
            await context.route_web_socket("**/*", lambda ws: asyncio.ensure_future(ws.close()))
        except Exception:  # older Playwright without route_web_socket
            logger.debug("route_web_socket unavailable; relying on CSP-less fallback")

    # ------------------------------------------------------------------ helpers
    def lock(self) -> None:
        """Cut the network: from now on every request is aborted (no-transmission mode)."""
        self.locked = True

    def unlock(self) -> None:
        self.locked = False

    def _block(self, url: str, reason: str) -> None:
        logger.warning("NetworkGuard[%s] blocked %s: %s", self.label, url[:200], reason)
        self.blocked.append({"url": url[:500], "reason": reason})

    async def _validate(
        self, url: str, redirected_from: Optional[str], method: str = "GET"
    ) -> tuple[list[str], str]:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return [], f"Non-HTTP(S) scheme '{parsed.scheme}' is prohibited."

        provider_ok = self.provider_resources and is_provider_resource(url, method)
        allowed, reason = await asyncio.to_thread(
            SecurityGuard.validate_target_url,
            url,
            False,
            self.allow_loopback,
            provider_ok,  # skip_domain_allowlist: ONLY for exact provider widget resources
        )
        if not allowed:
            return [], reason

        if redirected_from:
            # provider -> provider hops (e.g. recaptcha.net -> google.com) are permitted; all other hops
            # must stay on the same site (apex/www counts as the same site).
            prev_provider = self.provider_resources and is_provider_resource(redirected_from, "GET")
            if not (provider_ok and prev_provider):
                ok, why = await asyncio.to_thread(
                    SecurityGuard.validate_redirect_url,
                    url,
                    redirected_from,
                    False,
                    self.allow_loopback,
                    True,
                )
                if not ok:
                    return [], why
        if provider_ok:
            self.provider_requests.append(url[:300])

        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        ips, why = await asyncio.to_thread(
            SecurityGuard.resolve_public_addresses,
            parsed.hostname or "",
            port,
            self.allow_loopback,
        )
        if not ips:
            return [], why
        return ips, "ok"

    async def _pinned_fetch_once(
        self,
        url: str,
        method: str,
        headers_in: dict[str, str],
        body: Optional[bytes],
        ips: list[str],
    ) -> tuple[int, dict[str, str], bytes]:
        """Single HTTP exchange, connecting directly to a pre-validated IP (no redirects followed)."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or ""
        port = parsed.port or (443 if scheme == "https" else 80)

        headers = {k: v for k, v in headers_in.items() if k.lower() not in _DROP_REQUEST_HEADERS}
        headers["Host"] = host if parsed.port is None else f"{host}:{port}"
        headers["Accept-Encoding"] = "gzip, deflate"

        last_error: Optional[Exception] = None
        for ip in ips:
            ip_host = f"[{ip}]" if ":" in ip else ip
            target = f"{scheme}://{ip_host}:{port}{parsed.path or '/'}"
            if parsed.query:
                target += f"?{parsed.query}"
            extensions = {"sni_hostname": host} if scheme == "https" else {}
            try:
                async with self._get_client().stream(
                    method, target, headers=headers, content=body, extensions=extensions,
                ) as resp:
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > settings.GUARD_MAX_RESPONSE_BYTES:
                            raise ValueError("Response exceeds maximum permitted size.")
                        chunks.append(chunk)
                    out_headers: dict[str, str] = {}
                    for key, value in resp.headers.multi_items():
                        lk = key.lower()
                        if lk in _DROP_RESPONSE_HEADERS:
                            continue
                        if lk in out_headers:
                            sep = "\n" if lk == "set-cookie" else ", "
                            out_headers[lk] = out_headers[lk] + sep + value
                        else:
                            out_headers[lk] = value
                    return resp.status_code, out_headers, b"".join(chunks)
            except Exception as exc:  # try next validated address
                last_error = exc
        raise last_error or RuntimeError("No validated address could be reached.")

    async def _fetch_with_redirects(self, request) -> tuple[Optional[tuple[int, dict[str, str], bytes]], str, str]:
        """
        Fetch `request.url`, following redirects MANUALLY so that every hop is validated
        (SSRF policy, same-domain rule) and DNS-pinned before any socket is opened.

        Redirect responses are never handed to Chromium: Chromium follows a fulfilled 3xx
        internally WITHOUT routing the next hop, which would bypass this guard entirely.

        Returns (response_or_None, final_url, block_reason). `response` is None when blocked.
        """
        url = request.url
        method = request.method
        body = request.post_data_buffer
        headers_in = await request.all_headers()
        previous: Optional[str] = None

        for _hop in range(MAX_REDIRECT_HOPS + 1):
            ips, reason = await self._validate(url, previous, method)
            if not ips:
                return None, url, reason

            status, headers, payload = await self._pinned_fetch_once(url, method, headers_in, body, ips)
            location = headers.get("location")
            if status in _REDIRECT_STATUSES and location:
                previous = url
                url = urljoin(url, location)
                if status in (301, 302, 303) and method.upper() not in ("GET", "HEAD"):
                    method, body = "GET", None
                headers_in = {k: v for k, v in headers_in.items() if k.lower() not in ("content-type",)}
                continue
            return (status, headers, payload), url, "ok"

        return None, url, f"Too many redirects (>{MAX_REDIRECT_HOPS})."

    # ------------------------------------------------------------------ route handler
    async def _handle(self, route) -> None:
        request = route.request
        url = request.url
        try:
            if self.block_all_network:
                self._block(url, "Network access is disabled for this inspection mode.")
                await route.abort("blockedbyclient")
                return

            if self.locked:
                self._block(url, "Network locked (no-transmission mode): all requests are aborted.")
                await route.abort("blockedbyclient")
                return
            if self.read_only and request.method.upper() not in ("GET", "HEAD"):
                self._block(url, f"{request.method} blocked: read-only inspection never transmits data.")
                await route.abort("blockedbyclient")
                return

            response, final_url, reason = await self._fetch_with_redirects(request)
            if response is None:
                self._block(final_url, reason)
                await route.abort("blockedbyclient")
                return

            status, headers, body = response
            self.allowed_count += 1
            if final_url != url:
                self.final_urls[url] = final_url
            await route.fulfill(status=status, headers=headers, body=body)
        except Exception as exc:
            self.errors.append({"url": url[:500], "error": str(exc)[:300]})
            logger.warning("NetworkGuard[%s] fetch failed for %s: %s", self.label, url[:200], exc)
            try:
                await route.abort("failed")
            except Exception:
                pass

    def effective_url(self, url: str) -> str:
        """Final URL a (possibly redirected) navigation was actually served from."""
        return self.final_urls.get(url, url)

    def summary(self) -> dict[str, Any]:
        return {
            "allowed_requests": self.allowed_count,
            "blocked_requests": list(self.blocked),
            "provider_requests": list(self.provider_requests),
            "errors": list(self.errors),
        }


async def new_guarded_context(browser, guard: NetworkGuard, **context_kwargs):
    """
    Create a browser context whose entire network egress goes through `guard`.
    Certificate errors are NOT ignored (ignore_https_errors is never set here) and
    service workers are blocked so they cannot bypass routing.
    """
    context_kwargs.pop("ignore_https_errors", None)
    context = await browser.new_context(service_workers="block", **context_kwargs)
    await guard.install(context)
    return context
