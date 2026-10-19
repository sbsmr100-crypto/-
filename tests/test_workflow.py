from types import SimpleNamespace

from blog_assistant import writer
from blog_assistant.analyzer import analyze_post
from blog_assistant.insights import PostInsight, ThumbnailAnalysis
from blog_assistant.references import ReferenceStore, digest
from blog_assistant.scraper import post_from_text
from blog_assistant.thumbnail import render_html
from blog_assistant.writer import Draft, ThumbnailIdea, WriteRequest, char_count, write_draft


def _insight():
    return PostInsight(
        search_intent="금리 인하가 내 대출에 주는 영향", why_exposed=["도입부에 월 상환액 변화 수치"],
        title_analysis="키워드 앞배치", intro_hook="질문형", structure_analysis="소제목 4개",
        credibility_elements=["한국은행 발표 인용"], timeliness="기준금리 발표 직후",
        thumbnail=ThumbnailAnalysis(seen=True, text_on_image="내 이자 얼마?", layout="중앙", colors="남색/노랑",
                                    typography="굵은 고딕", why_it_works="질문+숫자"),
        weaknesses=["실제 사례 없음"], reusable_lessons=["첫 문단에 월 상환액 예시"],
    )


def test_post_from_text_and_char_count():
    post = post_from_text("금리 인하 대출 정리", "## 핵심 요약\n금리 인하 소식입니다.\n[사진]\n#금리 #대출", image_count=2)
    assert post.headings == ["핵심 요약"] and post.count("image") == 3 and post.tags == ["금리", "대출"]
    body = "### 소제목\n**금리**가 내려요.\n[사진: 그래프]\n끝"
    assert char_count(body) == (len("소제목 금리가 내려요. 끝"), len("소제목금리가내려요.끝"))


def test_reference_store_roundtrip(tmp_path):
    store = ReferenceStore(tmp_path)
    post = post_from_text("금리 인하 대출 갈아타기 총정리", "금리 인하 시기에 대출을 갈아타는 방법", url="https://blog.naver.com/abc/123")
    stats = analyze_post(post, "금리 인하")
    store.add(post, stats, "금리 인하", "홈판", rank=1, insight=_insight())
    other = post_from_text("부동산 세금", "양도세 정리", url="https://blog.naver.com/x/9")
    store.add(other, analyze_post(other, "양도세"), "양도세", "상위노출")
    # 같은 글이 다른 키워드로 다시 들어오면 키워드를 합친다
    store.add(post, stats, "대출 갈아타기", "상위노출")

    assert len(store.all()) == 2
    top = store.related("대출 갈아타기")[0]
    assert top["id"] == "abc_123" and top["also_keywords"] == ["금리 인하"]
    text = digest(store.related("금리 인하"))
    assert "양도세" in text  # 관련 없는 글도 뒤에 붙는다(분야 일반 레퍼런스)


def test_write_draft_trims_when_over_limit(monkeypatch):
    long = Draft(title="t", alt_titles=[], body="가" * 2500, hashtags=[], fill_in=[], applied_lessons=[])
    short = Draft(title="t", alt_titles=[], body="가" * 1800, hashtags=[], fill_in=[], applied_lessons=[])
    calls = []

    def fake_parse(schema, system, messages, **kw):
        calls.append(messages)
        return (long if len(calls) == 1 else short), SimpleNamespace(content=[])

    monkeypatch.setattr(writer.llm, "parse", fake_parse)
    d = write_draft(WriteRequest("금리", limit=2000), refs=[], client=object())
    assert d is short and len(calls) == 2
    assert "2500자" in calls[1][-1]["content"]


def test_render_thumbnail_escapes_and_highlights():
    idea = ThumbnailIdea(concept="c", main_copy="금리 <인하>\\n내 이자는?", emphasis="내 이자", sub_copy="",
                         layout="left", background="#000", text_color="#fff", accent_color="#ff0",
                         visual="그래프", rationale="r")
    h = render_html(idea)
    assert "&lt;인하&gt;" in h and '<span style="color:#ff0">내 이자</span>' in h and "<br>" in h
