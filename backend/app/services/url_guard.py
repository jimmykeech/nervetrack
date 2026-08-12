"""SSRF guard for the per-user LLM ``base_url`` (issue #13).

A custom ``base_url`` is a real feature — self-hosted Ollama / LM Studio on
localhost — so this guard is auth-mode-aware rather than a blanket
private-range ban:

- ``auth_mode == "none"`` is a single local user; no trust boundary is
  crossed, so anything with a valid http(s) scheme and hostname passes.
- ``password``/``google`` are multi-user: the URL must be ``https`` (unless
  it matches the ``NERVETRACK_LLM_ALLOWED_BASE_URLS`` operator allowlist) and
  must not resolve to a loopback, link-local, private, reserved, multicast,
  or unspecified address.

Two entry points share everything except DNS resolution: ``validate_llm_base_url``
does a blocking ``socket.getaddrinfo`` and is meant for the settings-save path;
``validate_llm_base_url_async`` uses the running loop's non-blocking resolver
and is meant for the per-request re-check called from async endpoints.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.config import get_settings, normalize_origin

_ALLOWED_SCHEMES = {"http", "https"}


def _parse(url: str) -> tuple[str, str, int | None]:
    """Validate scheme + hostname. Returns (scheme, hostname, port)."""
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"base_url must use http or https, got {parts.scheme or 'none'!r}")
    hostname = parts.hostname
    if not hostname:
        raise ValueError("base_url must include a hostname")
    return parts.scheme, hostname, parts.port


def _prepare(url: str) -> tuple[str, str] | None:
    """Run the scheme/auth-mode/allowlist checks shared by both entry points.

    Returns ``(scheme, hostname)`` if DNS resolution and address checks are
    still needed, or ``None`` if the URL is already known-good (single-user
    mode, or an operator-allowlisted origin).
    """
    scheme, hostname, port = _parse(url)

    settings = get_settings()
    if not settings.is_multi_user():
        return None

    origin = normalize_origin(scheme, hostname, port)
    if origin in settings.llm_allowed_base_url_set():
        return None  # operator-approved internal gateway

    if scheme != "https":
        raise ValueError("base_url must use https in multi-user mode")

    return scheme, hostname


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _check_addresses(addresses: set[str]) -> None:
    for addr in addresses:
        # Strip a zone/scope id (e.g. "fe80::1%eth0") before parsing.
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
        if _is_disallowed_ip(ip):
            raise ValueError(f"base_url resolves to a disallowed address: {addr}")


def validate_llm_base_url(url: str) -> None:
    """Reject base URLs that would let a user aim the backend at internal hosts.

    Blocking (uses ``socket.getaddrinfo``) — for the settings-save path only.
    Raises ``ValueError`` with a user-facing message on rejection.
    """
    prepared = _prepare(url)
    if prepared is None:
        return
    _, hostname = prepared

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except OSError as exc:
            raise ValueError(f"could not resolve base_url host: {hostname}") from exc
        _check_addresses({info[4][0] for info in infos})
    else:
        _check_addresses({hostname})


async def validate_llm_base_url_async(url: str) -> None:
    """Async twin of ``validate_llm_base_url`` for the request-time re-check.

    Uses the running loop's non-blocking resolver so it is safe to call from
    async endpoints without stalling the event loop.
    """
    prepared = _prepare(url)
    if prepared is None:
        return
    _, hostname = prepared

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(hostname, None)
        except OSError as exc:
            raise ValueError(f"could not resolve base_url host: {hostname}") from exc
        _check_addresses({info[4][0] for info in infos})
    else:
        _check_addresses({hostname})
