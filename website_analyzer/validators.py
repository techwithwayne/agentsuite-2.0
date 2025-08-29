# website_analyzer/validators.py
import re
import socket
import ipaddress
from urllib.parse import urlparse, urlunparse

# Optional: soft blocklist (add your own)
BLOCKED_TLDS = (".local", ".internal", ".invalid")
BLOCKED_HOST_SUBSTRINGS = ("localhost",)

def normalize_target_url(raw: str) -> str:
    """
    Normalize user input into a canonical HTTPS URL.
    - Adds scheme if missing
    - Forces https
    - Strips spaces and trailing slash on netloc
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("Missing URL")
    raw = raw.strip()
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parts = list(urlparse(raw))
    parts[0] = "https"  # force https
    if not parts[1]:
        raise ValueError("URL missing host")
    parts[1] = parts[1].rstrip("/")
    # Clean fragments; leave query intact
    parts[5] = ""  # fragment
    return urlunparse(parts)

def _is_ip_private(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast
    except ValueError:
        return True  # if parsing fails, treat as unsafe

def host_is_blocked(host: str) -> bool:
    host_l = host.lower()
    if any(b in host_l for b in BLOCKED_HOST_SUBSTRINGS):
        return True
    if any(host_l.endswith(tld) for tld in BLOCKED_TLDS):
        return True
    return False

def resolve_and_assert_public(host: str) -> None:
    """
    Resolve A/AAAA and ensure all resolved IPs are public.
    Raises ValueError on private/loopback/etc.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {host}: {e}") from e

    ips = []
    for family, _, _, _, sockaddr in infos:
        ip = sockaddr[0]
        ips.append(ip)
        if _is_ip_private(ip):
            raise ValueError(f"Blocked private/loopback IP {ip} for host {host}")
    if not ips:
        raise ValueError(f"No IPs resolved for {host}")

def validate_target_url(raw: str) -> str:
    """
    Full validation pipeline:
    - normalize to https
    - basic host sanity
    - block private/localhost/internal
    """
    url = normalize_target_url(raw)
    parts = urlparse(url)
    host = parts.hostname or ""
    if not host:
        raise ValueError("URL must include a host")
    if host_is_blocked(host):
        raise ValueError(f"Host {host} is blocked")
    resolve_and_assert_public(host)
    if parts.scheme not in ("https", "http"):  # should always be https after normalize
        raise ValueError("Unsupported scheme")
    return url
