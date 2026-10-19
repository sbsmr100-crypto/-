"""Claude 호출 공통부: 구조화 출력(Pydantic) + 거절 시 자동 대체 모델."""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-5-5"
T = TypeVar("T", bound=BaseModel)


class RefusedError(RuntimeError):
    pass


def parse(
    schema: type[T],
    system: str,
    messages: list[dict],
    effort: str = "high",
    client: anthropic.Anthropic | None = None,
    max_tokens: int = 16000,
):
    """구조화 응답을 받는다. (parsed, response) 반환 — response는 이어서 대화할 때 쓴다."""
    client = client or anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=messages,
        output_format=schema,
    )
    if response.stop_reason == "refusal":
        raise RefusedError("모델이 이 요청을 거절했습니다. 내용을 바꿔 다시 시도해 주세요.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise RuntimeError("응답이 잘렸거나 형식이 맞지 않습니다. 다시 시도해 주세요.")
    return response.parsed_output, response
