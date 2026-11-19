"""post.md 자연스러움·독창성 점검: AI 티 나는 습관과 레퍼런스와 겹치는 문장을 찾아 보고한다.

사용: python3 tools/natural_check.py "output/<키워드>"
기준은 사람이 쓴 블로그 글과 비교해 눈에 띄는 패턴이다. 점수가 아니라 고칠 곳 목록으로 본다.
"""

import collections
import json
import pathlib
import re
import statistics
import sys

# 정형화된 AI·보고서 말투 (블로그 사람 글에서는 드묾)
CLICHES = [
    "알아보겠습니다", "살펴보겠습니다", "정리해 보겠습니다", "결론적으로", "요약하자면", "종합하면",
    "주목할 만합니다", "주목할 필요", "시사하는 바", "중요한 점은", "핵심은", "다양한", "효과적으로",
    "에 대해 자세히", "도움이 되셨기를", "도움이 되길", "이번 포스팅에서는", "오늘은 ~", "한눈에",
    "무엇보다", "뿐만 아니라", "그렇다면", "과연", "~라고 할 수 있습니다", "라고 할 수 있습니다",
    "것으로 보입니다", "꼼꼼히", "확인해 보시기 바랍니다", "참고하시기 바랍니다",
]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def body_lines(md: str) -> list[str]:
    body = md.split("---\n", 1)[1]
    body = re.split(r"^#\S", body, flags=re.M)[0]
    out = []
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith(("![", "|", "---", "[직접 입력", "[사진")):
            continue
        out.append(ln.lstrip("> -").replace("**", ""))
    return out


def sentences(lines: list[str]) -> list[str]:
    s = []
    for ln in lines:
        s += [x.strip() for x in re.split(r"(?<=[.!?])\s+", ln) if len(x.strip()) > 4]
    return s


def ending(s: str) -> str:
    s = re.sub(r"[\s.!?)\]\"'”’]+$", "", s)
    return s[-3:]


def ngrams(t: str, n: int) -> set[str]:
    t = re.sub(r"\s+", "", t)
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def main(folder: str) -> None:
    f = pathlib.Path(folder)
    md = (f / "post.md").read_text()
    lines = body_lines(md)
    sents = sentences(lines)
    text = " ".join(lines)
    issues = []

    # 1) 문장 끝 반복
    ends = [ending(s) for s in sents]
    formal = sum(e.endswith(("니다", "니까")) for e in ends) / max(1, len(ends))
    streak, best, prev = 1, 1, None
    for e in ends:
        streak = streak + 1 if e == prev else 1
        best, prev = max(best, streak), e
    top = collections.Counter(ends).most_common(3)
    print(f"문장 {len(sents)}개 · '-니다' 끝 {formal:.0%} · 같은 어미 최장 연속 {best} · 많이 쓴 끝 {top}")
    if formal > 0.8:
        issues.append(f"'-니다'로 끝나는 문장이 {formal:.0%}: '-요', '-죠', 명사형·질문으로 섞기")
    if best >= 4:
        issues.append(f"같은 어미가 {best}문장 연속: 리듬 바꾸기")

    # 2) 문장 길이가 너무 고른지
    lens = [len(s) for s in sents]
    cv = statistics.pstdev(lens) / statistics.mean(lens) if lens else 0
    print(f"문장 길이 평균 {statistics.mean(lens):.0f}자 · 변동계수 {cv:.2f}")
    if cv < 0.4:
        issues.append(f"문장 길이가 너무 고름(변동계수 {cv:.2f}): 아주 짧은 문장·긴 문장 섞기")

    # 3) 상투어
    hits = [(c, text.count(c)) for c in CLICHES if c.replace("~", "") and c in text]
    if hits:
        issues.append("AI·보고서 말투: " + ", ".join(f"{c}×{n}" for c, n in hits))

    # 4) 굵게·이모지·서수 나열
    bold = md.split("---\n", 1)[1].count("**") // 2
    per_k = bold / max(1, len(text)) * 1000
    if per_k > 6:
        issues.append(f"굵게 {bold}곳(1,000자당 {per_k:.1f}): 섹션당 1곳 이하로")
    if EMOJI.search(text):
        issues.append("본문 이모지: 사람 글처럼 쓰려면 빼거나 1~2개만")
    if re.search(r"첫째.*둘째.*셋째", text):
        issues.append("'첫째·둘째·셋째' 나열: 이야기 흐름이나 실제 사례로 바꾸기")
    starts = collections.Counter(s[:4] for s in sents)
    rep = [k for k, v in starts.items() if v >= 3]
    if rep:
        issues.append(f"같은 말로 시작하는 문장 반복: {rep}")

    # 5) 레퍼런스와 겹침 (제목·소제목·도입부 기준, 10자 이상 연속 일치)
    refs = f / "refs.json"
    if refs.exists():
        r = json.loads(refs.read_text())
        pool = []
        for p in r.get("search", []) + r.get("home", []):
            pool += [p.get("title", "")] + p.get("headings", []) + [p.get("intro", "")]
        ref_grams = set().union(*(ngrams(x, 10) for x in pool if x)) if pool else set()
        title = md.splitlines()[0].lstrip("# ")
        dup = [(s, sorted(ngrams(s, 10) & ref_grams)[0]) for s in [title] + sents if ngrams(s, 10) & ref_grams]
        if dup:
            issues.append("레퍼런스와 10자 이상 겹침(사실 용어면 그대로 둬도 됨): "
                          + " / ".join(f"「{g}」 ← {d[:30]}" for d, g in dup[:6]))
        else:
            print("레퍼런스와 10자 이상 겹치는 문장 없음")

    print("\n고칠 곳" if issues else "\n고칠 곳 없음")
    for i in issues:
        print("-", i)


if __name__ == "__main__":
    main(sys.argv[1])
