"""Read a web page: title, description, visible text, images, price."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .. import http

log = logging.getLogger(__name__)

# Sites that build their pages with JavaScript, so a plain download misses the content.
JS_HEAVY_DOMAINS = ("ideas.lego.com", "kickstarter.com", "indiegogo.com", "etsy.com", "instagram.com")
MAX_TEXT = 15_000
SKIP_IMAGE_HINTS = ("logo", "icon", "sprite", "avatar", "badge", "pixel", "tracking", "favicon", ".svg", "data:")


@dataclass
class Page:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    images: list[str] = field(default_factory=list)
    price: str | None = None
    site_name: str = ""
    scripts: str = ""   # raw <script> contents: modern sites embed exact data (counts, names) here


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _json_ld(soup: BeautifulSoup) -> list[dict]:
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        out.extend(i for i in items if isinstance(i, dict))
    return out


def parse_html(url: str, html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    page = Page(url=url)
    page.title = _meta(soup, "og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    page.description = _meta(soup, "og:description", "description", "twitter:description")
    page.site_name = _meta(soup, "og:site_name") or urlparse(url).netloc

    images: list[str] = []
    for name in ("og:image", "og:image:url", "twitter:image"):
        value = _meta(soup, name)
        if value:
            images.append(urljoin(url, value))

    for entry in _json_ld(soup):
        img = entry.get("image")
        if isinstance(img, str):
            images.append(urljoin(url, img))
        elif isinstance(img, list):
            images.extend(urljoin(url, i if isinstance(i, str) else i.get("url", "")) for i in img)
        offers = entry.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict) and offers.get("price") and not page.price:
            page.price = f"{offers.get('price')} {offers.get('priceCurrency', '')}".strip()

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or any(h in src.lower() for h in SKIP_IMAGE_HINTS):
            continue
        width = img.get("width")
        if width and str(width).isdigit() and int(width) < 200:
            continue
        images.append(urljoin(url, src))

    seen = set()
    page.images = [i for i in images if i.startswith("http") and not (i in seen or seen.add(i))][:12]

    page.scripts = "\n".join(t.string or t.get_text() or "" for t in soup.find_all("script"))[:2_000_000]

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    page.text = text.strip()[:MAX_TEXT]
    return page


def _render_with_browser(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(user_agent=http.USER_AGENT)
            pg = ctx.new_page()
            pg.goto(url, wait_until="networkidle", timeout=60_000)
            html = pg.content()
            browser.close()
            return html
    except Exception as exc:  # browser problems shouldn't kill intake
        log.warning("browser render failed for %s: %s", url, exc)
        return None


def fetch_page(url: str, force_browser: bool = False) -> Page:
    if not urlparse(url).scheme.startswith("http"):
        raise ValueError(f"not a web link: {url}")
    host = urlparse(url).netloc.lower()
    html = None
    if force_browser or any(host.endswith(d) for d in JS_HEAVY_DOMAINS):
        html = _render_with_browser(url)
    if html is None:
        html = http.get(url).text
    page = parse_html(url, html)
    if len(page.text) < 400 and not force_browser:
        rendered = _render_with_browser(url)
        if rendered:
            richer = parse_html(url, rendered)
            if len(richer.text) > len(page.text):
                page = richer
    return page
