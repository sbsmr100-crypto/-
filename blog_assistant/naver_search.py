"""네이버 검색 API(블로그)로 키워드별 상위 노출 글 목록을 가져온다.

API 키 발급: https://developers.naver.com/apps  (검색 API 사용 신청)
환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 를 사용한다.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

import requests

SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SearchResult:
    rank: int
    title: str
    link: str
    description: str
    blogger_name: str
    blogger_link: str
    post_date: str  # YYYYMMDD

    @property
    def is_naver_blog(self) -> bool:
        return "blog.naver.com" in self.link


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def search_blog(
    keyword: str,
    display: int = 10,
    sort: str = "sim",
    client_id: str | None = None,
    client_secret: str | None = None,
    timeout: float = 10.0,
) -> list[SearchResult]:
    """키워드로 블로그 검색. sort='sim'(정확도순=상위노출 순서에 가장 가까움) 또는 'date'."""
    client_id = client_id or os.environ.get("NAVER_CLIENT_ID")
    client_secret = client_secret or os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 필요합니다. "
            "(https://developers.naver.com/apps 에서 검색 API 신청)"
        )

    resp = requests.get(
        SEARCH_URL,
        params={"query": keyword, "display": max(1, min(display, 100)), "sort": sort},
        headers={"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret},
        timeout=timeout,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [
        SearchResult(
            rank=i + 1,
            title=_clean(item.get("title", "")),
            link=item.get("link", ""),
            description=_clean(item.get("description", "")),
            blogger_name=item.get("bloggername", ""),
            blogger_link=item.get("bloggerlink", ""),
            post_date=item.get("postdate", ""),
        )
        for i, item in enumerate(items)
    ]
