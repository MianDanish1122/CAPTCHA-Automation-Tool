import ipaddress
import socket
from urllib.parse import urlparse
from app.config import settings

# Explicit blocked metadata IPs (AWS, GCP, Azure, OpenStack)
CLOUD_METADATA_IPS = {
    "169.254.169.254",
    "fd00:ec2::254",
}


class SecurityException(Exception):
    """Raised when security or SSRF validation fails."""
    pass


class SecurityGuard:
    @staticmethod
    def is_ip_allowed(ip_str: str) -> tuple[bool, str]:
        """Check if an IP address is safe for automated inspection."""
        if ip_str in CLOUD_METADATA_IPS:
            return False, f"Access to cloud metadata IP ({ip_str}) is prohibited."

        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"Invalid IP address format: {ip_str}"

        if ip.is_loopback:
            return False, f"Loopback address ({ip_str}) is prohibited."
        if ip.is_private:
            return False, f"Private RFC 1918 / CGNAT address ({ip_str}) is prohibited."
        if ip.is_link_local:
            return False, f"Link-local address ({ip_str}) is prohibited."
        if ip.is_multicast:
            return False, f"Multicast address ({ip_str}) is prohibited."
        if ip.is_reserved:
            return False, f"Reserved address ({ip_str}) is prohibited."

        return True, "IP is public and allowed"

    @classmethod
    def validate_target_url(
        cls,
        url: str,
        enforce_live_scan: bool = True,
        allow_loopback: bool = False
    ) -> tuple[bool, str]:
        """
        Validate a target URL against SSRF, protocol, and domain allowlist policies.
        """
        if not url:
            return False, "Target URL cannot be empty."

        try:
            parsed = urlparse(url)
        except Exception as e:
            return False, f"Malformed URL syntax: {str(e)}"

        # 1. Scheme Check
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Invalid protocol scheme '{parsed.scheme}'. Only http and https are permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL does not contain a valid hostname."

        hostname = hostname.lower()

        # 2. Check if hostname is an IP address literal
        try:
            ipaddress.ip_address(hostname)
            is_ip = True
        except ValueError:
            is_ip = False

        if is_ip:
            if not allow_loopback:
                allowed, reason = cls.is_ip_allowed(hostname)
                if not allowed:
                    return False, f"Target IP address prohibited: {reason}"

        # 3. Credential injection check
        if parsed.username or parsed.password:
            return False, "Embedded credentials in URL are prohibited."

        # 4. Port check
        if not allow_loopback and parsed.port and parsed.port not in (80, 443, 8080, 8443):
            return False, f"Non-standard port '{parsed.port}' is not permitted."

        # 5. Check domain allowlist
        if settings.ALLOWED_DOMAINS and not allow_loopback and not is_ip:
            domain_allowed = False
            for allowed in settings.ALLOWED_DOMAINS:
                if hostname == allowed or hostname.endswith("." + allowed):
                    domain_allowed = True
                    break
            if not domain_allowed:
                return False, f"Domain '{hostname}' is not in the authorized domains allowlist."

        # 6. Live scanning authorization check
        if enforce_live_scan and not settings.ENABLE_LIVE_SCAN and not allow_loopback:
            return (
                False,
                "Live scanning is disabled (ENABLE_LIVE_SCAN=false). "
                "Only authorized domains or local demo inspection allowed."
            )

        # 7. DNS resolution & DNS rebinding / Private IP check
        # We allow 'localhost' or '127.0.0.1' only if explicitly permitted (local dev/test mode)
        if hostname in ("localhost", "127.0.0.1"):
            if allow_loopback or ("localhost" in settings.ALLOWED_DOMAINS and not enforce_live_scan):
                return True, "Localhost permitted in local test mode."
            return False, "Localhost navigation is rejected by security policy."

        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            if not addr_info:
                return False, f"Could not resolve host '{hostname}'."

            for entry in addr_info:
                ip_resolved = entry[4][0]
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
