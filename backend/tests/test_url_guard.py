"""SSRF guard tests (issue #13): table-driven scheme/address checks, a
monkeypatched-resolver DNS-rebind simulation, and the auth-mode / allowlist
escape hatches.

Note: ``tests/conftest.py`` has an autouse ``_cookie_auth_mode`` fixture that
sets ``NERVETRACK_AUTH_MODE=password`` for every test, so tests in this file
run in multi-user mode by default. Tests that need single-user behaviour
override it explicitly via the ``none_mode`` fixture below.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import httpx
import pytest

from app.config import get_settings
from app.services import url_guard

# ---- fixtures ---------------------------------------------------------------


@pytest.fixture()
def none_mode(monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def allowlist(monkeypatch):
    def _set(*origins: str):
        monkeypatch.setenv("NERVETRACK_LLM_ALLOWED_BASE_URLS", ",".join(origins))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def _fake_getaddrinfo(family_map: dict[str, list[str]]):
    """Blocking-style fake matching socket.getaddrinfo's return shape."""

    def _fake(host, *args, **kwargs):
        return [
            (socket.AF_INET6 if ":" in addr else socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in family_map.get(host, [])
        ]

    return _fake


def _fake_loop_getaddrinfo(family_map: dict[str, list[str]]):
    """Fake for asyncio.BaseEventLoop.getaddrinfo (bound method: self, host, ...)."""

    async def _fake(self, host, *args, **kwargs):
        return [
            (socket.AF_INET6 if ":" in addr else socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, 0))
            for addr in family_map.get(host, [])
        ]

    return _fake


# ---- schemes: rejected in every mode -----------------------------------------

BAD_SCHEME_URLS = ["file:///etc/passwd", "ftp://example.com/x", "gopher://example.com/x"]


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
def test_bad_scheme_rejected_multi_user(url):
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url(url)


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
def test_bad_scheme_rejected_none_mode(url, none_mode):
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url(url)


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
async def test_bad_scheme_rejected_async(url):
    with pytest.raises(ValueError):
        await url_guard.validate_llm_base_url_async(url)


def test_missing_hostname_rejected():
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("https:///no-host")


# ---- literal addresses: rejected in multi-user mode --------------------------

LITERAL_PRIVATE_URLS = [
    "https://127.0.0.1",
    "https://[::1]",
    "https://10.0.0.1",
    "https://192.168.1.1",
    "https://172.16.0.1",
    "https://169.254.169.254",  # cloud metadata
    "https://[fd00:ec2::254]",  # EC2 IMDSv2 IPv6 metadata address
    "https://0.0.0.0",
]


@pytest.mark.parametrize("url", LITERAL_PRIVATE_URLS)
def test_literal_private_address_rejected_multi_user(url):
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url(url)


@pytest.mark.parametrize("url", LITERAL_PRIVATE_URLS)
async def test_literal_private_address_rejected_multi_user_async(url):
    with pytest.raises(ValueError):
        await url_guard.validate_llm_base_url_async(url)


def test_metadata_address_is_link_local_not_special_cased():
    # Spec: 169.254.169.254 must be caught by the generic link-local check.
    assert ipaddress.ip_address("169.254.169.254").is_link_local


def test_ec2_ula_address_is_private_not_special_cased():
    # Spec: fd00:ec2::254 must be caught by the generic private (ULA) check.
    assert ipaddress.ip_address("fd00:ec2::254").is_private


# ---- scheme requirement in multi-user mode ------------------------------------


def test_http_rejected_multi_user():
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("http://example.com")


def test_https_public_allowed_multi_user(monkeypatch):
    monkeypatch.setattr(
        url_guard.socket,
        "getaddrinfo",
        _fake_getaddrinfo({"api.openai.com": ["93.184.216.34"]}),
    )
    url_guard.validate_llm_base_url("https://api.openai.com/v1")  # must not raise


# ---- monkeypatched resolver: proves this is more than cosmetic ---------------


def test_public_looking_hostname_resolving_privately_is_rejected(monkeypatch):
    """A hostname with no obvious red flags that DNS points at a private
    address must still be rejected. This is what makes the guard more than a
    check on the literal string the user typed."""
    monkeypatch.setattr(
        url_guard.socket,
        "getaddrinfo",
        _fake_getaddrinfo({"sneaky.example.com": ["169.254.169.254"]}),
    )
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("https://sneaky.example.com")


def test_every_resolved_address_is_checked_not_just_the_first(monkeypatch):
    # Public A record + private AAAA record: must reject on the second address.
    monkeypatch.setattr(
        url_guard.socket,
        "getaddrinfo",
        _fake_getaddrinfo({"mixed.example.com": ["93.184.216.34", "fd00::1"]}),
    )
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("https://mixed.example.com")


def test_resolution_failure_is_a_rejection(monkeypatch):
    def _boom(host, *args, **kwargs):
        raise OSError("no such host")

    monkeypatch.setattr(url_guard.socket, "getaddrinfo", _boom)
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("https://nowhere.invalid")


async def test_public_looking_hostname_resolving_privately_is_rejected_async(monkeypatch):
    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "getaddrinfo",
        _fake_loop_getaddrinfo({"sneaky.example.com": ["169.254.169.254"]}),
    )
    with pytest.raises(ValueError):
        await url_guard.validate_llm_base_url_async("https://sneaky.example.com")


async def test_every_resolved_address_is_checked_not_just_the_first_async(monkeypatch):
    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "getaddrinfo",
        _fake_loop_getaddrinfo({"mixed.example.com": ["93.184.216.34", "fd00::1"]}),
    )
    with pytest.raises(ValueError):
        await url_guard.validate_llm_base_url_async("https://mixed.example.com")


async def test_resolution_failure_is_a_rejection_async(monkeypatch):
    async def _boom(self, host, *args, **kwargs):
        raise OSError("no such host")

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", _boom)
    with pytest.raises(ValueError):
        await url_guard.validate_llm_base_url_async("https://nowhere.invalid")


async def test_transport_pins_vetted_address_and_blocks_dns_rebinding(monkeypatch):
    resolutions = iter(["93.184.216.34", "169.254.169.254"])

    async def _rebind(self, host, *args, **kwargs):
        address = next(resolutions)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    class CaptureTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.requests: list[httpx.Request] = []

        async def handle_async_request(self, request):
            self.requests.append(request)
            return httpx.Response(200, request=request)

    capture = CaptureTransport()
    transport = url_guard.PinnedAsyncHTTPTransport(capture)
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", _rebind)

    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://rebind.example/v1")
        with pytest.raises(ValueError, match="disallowed address"):
            await client.get("https://rebind.example/v1")

    assert len(capture.requests) == 1
    request = capture.requests[0]
    assert request.url.host == "93.184.216.34"
    assert request.headers["host"] == "rebind.example"
    assert request.extensions["sni_hostname"] == "rebind.example"


# ---- allowlist escape hatch -----------------------------------------------------


def test_allowlist_origin_allowed_even_http_and_resolving_privately(allowlist, monkeypatch):
    allowlist("http://gateway.internal:8080")
    monkeypatch.setattr(
        url_guard.socket,
        "getaddrinfo",
        _fake_getaddrinfo({"gateway.internal": ["10.0.0.5"]}),
    )
    url_guard.validate_llm_base_url("http://gateway.internal:8080")  # must not raise


def test_allowlist_does_not_match_different_origin(allowlist):
    allowlist("http://gateway.internal:8080")
    with pytest.raises(ValueError):
        url_guard.validate_llm_base_url("http://gateway.internal:9090")  # different port


async def test_allowlist_origin_allowed_async(allowlist, monkeypatch):
    allowlist("http://gateway.internal:8080")
    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "getaddrinfo",
        _fake_loop_getaddrinfo({"gateway.internal": ["10.0.0.5"]}),
    )
    await url_guard.validate_llm_base_url_async("http://gateway.internal:8080")  # must not raise


# ---- auth_mode == "none": localhost Ollama / LM Studio keeps working ----------


def test_none_mode_allows_localhost_ollama(none_mode):
    url_guard.validate_llm_base_url("http://127.0.0.1:11434")  # must not raise
    url_guard.validate_llm_base_url("http://localhost:1234/v1")  # must not raise


async def test_none_mode_allows_localhost_ollama_async(none_mode):
    await url_guard.validate_llm_base_url_async("http://127.0.0.1:11434")
    await url_guard.validate_llm_base_url_async("http://localhost:1234/v1")
