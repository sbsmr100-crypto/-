"""상위노출/홈판 글들의 공통 패턴(분량, 이미지, 키워드 반복, 제목 패턴 등)을 수치로 뽑는다.

LLM 없이 계산되는 부분이라 결과가 매번 같고, 글쓰기 단계에서 '설계도'로 쓰인다.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field

from .scraper import BlogPost

_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# 흔한 조사/어미. 긴 것부터 떼어낸다.
_JOSA = sorted(
    "은 는 이 가 을 를 의 에 에서 에게 으로 로 와 과 도 만 까지 부터 이나 나 이랑 랑 하고 처럼 보다 "
    "이에요 예요 입니다 이다 했어요 해요 했는데 인데 에는 으로는 로는 이라 라 이라고 라고 같은".split(),
    key=len,
    reverse=True,
)
_STOPWORDS = set(
    """그리고 그래서 하지만 그런데 정말 진짜 너무 아주 조금 많이 이번 오늘 저는 제가 우리 여기 거기 이렇게 그렇게
    있어요 있습니다 없어요 했어요 합니다 해서 하는 하고 했던 같아요 같은 있는 없는 이런 그런 저런 때문 경우 정도
    사진 포스팅 블로그 이웃 감사 안녕하세요 여러분 다들 위해 통해 대한 대해 가장 바로 다시 함께 이제 이미 먼저""".split()
)
TITLE_HOOK_WORDS = [
    "후기", "추천", "방법", "총정리", "비교", "가격", "꿀팁", "정리", "내돈내산", "솔직", "리뷰", "best", "TOP",
    "주의", "필수", "가이드", "장단점", "비용", "위치", "메뉴", "효과", "차이", "순위",
]


def tokenize(text: str) -> list[str]:
    out = []
    for tok in _TOKEN_RE.findall(text):
        for j in _JOSA:
            if len(tok) > len(j) + 1 and tok.endswith(j):
                tok = tok[: -len(j)]
                break
        if len(tok) >= 2 and tok not in _STOPWORDS and not tok.isdigit():
            out.append(tok)
    return out


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def count_keyword(text: str, keyword: str) -> int:
    """띄어쓰기 차이는 무시하고 키워드 등장 횟수를 센다."""
    k = _squash(keyword)
    return _squash(text).count(k) if k else 0


@dataclass
class PostStats:
    url: str
    title: str
    title_len: int
    char_count: int  # 공백 제외 글자 수
    paragraph_count: int
    avg_paragraph_len: float
    image_count: int
    video_count: int
    heading_count: int
    sticker_count: int
    quote_count: int
    link_count: int
    map_count: int
    keyword_in_title: bool
    keyword_title_position: str  # front | middle | back | none
    keyword_count: int
    keyword_density: float  # 1000자당 등장 횟수
    keyword_in_first_paragraph: bool
    title_patterns: list[str]
    structure: str  # 예: "텍스트3 → 이미지2 → 소제목 → ..."
    tags: list[str]
    first_paragraph: str
    headings: list[str]


def _title_patterns(title: str) -> list[str]:
    p = []
    if re.search(r"\d", title):
        p.append("숫자 포함")
    if re.search(r"[\[\]【】()]", title):
        p.append("괄호/대괄호")
    if "?" in title:
        p.append("질문형")
    if "!" in title:
        p.append("느낌표")
    if _EMOJI_RE.search(title):
        p.append("이모지")
    if "," in title or "|" in title or "/" in title:
        p.append("구분자(, | /)")
    for w in TITLE_HOOK_WORDS:
        if w.lower() in title.lower():
            p.append(f"'{w}'")
    return p


def _structure(post: BlogPost) -> str:
    names = {
        "text": "텍스트", "heading": "소제목", "image": "이미지", "video": "동영상", "sticker": "스티커",
        "quote": "인용구", "link": "링크", "map": "지도", "table": "표", "divider": "구분선",
    }
    runs: list[list] = []
    for b in post.blocks:
        if runs and runs[-1][0] == b.kind:
            runs[-1][1] += 1
        else:
            runs.append([b.kind, 1])
    return " → ".join(f"{names.get(k, k)}{n if n > 1 else ''}" for k, n in runs)


def analyze_post(post: BlogPost, keyword: str) -> PostStats:
    body = post.body_text
    chars = len(re.sub(r"\s", "", body))
    paras = post.paragraphs
    kc = count_keyword(body, keyword)

    tpos = "none"
    k, t = _squash(keyword), _squash(post.title)
    if k and k in t:
        idx = t.index(k) / max(1, len(t))
        tpos = "front" if idx < 0.34 else ("middle" if idx < 0.67 else "back")

    return PostStats(
        url=post.url,
        title=post.title,
        title_len=len(post.title),
        char_count=chars,
        paragraph_count=len(paras),
        avg_paragraph_len=round(statistics.mean(len(p) for p in paras), 1) if paras else 0.0,
        image_count=post.count("image"),
        video_count=post.count("video"),
        heading_count=post.count("heading"),
        sticker_count=post.count("sticker"),
        quote_count=post.count("quote"),
        link_count=post.count("link"),
        map_count=post.count("map"),
        keyword_in_title=tpos != "none",
        keyword_title_position=tpos,
        keyword_count=kc,
        keyword_density=round(kc / chars * 1000, 2) if chars else 0.0,
        keyword_in_first_paragraph=bool(paras) and count_keyword(" ".join(paras[:2]), keyword) > 0,
        title_patterns=_title_patterns(post.title),
        structure=_structure(post),
        tags=post.tags,
        first_paragraph=paras[0] if paras else "",
        headings=post.headings,
    )


@dataclass
class Blueprint:
    """여러 글을 종합한 '이 키워드에서 먹히는 글'의 설계도."""

    keyword: str
    sample_size: int
    target_chars: int
    chars_range: tuple[int, int]
    target_images: int
    images_range: tuple[int, int]
    target_headings: int
    target_keyword_count: int
    keyword_count_range: tuple[int, int]
    avg_paragraph_len: float
    title_len: int
    keyword_in_title_ratio: float
    keyword_front_ratio: float
    keyword_in_intro_ratio: float
    video_ratio: float
    map_ratio: float
    title_patterns: list[tuple[str, int]]
    related_keywords: list[tuple[str, int]]
    common_tags: list[tuple[str, int]]
    example_titles: list[str]
    example_headings: list[str]
    example_intros: list[str]
    example_structures: list[str]
    posts: list[PostStats] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _median_int(values: list[float]) -> int:
    return int(round(statistics.median(values))) if values else 0


def build_blueprint(posts: list[BlogPost], keyword: str, top_related: int = 25) -> Blueprint:
    if not posts:
        raise ValueError("분석할 글이 없습니다.")
    stats = [analyze_post(p, keyword) for p in posts]
    n = len(stats)

    kw_tokens = set(tokenize(keyword)) | {_squash(keyword)}
    df: Counter[str] = Counter()  # 몇 개의 글에 등장했는가(문서 빈도)
    tf: Counter[str] = Counter()
    for p in posts:
        toks = tokenize(p.title + "\n" + p.body_text)
        tf.update(toks)
        df.update(set(toks))
    # 절반 가까이의 글에서 공통으로 쓰인 단어 = 검색 의도에 맞는 연관 키워드일 가능성이 높다
    min_df = max(2, n // 3) if n >= 3 else 1
    related = sorted(
        ((w, df[w]) for w in df if df[w] >= min_df and w.lower() not in kw_tokens),
        key=lambda x: (-x[1], -tf[x[0]]),
    )[:top_related]

    patterns: Counter[str] = Counter()
    for s in stats:
        patterns.update(set(s.title_patterns))
    tags: Counter[str] = Counter()
    for s in stats:
        tags.update(set(s.tags))

    chars = [s.char_count for s in stats]
    imgs = [s.image_count for s in stats]
    kcs = [s.keyword_count for s in stats]
    headings: list[str] = []
    for s in stats:
        headings.extend(s.headings[:4])

    return Blueprint(
        keyword=keyword,
        sample_size=n,
        target_chars=_median_int(chars),
        chars_range=(min(chars), max(chars)),
        target_images=_median_int(imgs),
        images_range=(min(imgs), max(imgs)),
        target_headings=_median_int([s.heading_count for s in stats]),
        target_keyword_count=_median_int(kcs),
        keyword_count_range=(min(kcs), max(kcs)),
        avg_paragraph_len=round(statistics.mean(s.avg_paragraph_len for s in stats), 1),
        title_len=_median_int([s.title_len for s in stats]),
        keyword_in_title_ratio=round(sum(s.keyword_in_title for s in stats) / n, 2),
        keyword_front_ratio=round(sum(s.keyword_title_position == "front" for s in stats) / n, 2),
        keyword_in_intro_ratio=round(sum(s.keyword_in_first_paragraph for s in stats) / n, 2),
        video_ratio=round(sum(s.video_count > 0 for s in stats) / n, 2),
        map_ratio=round(sum(s.map_count > 0 for s in stats) / n, 2),
        title_patterns=patterns.most_common(10),
        related_keywords=related,
        common_tags=[t for t in tags.most_common(20) if t[1] >= min(2, n)],
        example_titles=[s.title for s in stats if s.title],
        example_headings=headings[:20],
        example_intros=[s.first_paragraph[:200] for s in stats if s.first_paragraph][:5],
        example_structures=[s.structure[:300] for s in stats][:5],
        posts=stats,
    )


def blueprint_to_brief(bp: Blueprint) -> str:
    """글쓰기 모델에게 넘길 사람이 읽을 수 있는 분석 요약."""
    pct = lambda r: f"{int(r * 100)}%"  # noqa: E731
    lines = [
        f"# 키워드 '{bp.keyword}' 상위노출/인기글 {bp.sample_size}개 분석 결과",
        "",
        "## 분량·구성 (중앙값 기준)",
        f"- 본문 글자 수(공백 제외): 약 {bp.target_chars}자 (범위 {bp.chars_range[0]}~{bp.chars_range[1]}자)",
        f"- 이미지 수: 약 {bp.target_images}장 (범위 {bp.images_range[0]}~{bp.images_range[1]}장)",
        f"- 소제목 수: 약 {bp.target_headings}개",
        f"- 문단 평균 길이: 약 {bp.avg_paragraph_len}자 (모바일 가독성 기준)",
        f"- 동영상 포함 글 비율: {pct(bp.video_ratio)}, 지도 포함 글 비율: {pct(bp.map_ratio)}",
        "",
        "## 키워드 배치",
        f"- 본문 키워드 반복: 약 {bp.target_keyword_count}회 (범위 {bp.keyword_count_range[0]}~{bp.keyword_count_range[1]}회)",
        f"- 제목에 키워드 포함 비율: {pct(bp.keyword_in_title_ratio)} (그중 제목 앞부분 배치 {pct(bp.keyword_front_ratio)})",
        f"- 도입부(첫 1~2문단)에 키워드 포함 비율: {pct(bp.keyword_in_intro_ratio)}",
        f"- 제목 길이: 약 {bp.title_len}자",
        "",
        "## 제목 패턴 (글 수)",
        *(f"- {p}: {c}개" for p, c in bp.title_patterns),
        "",
        "## 공통 연관 키워드 (등장한 글 수) — 검색 의도를 충족시키는 주제어",
        ", ".join(f"{w}({c})" for w, c in bp.related_keywords) or "(없음)",
        "",
        "## 자주 쓰인 태그",
        ", ".join(f"#{t}" for t, _ in bp.common_tags) or "(없음)",
        "",
        "## 상위 글 제목 예시",
        *(f"- {t}" for t in bp.example_titles[:10]),
        "",
        "## 상위 글 소제목 예시",
        *(f"- {h}" for h in bp.example_headings[:15]),
        "",
        "## 상위 글 도입부 예시 (참고용, 그대로 베끼지 말 것)",
        *(f"- {i}" for i in bp.example_intros),
        "",
        "## 상위 글 블록 흐름 예시",
        *(f"- {s}" for s in bp.example_structures),
    ]
    return "\n".join(lines)
