"""post.md → post.html 미리보기 (그림을 base64로 넣어 파일 하나로 열람) + 본문 글자 수 출력.

사용: python3 tools/preview.py "output/<키워드>"
"""

import base64
import html
import pathlib
import re
import sys


def body_chars(md: str) -> int:
    """제목 후보 블록과 해시태그를 빼고, 그림·[직접 입력]·마크다운 기호를 제외한 공백 포함 글자 수."""
    body = md.split("---\n", 1)[1]
    body = re.split(r"^#\S", body, flags=re.M)[0]
    t = re.sub(r"^!\[[^\]]*\]\([^)]*\)\s*$", "", body, flags=re.M)
    t = re.sub(r"^\s*\[(직접 입력|사진)[^\]]*\]\s*$", "", t, flags=re.M)
    t = re.sub(r"^>\s*", "", t, flags=re.M).replace("**", "")
    t = re.sub(r"^\|?-[-|]+\|?$", "", t, flags=re.M).replace("|", " ").replace("---", "")
    t = re.sub(r"\n{2,}", "\n", t).strip()
    return len(t.replace("\n", " "))


def render(folder: pathlib.Path) -> pathlib.Path:
    md = (folder / "post.md").read_text()
    out, table = [], []

    def flush_table():
        if table:
            rows = [r for r in table if not re.match(r"^\|?\s*-[-|\s]+$", r)]
            cells = [[html.escape(c.strip()) for c in r.strip("|").split("|")] for r in rows]
            head = "".join(f"<th>{c}</th>" for c in cells[0])
            body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in cells[1:])
            out.append(f"<table><tr>{head}</tr>{body}</table>")
            table.clear()

    for line in md.splitlines():
        if line.startswith("|"):
            table.append(line)
            continue
        flush_table()
        m = re.match(r"!\[([^\]]*)\]\(([^)]*)\)", line)
        if m:
            b = base64.b64encode((folder / m.group(2)).read_bytes()).decode()
            out.append(f'<img src="data:image/png;base64,{b}" alt="{html.escape(m.group(1))}">')
            continue
        e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line))
        if line.startswith("# "):
            out.append(f"<h1>{e[2:]}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{e[5:]}</blockquote>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{e}</p>")
    flush_table()
    title = html.escape(folder.name)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} 원고</title>
<style>body{{max-width:720px;margin:0 auto;padding:24px 16px;font:17px/1.75 'Noto Sans KR',sans-serif;color:#222;background:#fff}}
h1{{font-size:24px;line-height:1.4}}p{{margin:.35em 0}}img{{width:100%;border-radius:8px;margin:14px 0}}
blockquote{{margin:28px 0 12px;padding:14px 18px;border-left:5px solid #e63946;background:#fff4f4;font-weight:700;font-size:20px}}
hr{{border:0;border-top:1px solid #ddd;margin:24px 0}}table{{border-collapse:collapse;width:100%;margin:12px 0}}
th,td{{border:1px solid #ddd;padding:8px 10px;text-align:left}}th{{background:#f4f5f7}}</style></head><body>
{chr(10).join(out)}</body></html>"""
    path = folder / "post.html"
    path.write_text(page)
    return path


if __name__ == "__main__":
    folder = pathlib.Path(sys.argv[1])
    print(render(folder), "/ 본문", body_chars((folder / "post.md").read_text()), "자(공백 포함)")
