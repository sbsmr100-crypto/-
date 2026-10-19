"""레퍼런스 글 한 편이 '왜' 상위노출/홈판에 올랐는지 Claude가 분석한다 (썸네일 이미지 포함)."""

from __future__ import annotations

import base64
from dataclasses import asdict

import anthropic
import requests
from pydantic import BaseModel, Field

from . import llm
from .analyzer import PostStats
from .scraper import USER_AGENT, BlogPost


class ThumbnailAnalysis(BaseModel):
    seen: bool = Field(description="썸네일 이미지를 실제로 보고 분석했는지")
    text_on_image: str = Field(description="이미지 위 문구 그대로 (없으면 빈 문자열)")
    layout: str = Field(description="구도/배치: 문구 위치, 인물·사물·그래프 배치, 여백")
    colors: str = Field(description="주요 색상과 대비 (가능하면 HEX 추정)")
    typography: str = Field(description="글꼴 느낌, 굵기, 강조 방식(색/박스/밑줄)")
    why_it_works: str = Field(description="작은 카드에서도 클릭을 부르는 이유 또는 약점")


class PostInsight(BaseModel):
    search_intent: str = Field(description="이 키워드 검색자/홈판 독자가 원하는 것")
    why_exposed: list[str] = Field(description="상위노출(또는 홈판 노출)된 핵심 이유. 각 항목에 글 속 근거 포함")
    title_analysis: str = Field(description="제목의 키워드 배치, 후킹 장치, 길이 평가")
    intro_hook: str = Field(description="첫 3줄이 체류를 만드는 방식")
    structure_analysis: str = Field(description="소제목·문단·이미지·표 흐름")
    credibility_elements: list[str] = Field(description="신뢰를 주는 요소: 수치·출처·기준일·경험·전문성")
    timeliness: str = Field(description="시의성(최근 이슈·발표·시즌)과의 연결")
    thumbnail: ThumbnailAnalysis
    weaknesses: list[str] = Field(description="이 글의 약점 = 내가 이길 수 있는 틈")
    reusable_lessons: list[str] = Field(description="다음 글에 그대로 적용할 수 있는 구체적 규칙 3~6개")


SYSTEM = """\
당신은 비즈니스·경제 분야 네이버 블로그 노출 분석가입니다.
사용자가 네이버 크리에이터 어드바이저 등에서 찾은 '키워드별 상위노출 글' 또는 '홈판(블로그 홈·주제판)에 노출된 글'을 줍니다.
이 글이 왜 노출됐는지를, 글 속에서 확인되는 근거를 들어 분석하세요.

관점:
- 상위노출: 검색 의도 충족도, 제목·도입부 키워드 배치, D.I.A.+ (경험·정보의 구체성), 문서 구조, 신뢰 요소, 시의성.
- 홈판: 썸네일과 제목의 클릭 유도력(작은 카드에서 읽히는가), 넓은 독자층이 공감할 화제성, 첫 화면 체류 장치.
- 비즈니스·경제 글은 숫자·기준일·출처·'그래서 나에게 무슨 영향인가'가 특히 중요합니다.
- 블로그 지수(C-Rank)처럼 글 밖에서만 확인 가능한 요인은 추정이라고 밝히고, 글 안에서 확인되는 요인을 우선하세요.
- 썸네일 이미지가 주어지지 않으면 thumbnail.seen=false로 두고 추정하지 마세요.
"""


def fetch_image(url: str, timeout: float = 10.0) -> tuple[str, bytes] | None:
    """썸네일 이미지를 받아온다. 실패하면 None."""
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://blog.naver.com/"}, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return None
    media_type = r.headers.get("Content-Type", "").split(";")[0].strip()
    if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return None
    return media_type, r.content


def build_content(post: BlogPost, stats: PostStats, keyword: str, source: str, rank: int | None,
                  image: tuple[str, bytes] | None, note: str = "") -> list[dict]:
    content: list[dict] = []
    if image:
        media_type, data = image
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()},
        })
        content.append({"type": "text", "text": "↑ 이 글의 대표 썸네일 이미지입니다."})
    s = asdict(stats)
    for k in ("first_paragraph", "headings", "tags", "url", "title"):
        s.pop(k, None)
    body = "\n".join(
        (f"[소제목] {b.text}" if b.kind == "heading" else "[사진]" if b.kind == "image" else b.text)
        for b in post.blocks if b.kind in ("text", "heading", "image", "quote")
    )
    content.append({"type": "text", "text": "\n\n".join([
        f"키워드: {keyword}",
        f"노출 위치: {source}" + (f" (순위 {rank}위)" if rank else ""),
        f"URL: {post.url}",
        f"제목: {post.title}",
        f"정량 지표: {s}",
        f"태그: {' '.join('#' + t for t in post.tags)}",
        f"굵게 강조된 문구: {post.bold_phrases[:20]}",
        *( [f"사용자 메모: {note}"] if note else [] ),
        f"본문:\n{body}",
    ])})
    return content


def analyze_reference(post: BlogPost, stats: PostStats, keyword: str, source: str, rank: int | None = None,
                      note: str = "", with_thumbnail: bool = True, client: anthropic.Anthropic | None = None,
                      effort: str = "high") -> PostInsight:
    image = fetch_image(post.thumbnail_url) if with_thumbnail else None
    content = build_content(post, stats, keyword, source, rank, image, note)
    insight, _ = llm.parse(PostInsight, SYSTEM, [{"role": "user", "content": content}], effort=effort, client=client)
    return insight
