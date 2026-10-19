"""키워드 → 상위노출 글 수집 (+ 홈판 글 URL) → 분석 설계도."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .analyzer import Blueprint, build_blueprint
from .naver_search import search_blog
from .scraper import BlogPost, fetch_post, parse_blog_url


@dataclass
class CollectResult:
    posts: list[BlogPost] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, 오류 메시지)


def collect_posts(
    keyword: str,
    top_n: int = 10,
    extra_urls: list[str] | None = None,
    use_search: bool = True,
    delay: float = 0.5,
    on_progress: Callable[[str], None] | None = None,
) -> CollectResult:
    """검색 상위 top_n개(네이버 블로그만) + 직접 넣은 URL(홈판 인기글 등)을 수집한다."""
    log = on_progress or (lambda _msg: None)
    urls: list[str] = []
    if use_search:
        log(f"'{keyword}' 네이버 블로그 검색 중…")
        # 외부 블로그가 섞여 있을 수 있어 넉넉히 받아서 네이버 블로그만 남긴다
        results = [r for r in search_blog(keyword, display=min(100, top_n * 3)) if r.is_naver_blog]
        urls.extend(r.link for r in results[:top_n])
    for u in extra_urls or []:
        u = u.strip()
        if u and u not in urls:
            urls.append(u)

    out = CollectResult()
    seen: set[tuple[str, str]] = set()
    for i, url in enumerate(urls, 1):
        ids = parse_blog_url(url)
        if ids is None:
            out.errors.append((url, "네이버 블로그 주소가 아닙니다"))
            continue
        if ids in seen:
            continue
        seen.add(ids)
        log(f"[{i}/{len(urls)}] 본문 수집: {url}")
        try:
            post = fetch_post(url)
        except Exception as e:  # 네트워크/파싱 실패는 건너뛰고 기록만
            out.errors.append((url, str(e)))
            continue
        if not post.blocks:
            out.errors.append((url, "본문을 찾지 못했습니다(비공개/삭제 글일 수 있음)"))
            continue
        out.posts.append(post)
        if delay:
            time.sleep(delay)
    return out


def analyze_keyword(keyword: str, **kwargs) -> tuple[Blueprint | None, CollectResult]:
    """수집에 하나도 성공하지 못하면 설계도는 None (기본 기준으로 글을 쓰게 된다)."""
    collected = collect_posts(keyword, **kwargs)
    blueprint = build_blueprint(collected.posts, keyword) if collected.posts else None
    return blueprint, collected
