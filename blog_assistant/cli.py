"""터미널 사용법:

    python -m blog_assistant.cli "제주도 맛집" --top 10 --notes "3월에 다녀옴, 1인 2만원" -o post.md
    python -m blog_assistant.cli "제주도 맛집" --analyze-only
    python -m blog_assistant.cli "제주도 맛집" --no-search --url https://blog.naver.com/xxx/123 --url ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import blueprint_to_brief
from .pipeline import analyze_keyword
from .writer import WriteRequest, stream_post


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="네이버 블로그 상위노출 분석 + 원고 작성 비서")
    ap.add_argument("keyword", help="메인 키워드")
    ap.add_argument("--top", type=int, default=10, help="분석할 검색 상위 글 수 (기본 10)")
    ap.add_argument("--url", action="append", default=[], help="추가 분석할 글 URL (홈판 인기글 등, 여러 번 사용 가능)")
    ap.add_argument("--urls-file", help="추가 분석할 URL 목록 파일 (한 줄에 하나)")
    ap.add_argument("--no-search", action="store_true", help="검색 API를 쓰지 않고 --url 글만 분석")
    ap.add_argument("--analyze-only", action="store_true", help="분석 결과만 출력하고 글은 쓰지 않음")
    ap.add_argument("--type", default="정보+후기형", help="글 유형 (예: 내돈내산 후기, 정보성, 맛집 리뷰, 제품 비교)")
    ap.add_argument("--tone", default="친근한 존댓말(~요체)", help="말투")
    ap.add_argument("--notes", default="", help="내 실제 경험/정보 메모 (또는 @파일경로)")
    ap.add_argument("--extra", default="", help="추가 요청 사항")
    ap.add_argument("--sponsored", action="store_true", help="협찬/광고 글")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("-o", "--output", help="원고 저장 경로 (.md)")
    ap.add_argument("--save-analysis", help="분석 결과 JSON 저장 경로")
    args = ap.parse_args(argv)

    extra_urls = list(args.url)
    if args.urls_file:
        extra_urls += [l.strip() for l in Path(args.urls_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    notes = args.notes
    if notes.startswith("@"):
        notes = Path(notes[1:]).read_text(encoding="utf-8")

    blueprint, collected = analyze_keyword(
        args.keyword,
        top_n=args.top,
        extra_urls=extra_urls,
        use_search=not args.no_search,
        on_progress=lambda m: print(m, file=sys.stderr),
    )
    for url, err in collected.errors:
        print(f"[건너뜀] {url}: {err}", file=sys.stderr)

    if blueprint is None:
        print("분석할 글을 하나도 수집하지 못했습니다. 일반 상위노출 기준으로 작성합니다.", file=sys.stderr)
        if args.analyze_only:
            return 1
    else:
        print(blueprint_to_brief(blueprint), file=sys.stderr if not args.analyze_only else sys.stdout)
    if args.save_analysis and blueprint is not None:
        Path(args.save_analysis).write_text(
            json.dumps(blueprint.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.analyze_only:
        return 0

    print("\n=== 원고 작성 중 ===\n", file=sys.stderr)
    req = WriteRequest(args.keyword, args.type, args.tone, notes, args.extra, args.sponsored)
    chunks = []
    for chunk in stream_post(req, blueprint, effort=args.effort):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    print()
    if args.output:
        Path(args.output).write_text("".join(chunks), encoding="utf-8")
        print(f"\n저장됨: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
