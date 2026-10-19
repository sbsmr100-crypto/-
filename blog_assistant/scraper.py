"""네이버 블로그 글 본문을 가져와 구조(문단/이미지/소제목 등)로 파싱한다.

blog.naver.com/{id}/{logNo} 형태의 주소는 iframe 껍데기라서, 실제 본문이 있는
PostView.naver 주소로 바꿔서 요청한다. 스마트에디터 ONE(se-*)과 구 에디터
(#postViewArea)를 모두 지원한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
_HASHTAG_RE = re.compile(r"#([0-9A-Za-z가-힣_]{2,30})")


@dataclass
class Block:
    """본문을 위에서 아래로 읽은 순서대로의 블록 하나."""

    kind: str  # text | heading | image | video | sticker | quote | link | map | table | divider
    text: str = ""


@dataclass
class BlogPost:
    url: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    bold_phrases: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    thumbnail_url: str = ""  # 대표이미지(og:image) = 홈판/검색 결과에 보이는 썸네일

    @property
    def paragraphs(self) -> list[str]:
        return [b.text for b in self.blocks if b.kind == "text" and b.text]

    @property
    def headings(self) -> list[str]:
        return [b.text for b in self.blocks if b.kind == "heading" and b.text]

    @property
    def body_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.kind in ("text", "heading", "quote") and b.text)

    def count(self, kind: str) -> int:
        return sum(1 for b in self.blocks if b.kind == kind)


def parse_blog_url(url: str) -> tuple[str, str] | None:
    """네이버 블로그 주소에서 (blogId, logNo)를 뽑는다. 아니면 None."""
    parsed = urlparse(url.strip())
    if "blog.naver.com" not in parsed.netloc:
        return None
    qs = parse_qs(parsed.query)
    if "blogId" in qs and "logNo" in qs:
        return qs["blogId"][0], qs["logNo"][0]
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0], parts[1]
    if len(parts) == 1 and "logNo" in qs:
        return parts[0], qs["logNo"][0]
    return None


def postview_url(url: str) -> str:
    ids = parse_blog_url(url)
    if not ids:
        return url
    blog_id, log_no = ids
    return f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}&directAccess=false"


def fetch_post(url: str, timeout: float = 15.0) -> BlogPost:
    resp = requests.get(
        postview_url(url),
        headers={"User-Agent": USER_AGENT, "Referer": "https://blog.naver.com/"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return parse_post_html(resp.text, url=url)


def _text(el: Tag) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _component_kind(classes: list[str]) -> str | None:
    c = set(classes)
    if c & {"se-sectionTitle", "se-section-sectionTitle"}:
        return "heading"
    if c & {"se-image", "se-imageGroup", "se-imageStrip", "se-section-image"}:
        return "image"
    if c & {"se-video", "se-oembed"}:
        return "video"
    if "se-sticker" in c:
        return "sticker"
    if "se-quotation" in c:
        return "quote"
    if "se-oglink" in c:
        return "link"
    if c & {"se-placesMap", "se-map"}:
        return "map"
    if "se-table" in c:
        return "table"
    if "se-horizontalLine" in c:
        return "divider"
    if "se-text" in c:
        return "text"
    return None


def _parse_smart_editor(container: Tag) -> list[Block]:
    blocks: list[Block] = []
    for comp in container.select("div.se-component"):
        kind = _component_kind(comp.get("class", []))
        if kind is None:
            continue
        if kind == "text":
            for p in comp.select(".se-text-paragraph"):
                t = _text(p)
                if t:
                    blocks.append(Block("text", t))
        elif kind == "image":
            n = max(1, len(comp.select("img")))
            caption = comp.select_one(".se-caption")
            for i in range(n):
                blocks.append(Block("image", _text(caption) if caption and i == 0 else ""))
        else:
            blocks.append(Block(kind, _text(comp) if kind in ("heading", "quote", "link", "table") else ""))
    return blocks


def _parse_legacy(container: Tag) -> list[Block]:
    blocks: list[Block] = []
    for el in container.find_all(["p", "img", "h2", "h3", "h4", "blockquote"]):
        if el.name == "img":
            blocks.append(Block("image"))
        elif el.name in ("h2", "h3", "h4"):
            blocks.append(Block("heading", _text(el)))
        elif el.name == "blockquote":
            blocks.append(Block("quote", _text(el)))
        else:
            t = _text(el)
            if t:
                blocks.append(Block("text", t))
            blocks.extend(Block("image") for _ in el.find_all("img"))
    return blocks


def parse_post_html(html: str, url: str = "") -> BlogPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(".se-title-text") or soup.select_one(".pcol1") or soup.select_one(".htitle")
    title = _text(title_el) if title_el else ""
    if not title:
        og = soup.select_one('meta[property="og:title"]')
        title = (og.get("content") or "").strip() if og else ""

    container = soup.select_one(".se-main-container")
    if container is not None:
        blocks = _parse_smart_editor(container)
    else:
        legacy = soup.select_one("#postViewArea") or soup.select_one(".post-view")
        blocks = _parse_legacy(legacy) if legacy else []
        container = legacy

    bold: list[str] = []
    if container is not None:
        for b in container.select("b, strong"):
            t = _text(b)
            if t and t not in bold:
                bold.append(t)

    tags: list[str] = []
    for el in soup.select('[class*="tag"] a, [class*="tag"] span'):
        for m in _HASHTAG_RE.finditer(_text(el)):
            if m.group(1) not in tags:
                tags.append(m.group(1))
    body = "\n".join(b.text for b in blocks)
    for m in _HASHTAG_RE.finditer(body):
        if m.group(1) not in tags:
            tags.append(m.group(1))

    image_urls: list[str] = []
    if container is not None:
        for img in container.select("img"):
            src = img.get("data-lazy-src") or img.get("src") or ""
            if src.startswith("http") and "sticker" not in src and src not in image_urls:
                image_urls.append(src)
    og_img = soup.select_one('meta[property="og:image"]')
    thumbnail = (og_img.get("content") or "").strip() if og_img else ""

    return BlogPost(
        url=url,
        title=title,
        blocks=blocks,
        tags=tags,
        bold_phrases=bold,
        image_urls=image_urls,
        thumbnail_url=thumbnail or (image_urls[0] if image_urls else ""),
    )


def post_from_text(title: str, body: str, url: str = "", image_count: int = 0) -> BlogPost:
    """네이버 접속이 막힌 환경용: 직접 복사해 붙인 제목/본문으로 BlogPost를 만든다.
    '## '나 '### '로 시작하는 줄은 소제목, '[사진]' 줄은 이미지로 본다."""
    blocks: list[Block] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#") and not _HASHTAG_RE.match(line):
            blocks.append(Block("heading", line.lstrip("# ").strip()))
        elif line in ("[사진]", "[이미지]"):
            blocks.append(Block("image"))
        else:
            blocks.append(Block("text", line))
    blocks.extend(Block("image") for _ in range(image_count))
    tags = list(dict.fromkeys(m.group(1) for m in _HASHTAG_RE.finditer(body)))
    return BlogPost(url=url, title=title.strip(), blocks=blocks, tags=tags)
