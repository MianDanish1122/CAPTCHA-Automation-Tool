import ipaddress
import socket
from urllib.parse import urlparse
from app.config import settings

# Explicit blocked metadata IPs (AWS, GCP, Azure, OpenStack, IPv4 and IPv6)
CLOUD_METADATA_IPS = {
    "169.254.169.254",
    "fd00:ec2::254",
}

# Special-purpose ranges that must never be reachable, independent of stdlib classification.
_BLOCKED_NETWORKS = [
    (ipaddress.ip_network("0.0.0.0/8"), "'This network'"),
    (ipaddress.ip_network("10.0.0.0/8"), "Private RFC 1918"),
    (ipaddress.ip_network("100.64.0.0/10"), "Carrier-grade NAT (CGNAT, RFC 6598)"),
    (ipaddress.ip_network("127.0.0.0/8"), "Loopback"),
    (ipaddress.ip_network("169.254.0.0/16"), "Link-local"),
    (ipaddress.ip_network("172.16.0.0/12"), "Private RFC 1918"),
    (ipaddress.ip_network("192.0.0.0/24"), "IETF protocol assignment"),
    (ipaddress.ip_network("192.0.2.0/24"), "Documentation (TEST-NET-1)"),
    (ipaddress.ip_network("192.88.99.0/24"), "6to4 relay anycast"),
    (ipaddress.ip_network("192.168.0.0/16"), "Private RFC 1918"),
    (ipaddress.ip_network("198.18.0.0/15"), "Benchmarking"),
    (ipaddress.ip_network("198.51.100.0/24"), "Documentation (TEST-NET-2)"),
    (ipaddress.ip_network("203.0.113.0/24"), "Documentation (TEST-NET-3)"),
    (ipaddress.ip_network("224.0.0.0/4"), "Multicast"),
    (ipaddress.ip_network("240.0.0.0/4"), "Reserved (Class E / broadcast)"),
    (ipaddress.ip_network("::/128"), "Unspecified"),
    (ipaddress.ip_network("::1/128"), "Loopback"),
    (ipaddress.ip_network("64:ff9b:1::/48"), "Local-use NAT64"),
    (ipaddress.ip_network("100::/64"), "Discard-only"),
    (ipaddress.ip_network("2001::/23"), "IETF protocol assignment / Teredo"),
    (ipaddress.ip_network("2001:db8::/32"), "Documentation"),
    (ipaddress.ip_network("fc00::/7"), "Unique local (ULA)"),
    (ipaddress.ip_network("fe80::/10"), "IPv6 link-local"),
    (ipaddress.ip_network("fec0::/10"), "Deprecated site-local"),
    (ipaddress.ip_network("ff00::/8"), "IPv6 multicast"),
]
_NAT64_NETWORK = ipaddress.ip_network("64:ff9b::/96")

# Approved ports for HTTP/HTTPS web traffic
APPROVED_PORTS = {80, 443, 8080, 8443, 8888}


class SecurityException(Exception):
    """Raised when security or SSRF validation fails."""
    pass


class SecurityGuard:
    @staticmethod
    def is_ip_allowed(ip_str: str) -> tuple[bool, str]:
        """
        Check whether an IP address is a safe, publicly routable destination.

        Policy: only *globally routable* unicast addresses are allowed. In addition to the
        stdlib `is_global` check, well-known special-purpose ranges are blocked explicitly
        (so the decision never depends on stdlib classification quirks), and IPv6 forms that
        embed an IPv4 address (IPv4-mapped, NAT64, 6to4, Teredo) are unwrapped and re-checked.
        """
        if not ip_str:
            return False, "IP address is empty."

        clean_ip = ip_str.strip().strip("[]")
        clean_ip = clean_ip.split("%", 1)[0]  # drop IPv6 zone id (fe80::1%eth0)

        try:
            ip = ipaddress.ip_address(clean_ip)
        except ValueError:
            return False, f"Invalid IP address format: {clean_ip}"

        return SecurityGuard._check_ip_object(ip, clean_ip, depth=0)

    @staticmethod
    def _check_ip_object(ip, label: str, depth: int) -> tuple[bool, str]:
        if depth > 2:
            return False, f"Address ({label}) embeds nested IP encodings and is prohibited."

        if str(ip) in CLOUD_METADATA_IPS:
            return False, f"Access to cloud metadata IP ({label}) is prohibited."

        # Unwrap IPv6 addresses that embed an IPv4 destination.
        if isinstance(ip, ipaddress.IPv6Address):
            embedded = None
            if ip.ipv4_mapped is not None:
                embedded = ip.ipv4_mapped
            elif ip in _NAT64_NETWORK:
                embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            elif ip.sixtofour is not None:
                embedded = ip.sixtofour
            elif ip.teredo is not None:
                return False, f"Teredo tunnel address ({label}) is prohibited."
            if embedded is not None:
                ok, reason = SecurityGuard._check_ip_object(
                    embedded, f"{embedded} (embedded in {label})", depth + 1
                )
                if not ok:
                    return False, reason
                return False, f"IPv6 transition-mechanism address ({label}) is prohibited."

        for network, description in _BLOCKED_NETWORKS:
            if ip.version == network.version and ip in network:
                return False, f"{description} address ({label}) is prohibited."

        if ip.is_loopback:
            return False, f"Loopback address ({label}) is prohibited."
        if ip.is_link_local:
            return False, f"Link-local address ({label}) is prohibited."
        if ip.is_multicast:
            return False, f"Multicast address ({label}) is prohibited."
        if ip.is_unspecified:
            return False, f"Unspecified address ({label}) is prohibited."
        if ip.is_private:
            return False, f"Private / non-routable address ({label}) is prohibited."
        if ip.is_reserved:
            return False, f"Reserved address ({label}) is prohibited."
        if not ip.is_global:
            return False, f"Non-global address ({label}) is prohibited."

        return True, "IP is public and allowed"

    @classmethod
    def resolve_public_addresses(
        cls, hostname: str, port: int, allow_loopback: bool = False
    ) -> tuple[list[str], str]:
        """
        Resolve `hostname` NOW and return (validated_ips, reason).
        Every resolved address must be public; one bad record rejects the host.
        Callers must connect to the returned IPs directly (pinning) to defeat DNS rebinding.
        """
        host = hostname.lower().strip("[]")
        loopback_names = ("localhost", "127.0.0.1", "::1")
        if host in loopback_names:
            if settings.can_allow_loopback:  # server-controlled: dev/test + ALLOW_DEV_LOOPBACK only
                return ["127.0.0.1" if host == "localhost" else host], "loopback permitted (dev/test)"
            return [], f"Loopback address ({host}) is prohibited."

        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            try:
                infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            except socket.gaierror as e:
                return [], f"DNS resolution failed for '{host}': {e}"
            addresses = []
            for info in infos:
                addr = info[4][0]
                if addr not in addresses:
                    addresses.append(addr)

        if not addresses:
            return [], f"Could not resolve host '{host}'."

        for addr in addresses:
            ok, reason = cls.is_ip_allowed(addr)
            if not ok:
                return [], f"Host '{host}' resolved to prohibited address {addr}: {reason}"
        return addresses, "ok"

    @classmethod
    def validate_target_url(
        cls,
        url: str,
        enforce_live_scan: bool = True,
        allow_loopback: bool = False,
    ) -> tuple[bool, str]:
        """
        Validate a target URL against SSRF, protocol, port, and domain allowlist policies.
        Server-side settings.can_allow_loopback strictly governs whether any loopback exception is valid.
        Client cannot enable loopback access in staging or production.
        """
        if not url:
            return False, "Target URL cannot be empty."

        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Malformed URL syntax: {str(e)}"

        # 1. Protocol Scheme Check
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Invalid protocol scheme '{parsed.scheme}'. Only http and https are permitted."

        raw_hostname = parsed.hostname
        if not raw_hostname:
            return False, "URL does not contain a valid hostname."

        hostname = raw_hostname.lower().strip("[]")

        # 2. Determine Server-Side Loopback Exception Authority
        # A loopback exception requires:
        # a) Server configuration ALLOW_DEV_LOOPBACK=true
        # b) Server environment APP_ENV in ("development", "test")
        # c) Target hostname must be explicitly localhost / 127.0.0.1 / ::1
        # In staging or production, settings.can_allow_loopback is ALWAYS False.
        effective_loopback_allowed = (
            allow_loopback and settings.can_allow_loopback
        ) or (settings.can_allow_loopback and hostname in ("localhost", "127.0.0.1", "::1"))

        # 3. Port Check
        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        is_loopback_host = hostname in ("localhost", "127.0.0.1", "::1")
        if target_port not in APPROVED_PORTS:
            # In server-authorized dev/test mode, dynamic localhost test server ports (> 1024) are permitted
            if not (effective_loopback_allowed and is_loopback_host and 1024 < target_port <= 65535):
                return False, f"Non-standard port '{target_port}' is not permitted."

        # 4. Credential Injection Check
        if parsed.username or parsed.password:
            return False, "Embedded credentials in URL are prohibited."

        # 5. Check if hostname is an IP literal
        try:
            ip_obj = ipaddress.ip_address(hostname)
            is_ip = True
        except ValueError:
            is_ip = False
            ip_obj = None

        if is_ip:
            if ip_obj.is_loopback:
                if not effective_loopback_allowed:
                    return False, f"Target IP address prohibited: Loopback address ({hostname}) is prohibited."
            else:
                # Private, metadata, or reserved IPs are NEVER permitted, even with loopback flag
                allowed, reason = cls.is_ip_allowed(hostname)
                if not allowed:
                    return False, f"Target IP address prohibited: {reason}"

        # 6. Domain Allowlist Check (for named domains)
        if settings.ALLOWED_DOMAINS and not is_ip:
            domain_allowed = False
            for allowed in settings.ALLOWED_DOMAINS:
                if hostname == allowed or hostname.endswith("." + allowed):
                    domain_allowed = True
                    break
            if not domain_allowed and not (effective_loopback_allowed and hostname in ("localhost", "127.0.0.1", "::1")):
                return False, f"Domain '{hostname}' is not in the authorized domains allowlist."

        # 7. Live Scanning Authorization Check
        if enforce_live_scan and not settings.ENABLE_LIVE_SCAN:
            is_local_demo = effective_loopback_allowed and hostname in ("localhost", "127.0.0.1", "::1")
            if not is_local_demo:
                return (
                    False,
                    "Live scanning is disabled (ENABLE_LIVE_SCAN=false). "
                    "Only authorized domains or local demo inspection allowed."
                )

        # 8. Loopback Hostname Handling
        if hostname in ("localhost", "127.0.0.1", "::1"):
            if effective_loopback_allowed:
                return True, "Server-authorized local dev/test mode permitted."
            return False, f"Target IP address prohibited: Loopback address ({hostname}) is prohibited."

        # 9. DNS Resolution & Rebinding / Private Subnet Check
        try:
            addr_info = socket.getaddrinfo(hostname, target_port)
            if not addr_info:
                return False, f"Could not resolve host '{hostname}'."

            for entry in addr_info:
                ip_resolved = entry[4][0]
                # Check resolved IP
                allowed, reason = cls.is_ip_allowed(ip_resolved)
                if not allowed:
                    return False, f"Host '{hostname}' resolved to prohibited address {ip_resolved}: {reason}"

        except socket.gaierror as e:
            return False, f"DNS resolution failed for '{hostname}': {str(e)}"
        except Exception as e:
            return False, f"Network validation error for '{hostname}': {str(e)}"

        return True, "URL validated and authorized."

    @classmethod
    def validate_redirect_url(
        cls,
        redirect_url: str,
        original_url: str,
        enforce_live_scan: bool = True,
        allow_loopback: bool = False,
        require_same_domain: bool = True,
    ) -> tuple[bool, str]:
        """
        Validate destination of an HTTP redirect against SSRF, cross-domain, and domain allowlist policies.
        """
        if require_same_domain:
            orig_parsed = urlparse(original_url)
            redir_parsed = urlparse(redirect_url)
            orig_host = (orig_parsed.hostname or "").lower()
            redir_host = (redir_parsed.hostname or "").lower()

            if orig_host != redir_host:
                return False, f"Cross-domain redirect from '{orig_host}' to '{redir_host}' is prohibited."

        allowed, reason = cls.validate_target_url(
            redirect_url,
            enforce_live_scan=enforce_live_scan,
            allow_loopback=allow_loopback,
        )
        if not allowed:
            return False, f"Redirect target rejected: {reason}"

        return True, "Redirect URL is valid and authorized."
