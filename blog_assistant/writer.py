"""레퍼런스(+선택: 실시간 상위글 설계도)를 바탕으로 2,000자 이내 원고와 홈판 썸네일 안을 만든다.

분야 기본값은 비즈니스·경제.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from . import llm
from .analyzer import Blueprint, blueprint_to_brief
from .llm import RefusedError  # noqa: F401  (app/cli에서 가져다 씀)
from .references import digest

DEFAULT_LIMIT = 2000

WRITER_SYSTEM = """\
당신은 비즈니스·경제 분야 네이버 블로그 전문 작가입니다. 사용자의 블로그에 바로 발행할 원고를 씁니다.

반드시 지킬 것:
- 본문은 공백 포함 {limit}자 이내(목표 {target_lo}~{target_hi}자). [사진: …] 표시는 글자 수에서 빠집니다.
- 레퍼런스에서 확인된 '노출 이유'와 '적용할 규칙'을 이 글에 구체적으로 적용하세요. 단, 레퍼런스 문장은 베끼지 말고 새로 쓰세요(유사문서 방지).
- 숫자·금리·환율·지수·정책 내용은 당신이 확실히 아는 것이 아니면 지어내지 말고 [직접 입력: 최신 ○○ 수치, 기준일·출처]로 비워 두세요.
  경제 수치는 금방 낡으므로, 확실히 아는 수치라도 기준 시점을 함께 쓰세요.
- 사용자가 준 메모의 사실과 관점을 최우선으로 살리세요.
- 첫 3줄: 독자가 얻을 것(돈·시간·리스크)을 약속하는 훅 + 메인 키워드 자연스럽게 1회.
- 키워드는 제목 앞부분, 도입부, 소제목 1~2곳, 마무리에 자연스럽게. 억지 반복 금지.
- 어려운 개념은 한 줄 정의 + 생활 속 예시. '그래서 나에게 어떤 영향인가'를 꼭 다루세요.
- 모바일 기준 짧은 문단(1~3문장), 소제목은 '### ', 핵심 문장은 **굵게**(과하지 않게), 사진 위치는 [사진: 설명] 줄로.
- 마지막: 3줄 요약 + 댓글을 부르는 질문 한 줄. 특정 종목·상품 매수/매도 권유는 하지 말고, 필요하면 '투자 판단은 본인 책임' 한 줄.
"""

THUMB_SYSTEM = """\
당신은 네이버 블로그 홈판(블로그 홈·주제판) 썸네일 디자이너입니다. 분야는 비즈니스·경제입니다.
홈판 카드에서 썸네일은 작게 보이므로: 문구는 짧고 굵게(메인 6~12자), 한 단어는 강조색, 배경과 글자 대비 강하게,
시선이 멈출 요소(숫자, 화살표/그래프, 질문, 인물 표정) 하나. 레퍼런스에서 실제로 먹힌 썸네일 패턴을 근거로 제안하고,
서로 다른 방향의 안 3개를 주세요. 제목과 썸네일 문구는 겹치지 않고 서로 보완해야 합니다.
"""


class Draft(BaseModel):
    title: str = Field(description="발행할 제목 (메인 키워드를 앞쪽에)")
    alt_titles: list[str] = Field(description="다른 제목 후보 4개, 서로 다른 패턴")
    body: str = Field(description="본문. ### 소제목, [사진: 설명] 줄, **굵게** 사용")
    hashtags: list[str] = Field(description="해시태그 10~15개, # 없이 단어만")
    fill_in: list[str] = Field(description="사용자가 직접 채워야 하는 [직접 입력] 항목 목록")
    applied_lessons: list[str] = Field(description="이 원고에 적용한 레퍼런스 규칙과 적용 위치")


class ThumbnailIdea(BaseModel):
    concept: str = Field(description="한 줄 콘셉트")
    main_copy: str = Field(description="썸네일 메인 문구 (6~12자 권장, 줄바꿈은 \\n)")
    emphasis: str = Field(description="main_copy 안에서 강조색을 입힐 부분 (main_copy의 부분 문자열)")
    sub_copy: str = Field(description="보조 문구 (짧게, 없으면 빈 문자열)")
    layout: Literal["center", "left", "top", "bottom"] = Field(description="문구 배치")
    background: str = Field(description="배경색 HEX, 예: #0B1F3A")
    text_color: str = Field(description="메인 글자색 HEX")
    accent_color: str = Field(description="강조색 HEX")
    visual: str = Field(description="넣을 시각 요소 (예: 상승 그래프 화살표, 지폐 사진, 놀란 표정 인물). 직접 찍거나 구할 이미지 설명")
    rationale: str = Field(description="이 안을 추천하는 근거 (어떤 레퍼런스 패턴인지)")


class ThumbnailPlan(BaseModel):
    ideas: list[ThumbnailIdea] = Field(description="서로 다른 방향의 3개 안")
    tips: list[str] = Field(description="제작 팁 2~4개 (사이즈, 글꼴, 피해야 할 것)")


@dataclass
class WriteRequest:
    keyword: str
    notes: str = ""
    extra_instructions: str = ""
    limit: int = DEFAULT_LIMIT


_IMG_LINE = re.compile(r"^\s*\[(사진|이미지)[^\]]*\]\s*$", re.M)


def visible_text(body: str) -> str:
    """발행 시 실제로 보일 글자: 사진 표시 줄과 마크다운 기호를 뺀다."""
    t = _IMG_LINE.sub("", body)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M).replace("**", "")
    return re.sub(r"\n{2,}", "\n", t).strip()


def char_count(body: str) -> tuple[int, int]:
    """(공백 포함, 공백 제외) 글자 수."""
    t = visible_text(body)
    return len(t.replace("\n", " ")), len(re.sub(r"\s", "", t))


def _context(req: WriteRequest, refs: list[dict], blueprint: Blueprint | None) -> str:
    parts = [f"메인 키워드: {req.keyword}"]
    parts.append("내 메모(경험·관점·전달할 사실):\n" + (req.notes.strip() or "(없음)"))
    if req.extra_instructions.strip():
        parts.append("추가 요청:\n" + req.extra_instructions.strip())
    parts.append("## 레퍼런스 분석 (관련도 높은 순)\n" + (digest(refs) if refs else "(아직 레퍼런스 없음 - 일반 원칙으로)"))
    if blueprint is not None:
        parts.append(blueprint_to_brief(blueprint))
    return "\n\n".join(parts)


def write_draft(req: WriteRequest, refs: list[dict], blueprint: Blueprint | None = None,
                client: anthropic.Anthropic | None = None, effort: str = "high", max_revisions: int = 2) -> Draft:
    client = client or anthropic.Anthropic()
    system = WRITER_SYSTEM.format(limit=req.limit, target_lo=int(req.limit * 0.75), target_hi=int(req.limit * 0.95))
    messages: list[dict] = [{"role": "user", "content": _context(req, refs, blueprint) + "\n\n원고를 작성해 주세요."}]
    draft, resp = llm.parse(Draft, system, messages, effort=effort, client=client)
    for _ in range(max_revisions):
        with_space, _ = char_count(draft.body)
        if with_space <= req.limit:
            break
        messages += [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": (
                f"본문이 공백 포함 {with_space}자로 {req.limit}자를 넘습니다. "
                f"핵심과 키워드 배치는 유지하고 {int(req.limit * 0.9)}자 안팎으로 줄여 같은 형식으로 다시 주세요."
            )},
        ]
        draft, resp = llm.parse(Draft, system, messages, effort=effort, client=client)
    return draft


def plan_thumbnails(keyword: str, draft: Draft | None, refs: list[dict],
                    client: anthropic.Anthropic | None = None, effort: str = "medium") -> ThumbnailPlan:
    parts = [f"메인 키워드: {keyword}"]
    if draft is not None:
        parts.append(f"글 제목: {draft.title}\n본문 앞부분:\n{visible_text(draft.body)[:600]}")
    parts.append("## 레퍼런스 분석\n" + (digest(refs) if refs else "(아직 레퍼런스 없음)"))
    parts.append("홈판 썸네일 3개 안을 제안해 주세요.")
    plan, _ = llm.parse(ThumbnailPlan, THUMB_SYSTEM, [{"role": "user", "content": "\n\n".join(parts)}],
                        effort=effort, client=client)
    return plan


def draft_to_markdown(d: Draft) -> str:
    with_space, no_space = char_count(d.body)
    return "\n".join([
        f"# {d.title}", "", d.body, "", " ".join("#" + h.lstrip("#") for h in d.hashtags), "", "---",
        f"글자 수: 공백 포함 {with_space}자 / 공백 제외 {no_space}자", "",
        "다른 제목 후보:", *(f"- {t}" for t in d.alt_titles), "",
        "직접 채울 항목:", *(f"- {f}" for f in d.fill_in), "",
        "적용한 레퍼런스 규칙:", *(f"- {a}" for a in d.applied_lessons),
    ])
