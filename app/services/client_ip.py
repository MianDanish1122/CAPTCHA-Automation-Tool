"""
Client IP resolution that cannot be spoofed by arbitrary clients.

`X-Forwarded-For` is attacker-controlled unless it was appended by a proxy WE operate.
Rules:
  * By default (TRUSTED_PROXIES empty) forwarding headers are ignored entirely and the
    direct TCP peer address is used.
  * If the direct peer is a configured trusted proxy, X-Forwarded-For is walked from
    right to left, skipping addresses that are themselves trusted proxies; the first
    untrusted address is the client. Entries the client prepended to the header are
    therefore never used.
  * Malformed header values fall back to the direct peer.
"""
import ipaddress
from functools import lru_cache
from typing import Iterable, Optional

from app.config import settings

_FALLBACK_IP = "127.0.0.1"


@lru_cache(maxsize=32)
def _parse_networks(entries: tuple[str, ...]):
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue  # ignore malformed config entries (fail closed: they trust nothing)
    return tuple(networks)


def _is_trusted(ip_text: str, networks) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return any(ip.version == n.version and ip in n for n in networks)


def resolve_client_ip(
    peer_host: Optional[str],
    forwarded_for: Optional[str],
    trusted_proxies: Optional[Iterable[str]] = None,
) -> str:
    """Pure function: determine the effective client IP."""
    peer = (peer_host or "").strip() or _FALLBACK_IP
    entries = tuple(settings.TRUSTED_PROXIES if trusted_proxies is None else trusted_proxies)
    networks = _parse_networks(entries)

    if not networks or not forwarded_for or not _is_trusted(peer, networks):
        return peer

    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    for hop in reversed(hops):
        try:
            ipaddress.ip_address(hop)
        except ValueError:
            return peer  # malformed chain: do not trust any of it
        if not _is_trusted(hop, networks):
            return hop
    return peer  # every hop was a trusted proxy


def get_client_ip(request) -> str:
    """FastAPI/Starlette request helper."""
    if request is None:
        return _FALLBACK_IP
    peer = request.client.host if getattr(request, "client", None) else None
    return resolve_client_ip(peer, request.headers.get("X-Forwarded-For"))
