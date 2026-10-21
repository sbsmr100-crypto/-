"""키워드로 네이버를 직접 검색해 레퍼런스(검색 상위글 + 블로그 홈 주제판 노출글)를 수집·요약한다.

사용: python3 tools/naver_ref.py "키워드" [--top 10] [--dirs 33,31] [--pages 10]
결과: output/<키워드>/refs.json (글별 지표), output/<키워드>/refs.md (요약 리포트)

- 검색 상위: search.naver.com 블로그 탭 순위 그대로.
- 홈판: 블로그 홈 '주제별 보기'(section.blog.naver.com) 최신 노출 목록에서 키워드가 들어간 글.
  기본 주제 33=비즈니스·경제, 31=사회·정치 위주. 네이버 앱 홈피드는 개인화라 서버에서 볼 수 없어 이걸로 대신한다.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import pathlib
import re
import statistics
import subprocess
import sys
import time
import urllib.parse

from bs4 import BeautifulSoup

UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
UA_PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def get(url: str, ua: str = UA_MOBILE, ref: str = "https://m.blog.naver.com/") -> str:
    return subprocess.run(["curl", "-sS", "--compressed", "-A", ua, "-H", "Referer: " + ref, url],
                          capture_output=True, text=True).stdout


def _json(text: str):
    return json.loads(text[text.find("{"):])


def search_top(keyword: str, n: int) -> list[tuple[str, str]]:
    url = "https://search.naver.com/search.naver?ssc=tab.blog.all&query=" + urllib.parse.quote(keyword)
    s = get(url, UA_PC, "https://www.naver.com/")
    seen, out = set(), []
    for m in re.finditer(r'<a[^>]*href="(https://blog\.naver\.com/[\w-]+/\d+)"[^>]*>(.*?)</a>', s, re.S):
        title = html.unescape(re.sub("<[^>]+>", "", m.group(2))).replace("새 창 열림", "").strip()
        if len(title) > 8 and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append((m.group(1), title))
    return out[:n]


def home_feed(keyword: str, dirs: list[int], pages: int) -> list[dict]:
    tokens = [t for t in re.split(r"\s+", keyword) if t]
    hits = []
    for d in dirs:
        for p in range(1, pages + 1):
            try:
                posts = _json(get(f"https://section.blog.naver.com/ajax/DirectoryPostList.naver?directorySeq={d}&pageNo={p}",
                                  UA_PC, "https://section.blog.naver.com/"))["result"]["postList"]
            except Exception:
                break
            for x in posts:
                text = re.sub(r"\s", "", (x.get("title") or "") + (x.get("briefContents") or ""))
                if all(t in text for t in tokens):
                    hits.append({"url": x["postUrl"], "title": x["title"], "dir": d, "page": p,
                                 "sympathy": int(x.get("sympathyCnt") or 0), "comments": int(x.get("commentCnt") or 0)})
            time.sleep(0.3)
    return hits


def analyze_post(url: str, keyword: str) -> dict:
    bid, log = re.search(r"naver\.com/([\w-]+)/(\d+)", url).groups()
    h = get(f"https://m.blog.naver.com/PostView.naver?blogId={bid}&logNo={log}")
    s = BeautifulSoup(h, "html.parser")
    prop = s.find(id="_post_property")
    main = s.select_one(".se-main-container")
    comps = collections.Counter()
    for c in (main.select(".se-component") if main else []):
        for cl in c.get("class", []):
            if cl.startswith("se-") and not cl.startswith("se-l-") and cl != "se-component":
                comps[cl.removeprefix("se-")] += 1
    text = main.get_text("\n", strip=True) if main else ""
    paras = [p.get_text(strip=True) for p in main.select(".se-text-paragraph")] if main else []
    paras = [p for p in paras if p]
    title_el = s.select_one(".se-title-text")
    date_el = s.select_one(".blog_date")
    kw = keyword.replace(" ", "")
    tag = get(f"https://blog.naver.com/BlogTagListInfo.naver?blogId={bid}&logNoList={log}&logType=mobile")
    tm = re.search(r'"tagName":"([^"]*)"', tag)
    likes = re.search(r'"count":(\d+)', get(
        f"https://blog.like.naver.com/v1/search/contents?suppress_response_codes=true&q=BLOG%5B{bid}_{log}%5D&isDuplication=true&cssIds=BASIC_MOBILE"))
    try:
        bi = _json(get(f"https://m.blog.naver.com/rego/BlogInfo.naver?blogId={bid}", ref=f"https://m.blog.naver.com/{bid}"))["result"]
    except Exception:
        bi = {}
    try:
        items = _json(get(f"https://m.blog.naver.com/api/blogs/{bid}/post-list?categoryNo=0&itemCount=30&page=1",
                          ref=f"https://m.blog.naver.com/{bid}"))["result"]["items"]
    except Exception:
        items = []
    ds = [dt.datetime.fromtimestamp(int(i["addDate"]) / 1000) for i in items]
    span = (ds[0] - ds[-1]).total_seconds() / 86400 if len(ds) > 1 else 0
    cats = collections.Counter(i.get("categoryName") for i in items)
    return {
        "url": url, "blogId": bid,
        "title": title_el.get_text(strip=True) if title_el else "",
        "date": date_el.get_text(" ", strip=True) if date_el else "",
        "mate": "네이버 메이트" in (date_el.get_text() if date_el else ""),
        "feedmaker": any("피드메이커" in (c or "") for c in cats),
        "chars": len(re.sub(r"\s", "", text)),
        "paras": len(paras), "avg_para": round(sum(map(len, paras)) / max(1, len(paras)), 1),
        "images": comps.get("image", 0) + comps.get("imageStrip", 0),
        "quotes": comps.get("quotation", 0), "tables": comps.get("table", 0),
        "videos": comps.get("video", 0) + comps.get("oembed", 0), "links": comps.get("oglink", 0),
        "headings": [q.get_text(" ", strip=True)[:60] for q in main.select(".se-quotation, .se-sectionTitle")][:8] if main else [],
        "kw_count": re.sub(r"\s", "", text).count(kw),
        "kw_in_title_front": (title_el.get_text(strip=True).replace(" ", "") if title_el else "").startswith(kw),
        "tags": urllib.parse.unquote(tm.group(1)).split(",") if tm and tm.group(1) else [],
        "likes": int(likes.group(1)) if likes else None,
        "comments": int(prop.get("commentcount") or 0) if prop else None,
        "intro": " / ".join(paras[:4])[:300],
        "blog": {"name": bi.get("blogName"), "dir": bi.get("blogDirectoryName"), "subscribers": bi.get("subscriberCount"),
                 "day_visitors": bi.get("dayVisitorCount"), "total_visitors": bi.get("totalVisitorCount"),
                 "official": bi.get("officialBlog")},
        "posting": {"per_day": round(len(items) / span, 1) if span else None,
                    "top_categories": cats.most_common(3),
                    "avg_likes_recent": round(statistics.mean(int(i.get("sympathyCnt") or 0) for i in items), 1) if items else None},
    }


def summarize(keyword: str, search: list[dict], home: list[dict]) -> str:
    def med(rows, k):
        v = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        return int(statistics.median(v)) if v else "-"

    allp = search + [h for h in home if h.get("chars") is not None]
    lines = [f"# 레퍼런스: {keyword}", f"수집: {dt.datetime.now():%Y-%m-%d %H:%M} · 검색 상위 {len(search)}개 · 블로그 홈 주제판 노출 {len(home)}개", ""]
    if allp:
        lines += ["## 공통 지표 (중앙값)",
                  f"- 글자수(공백 제외) {med(allp, 'chars')} · 이미지 {med(allp, 'images')} · 인용구 소제목 {med(allp, 'quotes')} · 표 {med(allp, 'tables')} · 평균 문단 길이 {med(allp, 'avg_para')}자",
                  f"- 본문 키워드 반복 {med(allp, 'kw_count')}회 · 제목 맨 앞 키워드 {sum(p['kw_in_title_front'] for p in allp)}/{len(allp)}",
                  f"- 네이버 메이트 {sum(p['mate'] for p in allp)}/{len(allp)} · 피드메이커 {sum(p['feedmaker'] for p in allp)}/{len(allp)} · 공식 블로그 {sum(bool(p['blog']['official']) for p in allp)}/{len(allp)}",
                  ""]
    for name, rows in (("검색 상위", search), ("블로그 홈 주제판 노출", home)):
        lines.append(f"## {name}")
        if not rows:
            lines += ["(없음)", ""]
            continue
        lines += ["| # | 제목 | 블로그(이웃/일방문) | 글자 | 이미지 | 소제목 | 공감·댓글 | 배지 |", "|---|---|---|---|---|---|---|---|"]
        for i, p in enumerate(rows, 1):
            if p.get("chars") is None:
                continue
            b = p["blog"]
            badge = " ".join(x for x, ok in (("메이트", p["mate"]), ("피드메이커", p["feedmaker"]), ("공식", b["official"])) if ok)
            lines.append(f"| {i} | [{p['title'][:40]}]({p['url']}) | {b['name']} ({b['subscribers']}/{b['day_visitors']}) | {p['chars']} | {p['images']} | {p['quotes']} | {p['likes']}·{p['comments']} | {badge} |")
        lines.append("")
        for i, p in enumerate(rows, 1):
            if p.get("chars") is None:
                continue
            lines += [f"**{i}. {p['title']}** ({p['date']})",
                      f"- 소제목: {' | '.join(p['headings']) or '-'}",
                      f"- 도입: {p['intro']}",
                      f"- 태그: {', '.join(p['tags'][:12]) or '-'} · 키워드 {p['kw_count']}회 · 발행 {p['posting']['per_day']}개/일 · 최근 카테고리 {p['posting']['top_categories']}",
                      ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--dirs", default="33,31")
    ap.add_argument("--pages", type=int, default=10)
    a = ap.parse_args()
    out = ROOT / "output" / a.keyword
    out.mkdir(parents=True, exist_ok=True)

    search = []
    for url, _ in search_top(a.keyword, a.top):
        try:
            search.append(analyze_post(url, a.keyword))
        except Exception as e:  # 삭제·비공개 글은 건너뜀
            print("skip", url, e, file=sys.stderr)
        time.sleep(0.5)
    home = []
    for h in home_feed(a.keyword, [int(d) for d in a.dirs.split(",")], a.pages):
        try:
            home.append({**analyze_post(h["url"], a.keyword), "home_page": h["page"], "home_dir": h["dir"]})
        except Exception as e:
            print("skip", h["url"], e, file=sys.stderr)
        time.sleep(0.5)

    (out / "refs.json").write_text(json.dumps({"keyword": a.keyword, "search": search, "home": home}, ensure_ascii=False, indent=1))
    (out / "refs.md").write_text(summarize(a.keyword, search, home))
    print(out / "refs.md", f"(검색 {len(search)}, 홈 {len(home)})")


if __name__ == "__main__":
    main()
