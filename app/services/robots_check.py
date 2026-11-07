"""
robots.txt / access-restriction check used by the batch workflow.

Policy (the operator's rule: respect robots.txt and access controls, never work around them):
  200 + rules           -> parse; the target path must be allowed for our user agent
  404 / 410             -> no robots file: no stated restriction, proceed
  401 / 403 / 429       -> the site restricts automated access (e.g. a Cloudflare challenge): STOP and report
  5xx / network error   -> cannot tell: STOP (conservative, RFC 9309 treats server errors as "disallow")
The fetch goes through the guarded browser context, so SSRF/DNS/TLS rules apply to it as well.
"""
import re
import urllib.robotparser
from typing import Any, Optional
from urllib.parse import urlparse

# Browser-compatibility product tokens that identify nobody; the token that names US is what robots.txt files target.
_GENERIC_TOKENS = {"mozilla", "applewebkit", "chrome", "safari", "gecko", "firefox", "edg", "version", "mobile"}


def robots_agents(user_agent: str) -> list[str]:
    """
    Names to test against robots.txt: our own product token(s) first (e.g. 'TechnologyBrainz-Crawler' from
    'Mozilla/5.0 ... Chrome/128 ... TechnologyBrainz-Crawler/2.0'), then the full string.
    urllib's parser matches only the text before the first '/', so a Chrome-prefixed string is seen as
    'Mozilla' and rules written for our crawler would otherwise be silently ignored.
    """
    tokens = [t for t in re.findall(r"([A-Za-z][A-Za-z0-9_.-]*)/[0-9][\w.]*", user_agent or "")
              if t.lower() not in _GENERIC_TOKENS]
    return list(dict.fromkeys(tokens + [user_agent or "*"]))


def can_fetch_all(rp: urllib.robotparser.RobotFileParser, user_agent: str, url: str) -> bool:
    """Allowed only if EVERY relevant agent name is allowed (most restrictive wins)."""
    return all(rp.can_fetch(agent, url) for agent in robots_agents(user_agent))


STOP_STATUSES = ("disallowed", "access_restricted", "blocked_by_challenge", "error")


def evaluate_robots(status: Optional[int], body: str, headers: dict[str, str], user_agent: str, target_url: str) -> dict[str, Any]:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    if status is None:
        return {"robots_status": "error", "proceed": False, "http_status": None,
                "reason": "robots.txt could not be fetched (network/timeout); stopping conservatively."}
    if status in (404, 410):
        return {"robots_status": "unavailable", "proceed": True, "http_status": status,
                "reason": "No robots.txt (HTTP %d): no stated restriction." % status}
    if status in (401, 403, 429):
        challenged = "cf-mitigated" in h or "just a moment" in (body or "")[:2000].lower()
        return {"robots_status": "blocked_by_challenge" if challenged else "access_restricted", "proceed": False,
                "http_status": status,
                "reason": ("The site answered the robots.txt request with a bot challenge" if challenged
                           else "The site restricts access to automated clients") + f" (HTTP {status}); inspection stopped, no workaround attempted."}
    if status >= 500 or status < 200 or status >= 300:
        return {"robots_status": "error", "proceed": False, "http_status": status,
                "reason": f"robots.txt returned HTTP {status}; stopping conservatively."}
    rp = urllib.robotparser.RobotFileParser()
    rp.parse((body or "")[:500_000].splitlines())
    rp.modified()  # mark as checked; otherwise can_fetch() denies everything for an empty file
    path = urlparse(target_url).path or "/"
    if urlparse(target_url).query:
        path += "?" + urlparse(target_url).query
    allowed = can_fetch_all(rp, user_agent, path)
    return {"robots_status": "allowed" if allowed else "disallowed", "proceed": bool(allowed), "http_status": status,
            "reason": "robots.txt allows this path." if allowed else "robots.txt disallows this path for our user agent."}


async def fetch_and_evaluate(page, target_url: str, user_agent: str, timeout_ms: int = 15000) -> dict[str, Any]:
    """Fetch /robots.txt of target_url's origin through the guarded page and evaluate it."""
    p = urlparse(target_url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        resp = await page.goto(robots_url, wait_until="domcontentloaded", timeout=timeout_ms)
        if resp is None:
            return {**evaluate_robots(None, "", {}, user_agent, target_url), "robots_url": robots_url}
        body = ""
        try:
            body = (await resp.text())[:500_000]
        except Exception:
            pass
        result = evaluate_robots(resp.status, body, dict(resp.headers), user_agent, target_url)
    except Exception as exc:
        result = evaluate_robots(None, "", {}, user_agent, target_url)
        result["reason"] += f" ({type(exc).__name__})"
    result["robots_url"] = robots_url
    return result
