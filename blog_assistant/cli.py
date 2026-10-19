"""터미널 사용법

레퍼런스 쌓기 (크리에이터 어드바이저에서 찾은 글):
    python -m blog_assistant.cli ref add URL [URL...] -k "금리 인하" -s 상위노출 --rank 1
    python -m blog_assistant.cli ref add URL -k "금리 인하" -s 홈판 --note "경제 주제판 1위"
    python -m blog_assistant.cli ref import refs.csv          # 열: keyword,source,rank,url,note
    python -m blog_assistant.cli ref paste -k "금리 인하" -s 홈판 --title "..." --body-file body.txt
    python -m blog_assistant.cli ref list [-k 키워드]

원고 + 썸네일:
    python -m blog_assistant.cli write "금리 인하 대출" --notes "변동금리 대출 갈아탈지 고민하는 직장인 관점" -o out
    → out.md (원고), out_thumbnails.html (썸네일 시안 3개)

검색 상위글 지표만 빠르게 보기 (네이버 검색 API 필요):
    python -m blog_assistant.cli analyze "금리 인하" --top 10
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .analyzer import blueprint_to_brief
from .pipeline import add_reference, analyze_keyword
from .references import SOURCES, ReferenceStore
from .scraper import post_from_text


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def cmd_ref_add(a) -> int:
    ok = 0
    for i, url in enumerate(a.urls):
        rank = a.rank + i if a.rank else None
        try:
            path = add_reference(a.keyword, a.source, url=url, rank=rank, note=a.note, with_insight=not a.no_insight)
            _err(f"저장: {path}")
            ok += 1
        except Exception as e:
            _err(f"[실패] {url}: {e}")
    return 0 if ok else 1


def cmd_ref_import(a) -> int:
    ok = 0
    with open(a.csv, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                path = add_reference(
                    row["keyword"].strip(), row.get("source", "상위노출").strip() or "상위노출", url=row["url"].strip(),
                    rank=int(row["rank"]) if (row.get("rank") or "").strip() else None,
                    note=(row.get("note") or "").strip(), with_insight=not a.no_insight,
                )
                _err(f"저장: {path}")
                ok += 1
            except Exception as e:
                _err(f"[실패] {row.get('url')}: {e}")
    return 0 if ok else 1


def cmd_ref_paste(a) -> int:
    body = Path(a.body_file).read_text(encoding="utf-8") if a.body_file else sys.stdin.read()
    post = post_from_text(a.title, body, url=a.url or "", image_count=a.images)
    path = add_reference(a.keyword, a.source, post=post, rank=a.rank, note=a.note, with_insight=not a.no_insight)
    _err(f"저장: {path}")
    return 0


def cmd_ref_list(a) -> int:
    store = ReferenceStore()
    refs = store.related(a.keyword, limit=1000) if a.keyword else store.all()
    for r in refs:
        mark = "✓" if r.get("insight") else " "
        print(f"{mark} [{r['source']}] {r['keyword']:<14} {r.get('rank') or '-':>3}  {r['title'][:40]}  {r['url']}")
    _err(f"총 {len(refs)}개 (✓ = 노출 이유 분석 완료)")
    return 0


def cmd_write(a) -> int:
    from .thumbnail import render_page
    from .writer import WriteRequest, draft_to_markdown, plan_thumbnails, write_draft

    notes = Path(a.notes[1:]).read_text(encoding="utf-8") if a.notes.startswith("@") else a.notes
    refs = ReferenceStore().related(a.keyword, limit=a.refs)
    _err(f"레퍼런스 {len(refs)}개 사용")
    blueprint = None
    if a.live_top:
        blueprint, collected = analyze_keyword(a.keyword, top_n=a.live_top, on_progress=_err)
        for url, err in collected.errors:
            _err(f"[건너뜀] {url}: {err}")

    _err("원고 작성 중…")
    draft = write_draft(WriteRequest(a.keyword, notes, a.extra, a.limit), refs, blueprint, effort=a.effort)
    md = draft_to_markdown(draft)
    print(md)
    _err("썸네일 안 만드는 중…")
    plan = plan_thumbnails(a.keyword, draft, refs)
    for i, idea in enumerate(plan.ideas, 1):
        print(f"\n[썸네일 {i}] {idea.concept}\n  메인: {idea.main_copy} (강조: {idea.emphasis})\n  보조: {idea.sub_copy}\n"
              f"  배치 {idea.layout} / 배경 {idea.background} / 글자 {idea.text_color} / 강조 {idea.accent_color}\n"
              f"  이미지: {idea.visual}\n  근거: {idea.rationale}")
    print("\n제작 팁:", *(f"- {t}" for t in plan.tips), sep="\n")
    if a.output:
        Path(a.output + ".md").write_text(md, encoding="utf-8")
        Path(a.output + "_thumbnails.html").write_text(render_page(plan.ideas, draft.title), encoding="utf-8")
        _err(f"저장: {a.output}.md, {a.output}_thumbnails.html")
    return 0


def cmd_analyze(a) -> int:
    blueprint, collected = analyze_keyword(a.keyword, top_n=a.top, on_progress=_err)
    for url, err in collected.errors:
        _err(f"[건너뜀] {url}: {err}")
    if blueprint is None:
        _err("분석할 글을 수집하지 못했습니다.")
        return 1
    print(blueprint_to_brief(blueprint))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="네이버 블로그(비즈니스·경제) 레퍼런스 분석 + 원고·썸네일 비서")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ref = sub.add_parser("ref", help="레퍼런스 관리").add_subparsers(dest="ref_cmd", required=True)

    def ref_common(p, need_kw=True):
        p.add_argument("-k", "--keyword", required=need_kw)
        p.add_argument("-s", "--source", choices=SOURCES, default="상위노출")
        p.add_argument("--rank", type=int, help="순위 (여러 URL이면 순서대로 +1)")
        p.add_argument("--note", default="", help="내 메모 (예: 경제 주제판 1위, 조회수 급등)")
        p.add_argument("--no-insight", action="store_true", help="Claude 분석 없이 지표만 저장")

    p = ref.add_parser("add", help="URL로 추가")
    p.add_argument("urls", nargs="+")
    ref_common(p)
    p.set_defaults(fn=cmd_ref_add)

    p = ref.add_parser("import", help="CSV로 한꺼번에 추가 (keyword,source,rank,url,note)")
    p.add_argument("csv")
    p.add_argument("--no-insight", action="store_true")
    p.set_defaults(fn=cmd_ref_import)

    p = ref.add_parser("paste", help="복사한 제목/본문으로 추가 (네이버 접속이 안 될 때)")
    ref_common(p)
    p.add_argument("--title", required=True)
    p.add_argument("--body-file", help="본문 텍스트 파일 (없으면 표준입력)")
    p.add_argument("--url", default="")
    p.add_argument("--images", type=int, default=0, help="본문 이미지 수")
    p.set_defaults(fn=cmd_ref_paste)

    p = ref.add_parser("list", help="레퍼런스 목록")
    p.add_argument("-k", "--keyword")
    p.set_defaults(fn=cmd_ref_list)

    p = sub.add_parser("write", help="원고(2,000자 이내) + 썸네일 안")
    p.add_argument("keyword")
    p.add_argument("--notes", default="", help="내 경험·관점 메모 (또는 @파일)")
    p.add_argument("--extra", default="", help="추가 요청")
    p.add_argument("--limit", type=int, default=2000, help="본문 최대 글자 수(공백 포함)")
    p.add_argument("--refs", type=int, default=12, help="참고할 레퍼런스 수")
    p.add_argument("--live-top", type=int, default=0, help="검색 상위 N개를 실시간으로 추가 분석 (네이버 API 필요)")
    p.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("-o", "--output", help="저장 경로(확장자 없이)")
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("analyze", help="검색 상위글 지표 분석")
    p.add_argument("keyword")
    p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_analyze)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
