"""분석 설계도(Blueprint)를 바탕으로 Claude가 네이버 블로그 원고를 작성한다."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import anthropic

from .analyzer import Blueprint, blueprint_to_brief

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
당신은 네이버 블로그 상위노출과 홈판(블로그 홈/주제별 인기글) 노출 경험이 많은 전문 블로그 작가이자 비서입니다.
사용자가 준 키워드와 '상위노출 글 분석 결과'를 설계도로 삼아, 바로 복사해 발행할 수 있는 원고를 씁니다.

네이버 노출 로직에 대해 알고 지킬 것:
- D.I.A.+ 로직은 '직접 경험한 정보', 구체성(가격·날짜·수치·장소·사용 기간), 검색 의도 충족을 높게 평가합니다.
  사용자가 준 경험 메모의 사실을 최대한 살리고, 없는 경험·수치·가격을 지어내지 마세요.
  정보가 비어 있는 곳은 [직접 입력: 무엇을 적을지] 형태로 표시해 사용자가 채우게 하세요.
- 유사문서 판정을 피해야 합니다. 상위 글의 문장·표현을 그대로 가져오지 말고, 구조와 다루는 주제만 참고해 새로 쓰세요.
- 키워드는 분석 결과의 반복 횟수 범위 안에서 자연스럽게 배치합니다. 억지 반복(어뷰징)은 오히려 감점입니다.
  제목 앞부분, 도입부 첫 2문단, 소제목 일부, 마무리에 배치하고, 연관 키워드는 본문 곳곳에 녹입니다.
- 홈판 노출·체류시간을 위해: 첫 3줄 안에 독자가 얻을 것을 약속하는 훅, 모바일 기준 짧은 문단(1~3문장),
  소제목으로 끊어 읽기, 중간중간 이미지 위치, 마지막에 요약과 공감/댓글을 부르는 한 줄.
- 이미지 위치는 [사진: 어떤 장면을 어떻게 찍을지] 로 표시합니다. 분석된 이미지 수에 맞춥니다.
- 강조가 필요한 핵심 문장은 **굵게** 표시합니다(과하지 않게).
- 광고·협찬이 있다면 사용자가 알려준 경우 본문 상단에 표기 문구를 넣습니다.

출력 형식(마크다운, 이 순서 그대로):
## 제목 후보
(5개, 각각 다른 패턴. 분석된 제목 길이·패턴을 참고)
## 본문
(첫 번째 제목 기준 완성 원고. 소제목은 ### 로)
## 해시태그
(10~15개, 한 줄에 #태그 형식)
## 발행 전 체크리스트
(이 원고의 글자 수 추정치, 키워드 반복 횟수, 이미지 수가 분석 범위에 맞는지, 사용자가 채워야 할 [직접 입력] 항목 목록, 발행 팁 3가지)
"""


@dataclass
class WriteRequest:
    keyword: str
    post_type: str = "정보+후기형"
    tone: str = "친근한 존댓말(~요체)"
    experience_notes: str = ""
    extra_instructions: str = ""
    sponsored: bool = False


def build_user_prompt(req: WriteRequest, blueprint: Blueprint | None) -> str:
    parts = [f"메인 키워드: {req.keyword}", f"글 유형: {req.post_type}", f"말투: {req.tone}"]
    parts.append(f"협찬/광고 여부: {'예 - 상단에 표기 필요' if req.sponsored else '아니오'}")
    parts.append(
        "내 실제 경험/정보 메모:\n" + (req.experience_notes.strip() or "(없음 - 경험이 필요한 부분은 [직접 입력]으로 비워 둘 것)")
    )
    if req.extra_instructions.strip():
        parts.append("추가 요청:\n" + req.extra_instructions.strip())
    if blueprint is not None:
        parts.append(blueprint_to_brief(blueprint))
    else:
        parts.append(
            "(상위 글 분석 데이터 없음 - 일반적인 네이버 상위노출 기준: 공백 제외 1,500~2,500자, 이미지 10~15장, "
            "소제목 3~5개, 키워드 5~8회로 작성)"
        )
    parts.append("위 설계도를 따라 원고를 작성해 주세요.")
    return "\n\n".join(parts)


class RefusedError(RuntimeError):
    pass


def stream_post(
    req: WriteRequest,
    blueprint: Blueprint | None = None,
    client: anthropic.Anthropic | None = None,
    effort: str = "high",
) -> Iterator[str]:
    """원고를 스트리밍으로 생성한다. 텍스트 조각을 차례로 yield."""
    client = client or anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(req, blueprint)}],
    ) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
    if final.stop_reason == "refusal":
        raise RefusedError("모델이 이 요청의 작성을 거절했습니다. 키워드나 요청 내용을 바꿔 다시 시도해 주세요.")
    if final.stop_reason == "max_tokens":
        yield "\n\n(⚠️ 출력 길이 한도에 도달해 원고가 잘렸을 수 있습니다.)"


def write_post(req: WriteRequest, blueprint: Blueprint | None = None, **kwargs) -> str:
    return "".join(stream_post(req, blueprint, **kwargs))
