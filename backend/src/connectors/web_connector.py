"""Web 抓取连接器（可选）。

从起始 URL 出发，按同域 BFS 抓取页面，抽取正文。
不依赖第三方库（urllib + html.parser）。
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from src.connectors.base import BaseConnector, RawDocument, ResourceMeta, register

_UA = "Mozilla/5.0 (compatible; AgenticRAGBot/1.0)"


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self.links: List[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        if not self._skip:
            t = data.strip()
            if t:
                self.parts.append(t)


@register("web")
@register("url")
class WebConnector(BaseConnector):
    type = "web"
    subtype = "web"
    capabilities = ("discover", "read", "describe")

    def _start_url(self) -> str:
        return self.config.get("url") or self.config.get("uri") or ""

    def _fetch(self, url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=int(self.config.get("timeout", 10))) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")

    def test_connection(self) -> Tuple[bool, str]:
        url = self._start_url()
        if not url:
            return False, "缺少起始 URL"
        try:
            self._fetch(url)
            return True, f"抓取成功：{url}"
        except Exception as e:  # noqa: BLE001
            return False, f"抓取失败：{type(e).__name__}: {e}"

    def discover(self) -> List[ResourceMeta]:
        url = self._start_url()
        if not url:
            return []
        try:
            html = self._fetch(url)
        except Exception:  # noqa: BLE001
            return [ResourceMeta(name=url, kind="page")]
        parser = _PageParser()
        parser.feed(html)
        base = urllib.parse.urlparse(url)
        seen: Set[str] = set()
        out: List[ResourceMeta] = [ResourceMeta(name=url, kind="page", extra={"title": parser.title})]
        depth = int(self.config.get("depth", 1))
        if depth > 0:
            for href in parser.links:
                full = urllib.parse.urljoin(url, href)
                p = urllib.parse.urlparse(full)
                if p.scheme in ("http", "https") and p.netloc == base.netloc and full not in seen:
                    seen.add(full)
                    out.append(ResourceMeta(name=full, kind="page"))
                if len(out) >= int(self.config.get("max_pages", 50)):
                    break
        return out

    def describe(self, resource: str) -> Any:
        from src.connectors.base import SchemaInfo
        return SchemaInfo(name=resource, description="Web 页面")

    def read(self, resource: Optional[str] = None, watermark: Any = None,
             limit: Optional[int] = None) -> Iterator[RawDocument]:
        targets = [resource] if resource else [m.name for m in self.discover()]
        for i, url in enumerate(targets):
            if limit and i >= limit:
                return
            try:
                html = self._fetch(url)
            except Exception:  # noqa: BLE001
                continue
            parser = _PageParser()
            parser.feed(html)
            yield RawDocument(
                ref=url,
                text="\n".join(parser.parts),
                title=parser.title or url,
                metadata={
                    "source_type": "web",
                    "datasource_id": self.ds_id,
                    "doc_name": parser.title or url,
                    "doc_type": "web",
                    "url": url,
                    "page": 1,
                },
            )
            time.sleep(float(self.config.get("delay", 0.2)))
