"""썸네일 안을 정사각형 HTML 시안으로 그린다 (미리캔버스·캔바로 옮기기 전 확인용)."""

from __future__ import annotations

import html

from .writer import ThumbnailIdea

_ALIGN = {
    "center": "justify-content:center;align-items:center;text-align:center;",
    "left": "justify-content:center;align-items:flex-start;text-align:left;",
    "top": "justify-content:flex-start;align-items:center;text-align:center;",
    "bottom": "justify-content:flex-end;align-items:center;text-align:center;",
}


def _main_copy_html(idea: ThumbnailIdea) -> str:
    text = html.escape(idea.main_copy)
    emph = html.escape(idea.emphasis or "")
    if emph and emph in text:
        text = text.replace(emph, f'<span style="color:{idea.accent_color}">{emph}</span>', 1)
    return text.replace("\\n", "<br>").replace("\n", "<br>")


def render_html(idea: ThumbnailIdea, size: int = 360) -> str:
    sub = html.escape(idea.sub_copy)
    visual = html.escape(idea.visual)
    return f"""
<div style="width:{size}px;height:{size}px;background:{idea.background};display:flex;flex-direction:column;
  {_ALIGN.get(idea.layout, _ALIGN['center'])}padding:{size // 12}px;box-sizing:border-box;border-radius:8px;
  font-family:'Pretendard','Noto Sans KR','Apple SD Gothic Neo','Malgun Gothic',sans-serif;position:relative;overflow:hidden">
  <div style="color:{idea.text_color};font-weight:900;font-size:{size // 8}px;line-height:1.2;letter-spacing:-1px">{_main_copy_html(idea)}</div>
  {f'<div style="color:{idea.text_color};opacity:.85;font-weight:600;font-size:{size // 18}px;margin-top:{size // 30}px">{sub}</div>' if sub else ''}
  <div style="position:absolute;bottom:8px;right:10px;left:10px;color:{idea.text_color};opacity:.55;font-size:{max(10, size // 32)}px;text-align:right">🖼 {visual}</div>
</div>"""


def render_page(ideas: list[ThumbnailIdea], title: str = "썸네일 시안") -> str:
    cards = "".join(
        f'<div style="margin:12px">{render_html(i)}<p style="max-width:360px;font-size:13px;color:#333">'
        f"<b>{html.escape(i.concept)}</b><br>{html.escape(i.rationale)}</p></div>"
        for i in ideas
    )
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title></head>'
            f'<body style="background:#f4f4f4;display:flex;flex-wrap:wrap">{cards}</body></html>')
