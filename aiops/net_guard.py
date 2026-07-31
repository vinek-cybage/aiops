import http.client
import ipaddress
import os
import socket
import ssl
from urllib.parse import urlparse

# Docker-network service names that are legitimate "internal" targets in this
# stack. Narrowly scoped to telemetry-api only — that's the one case a team's
# own MCP server config might legitimately need to point back into this stack
# by container DNS name. aiops-api/aiops-db/loki/grafana have no such reason
# to ever be a team-configured target, so they're deliberately NOT allowlisted:
# letting a team's data-source/MCP "test connection" reach them would be an
# SSRF primitive against internal-only services, even though only the
# hostname (not path/query) could ever have been restricted anyway.
INTERNAL_HOSTNAME_ALLOWLIST = {"telemetry-api"}

_ALLOW_HTTP = os.getenv("NET_GUARD_ALLOW_HTTP", "false").lower() == "true"
_TIMEOUT_SECONDS = 5
_MAX_RESPONSE_BYTES = 1024 * 1024


class UnsafeUrlError(ValueError):
    pass


def _is_private_or_reserved(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


def validate_outbound_url(url: str) -> str:
    """Raises UnsafeUrlError if url isn't safe to have the backend connect to.
    Called before any test-connection / live call to a team-supplied endpoint
    (MCP servers, data sources) — these URLs are attacker-controllable input,
    so this is the SSRF boundary.

    Returns the resolved IP address to actually connect to. Callers that go on
    to make the request (safe_get) MUST reuse this exact IP rather than
    re-resolving the hostname — re-resolving at connect time is a classic
    DNS-rebinding bypass (validate against a safe IP, then have the real
    connection follow a since-changed DNS record to an internal address)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https",) and not (_ALLOW_HTTP and parsed.scheme == "http"):
        raise UnsafeUrlError(f"URL scheme must be https (got {parsed.scheme!r})")
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as e:
        raise UnsafeUrlError(f"Could not resolve host: {e}")
    if not addr_infos:
        raise UnsafeUrlError("Could not resolve host: no addresses returned")

    if parsed.hostname in INTERNAL_HOSTNAME_ALLOWLIST:
        return addr_infos[0][4][0]

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        if _is_private_or_reserved(ip_str):
            raise UnsafeUrlError(f"URL resolves to a non-routable address ({ip_str}) — not allowed")

    return addr_infos[0][4][0]


def safe_get(url: str, headers: dict | None = None) -> bytes:
    """Fetches url after validating it, connecting directly to the single IP
    validate_outbound_url resolved (never re-resolving the hostname, which
    would reopen the DNS-rebinding window) and refusing to follow redirects —
    a validated-safe URL redirecting to an internal address at request time is
    a classic SSRF bypass; the caller can re-validate and re-request manually
    if a redirect ever needs support."""
    ip = validate_outbound_url(url)
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    raw_sock = socket.create_connection((ip, port), timeout=_TIMEOUT_SECONDS)
    try:
        if parsed.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(raw_sock, server_hostname=parsed.hostname)
            conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=_TIMEOUT_SECONDS)
        else:
            sock = raw_sock
            conn = http.client.HTTPConnection(parsed.hostname, port, timeout=_TIMEOUT_SECONDS)
        conn.sock = sock
        try:
            req_headers = dict(headers or {})
            req_headers.setdefault("Host", parsed.hostname)
            conn.request("GET", path, headers=req_headers)
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                raise UnsafeUrlError(f"Refusing to follow redirect (status {resp.status})")
            return resp.read(_MAX_RESPONSE_BYTES)
        finally:
            conn.close()
    except Exception:
        raw_sock.close()
        raise
