"""Fetch a public web page and extract its readable text.

Guards: http(s) only; hostnames resolving to private, loopback, link-local or reserved
addresses are refused (SSRF protection); robots.txt is honoured; size and time limits
apply; only HTML/plain-text responses are accepted. The extracted text is untrusted
input and is only ever analysed, never executed or obeyed.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .config import settings

USER_AGENT = "ContentQualityChecker/1.0 (+editorial audit tool)"


class ExtractionError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def validate_url(url: str) -> str:
    url = url.strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ExtractionError("Only http:// and https:// URLs are supported.")
    if not p.hostname:
        raise ExtractionError("The URL has no host name.")
    if p.username or p.password:
        raise ExtractionError("URLs with embedded credentials are not allowed.")
    return url


async def _check_host(host: str) -> None:
    if settings.allow_private_urls:
        return
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ExtractionError(f"Could not resolve host “{host}”.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ExtractionError("That address points to a private or local network, which is not allowed.", 403)


async def _robots_allows(client: httpx.AsyncClient, url: str) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = await client.get(robots_url)
    except httpx.HTTPError:
        return True  # unreachable robots.txt: treat as allowed (standard practice)
    if r.status_code in (401, 403):
        return False
    if r.status_code >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(USER_AGENT, url)


def html_to_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe", "template"]):
        tag.decompose()
    for tag in soup.select("[aria-hidden=true], [hidden], .cookie, #cookie-banner"):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    blocks: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre", "td"]):
        if el.find_parent(["li", "blockquote"]) and el.name in ("p",):
            continue
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
        if not t:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            t = "#" * int(el.name[1]) + " " + t
        elif el.name == "li":
            t = "- " + t
        blocks.append(t)
    if not blocks:
        txt = re.sub(r"\s+", " ", root.get_text(" ", strip=True))
        blocks = [txt] if txt else []
    return title, "\n\n".join(blocks)


async def extract(url: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> tuple[str, str, str]:
    """Return (final_url, title, text)."""
    url = validate_url(url)
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout, transport=transport, headers={"User-Agent": USER_AGENT}, follow_redirects=False
    ) as client:
        if transport is None:
            await _check_host(urlparse(url).hostname or "")
        if not await _robots_allows(client, url):
            raise ExtractionError("This site's robots.txt does not permit automated access to that page. Paste the text instead.", 403)
        current = url
        for _ in range(5):
            try:
                async with client.stream("GET", current) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                        current = validate_url(urljoin(current, r.headers["location"]))
                        if transport is None:
                            await _check_host(urlparse(current).hostname or "")
                        continue
                    if r.status_code >= 400:
                        raise ExtractionError(f"The page returned HTTP {r.status_code}.", 502)
                    ctype = r.headers.get("content-type", "").lower()
                    if "html" not in ctype and "text/plain" not in ctype:
                        raise ExtractionError(f"Unsupported content type “{ctype or 'unknown'}”. Only HTML pages can be extracted.", 415)
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf += chunk
                        if len(buf) > settings.fetch_max_bytes:
                            raise ExtractionError("The page is too large to extract.", 413)
                    body = buf.decode(r.encoding or "utf-8", errors="replace")
                    break
            except httpx.TimeoutException as e:
                raise ExtractionError("The page took too long to respond.", 504) from e
            except httpx.HTTPError as e:
                raise ExtractionError(f"Could not fetch the page ({type(e).__name__}).", 502) from e
        else:
            raise ExtractionError("Too many redirects.", 502)
    if "text/plain" in ctype:
        title, text = "", body.strip()
    else:
        title, text = html_to_text(body)
    if len(text.strip()) < 40:
        raise ExtractionError("No readable article text was found on that page. It may be rendered with JavaScript; paste the text instead.", 422)
    if len(text) > settings.max_chars:
        text = text[: settings.max_chars]
    return current, title, text
