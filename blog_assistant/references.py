"""분석한 레퍼런스 글을 references/ 폴더에 JSON으로 쌓고, 키워드별로 꺼내 쓴다.

남의 글 전문은 저장하지 않는다(지표·소제목·도입부 일부·분석 결과만). 다시 분석이 필요하면 URL로 재수집.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .analyzer import PostStats, tokenize
from .insights import PostInsight
from .scraper import BlogPost, parse_blog_url

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "references"
SOURCES = ("상위노출", "홈판")


def _ref_id(url: str, title: str) -> str:
    ids = parse_blog_url(url) if url else None
    if ids:
        return f"{ids[0]}_{ids[1]}"
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", title)[:60] or datetime.now().strftime("manual_%Y%m%d%H%M%S")


class ReferenceStore:
    def __init__(self, root: Path | str = DEFAULT_DIR):
        self.root = Path(root)

    def add(self, post: BlogPost, stats: PostStats, keyword: str, source: str, rank: int | None = None,
            note: str = "", insight: PostInsight | None = None) -> Path:
        if source not in SOURCES:
            raise ValueError(f"source는 {SOURCES} 중 하나여야 합니다")
        self.root.mkdir(parents=True, exist_ok=True)
        s = asdict(stats)
        record = {
            "id": _ref_id(post.url, post.title),
            "keyword": keyword,
            "source": source,
            "rank": rank,
            "url": post.url,
            "title": post.title,
            "added_at": datetime.now().isoformat(timespec="seconds"),
            "note": note,
            "thumbnail_url": post.thumbnail_url,
            "tags": post.tags,
            "headings": post.headings,
            "intro": s.pop("first_paragraph", "")[:300],
            "stats": {k: v for k, v in s.items() if k not in ("url", "title", "tags", "headings")},
            "insight": insight.model_dump() if insight else None,
        }
        path = self.root / f"{record['id']}.json"
        if path.exists():  # 같은 글이 다른 키워드로도 노출되면 키워드를 합쳐 둔다
            old = json.loads(path.read_text(encoding="utf-8"))
            kws = old.get("also_keywords", [])
            if old["keyword"] != keyword and keyword not in kws:
                record["also_keywords"] = kws + [old["keyword"]]
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def all(self) -> list[dict]:
        if not self.root.exists():
            return []
        return sorted(
            (json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*.json")),
            key=lambda r: r.get("added_at", ""),
            reverse=True,
        )

    def related(self, keyword: str, limit: int = 12) -> list[dict]:
        """키워드가 같은 글 > 단어가 겹치는 글 > 나머지(같은 분야 일반 레퍼런스) 순."""
        want = set(tokenize(keyword))
        squashed = keyword.replace(" ", "")

        def score(r: dict) -> tuple:
            kws = [r["keyword"], *r.get("also_keywords", [])]
            exact = any(k.replace(" ", "") == squashed for k in kws)
            overlap = len(want & set(tokenize(" ".join(kws) + " " + r.get("title", ""))))
            return (exact, overlap, r.get("insight") is not None, r.get("added_at", ""))

        return sorted(self.all(), key=score, reverse=True)[:limit]


def digest(refs: list[dict], max_chars: int = 12000) -> str:
    """레퍼런스 분석 결과를 프롬프트용 요약 텍스트로."""
    out: list[str] = []
    for r in refs:
        ins = r.get("insight") or {}
        st = r.get("stats", {})
        lines = [
            f"### [{r['source']}] {r['title']}  (키워드: {r['keyword']}{', ' + str(r['rank']) + '위' if r.get('rank') else ''})",
            f"- 지표: 글자수 {st.get('char_count')}, 이미지 {st.get('image_count')}, 소제목 {st.get('heading_count')}, "
            f"키워드 {st.get('keyword_count')}회, 제목패턴 {st.get('title_patterns')}",
        ]
        if r.get("headings"):
            lines.append(f"- 소제목: {' / '.join(r['headings'][:6])}")
        if ins:
            lines.append(f"- 노출 이유: {' · '.join(ins.get('why_exposed', [])[:4])}")
            th = ins.get("thumbnail") or {}
            if th.get("seen"):
                lines.append(
                    f"- 썸네일: 문구「{th.get('text_on_image')}」, 구도 {th.get('layout')}, 색 {th.get('colors')}, "
                    f"글꼴 {th.get('typography')} → {th.get('why_it_works')}"
                )
            lines.append(f"- 적용할 규칙: {' · '.join(ins.get('reusable_lessons', []))}")
        if r.get("note"):
            lines.append(f"- 내 메모: {r['note']}")
        block = "\n".join(lines)
        if sum(len(x) for x in out) + len(block) > max_chars:
            break
        out.append(block)
    return "\n\n".join(out)
