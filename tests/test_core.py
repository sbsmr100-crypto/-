from pathlib import Path

from blog_assistant.analyzer import analyze_post, blueprint_to_brief, build_blueprint, count_keyword, tokenize
from blog_assistant.scraper import BlogPost, Block, parse_blog_url, parse_post_html, postview_url
from blog_assistant.writer import WriteRequest, build_user_prompt

FIXTURE = (Path(__file__).parent / "fixtures" / "se_post.html").read_text(encoding="utf-8")


def test_parse_blog_url_variants():
    assert parse_blog_url("https://blog.naver.com/abc/223456") == ("abc", "223456")
    assert parse_blog_url("https://m.blog.naver.com/abc/223456") == ("abc", "223456")
    assert parse_blog_url("https://blog.naver.com/PostView.naver?blogId=abc&logNo=1") == ("abc", "1")
    assert parse_blog_url("https://blog.naver.com/abc?Redirect=Log&logNo=9") == ("abc", "9")
    assert parse_blog_url("https://example.tistory.com/1") is None
    assert "PostView.naver?blogId=abc&logNo=223456" in postview_url("https://blog.naver.com/abc/223456")


def test_parse_smart_editor():
    post = parse_post_html(FIXTURE, url="u")
    assert post.title.startswith("제주도 흑돼지 맛집")
    assert post.count("image") == 3
    assert post.headings == ["1. 위치와 주차"]
    assert post.count("sticker") == 1 and post.count("map") == 1
    assert len(post.paragraphs) == 4
    assert "2만5천원" in post.bold_phrases
    assert {"제주맛집", "흑돼지", "제주도여행"} <= set(post.tags)


def test_keyword_counting_ignores_spaces():
    assert count_keyword("제주도 흑돼지 맛집, 제주도흑돼지맛집", "제주도 흑돼지 맛집") == 2


def test_tokenize_strips_josa():
    toks = tokenize("흑돼지는 정말 맛있어요 주차를 했어요")
    assert "흑돼지" in toks and "주차" in toks and "정말" not in toks


def test_analyze_and_blueprint():
    post = parse_post_html(FIXTURE, url="u")
    s = analyze_post(post, "제주도 흑돼지 맛집")
    assert s.keyword_in_title and s.keyword_title_position == "front"
    assert s.keyword_count == 2 and s.keyword_in_first_paragraph
    assert "숫자 포함" in s.title_patterns and "'후기'" in s.title_patterns
    assert s.structure.startswith("텍스트2 → 이미지3 → 소제목")

    other = BlogPost(url="v", title="흑돼지 맛집 추천", blocks=[Block("text", "흑돼지 주차 가능한 곳"), Block("image")])
    bp = build_blueprint([post, other], "제주도 흑돼지 맛집")
    assert bp.sample_size == 2 and bp.images_range == (1, 3)
    assert bp.related_keywords[0] == ("주차", 2)
    assert all(w != "흑돼지" for w, _ in bp.related_keywords)  # 키워드 자체는 제외
    brief = blueprint_to_brief(bp)
    assert "제주도 흑돼지 맛집" in brief and "이미지 수" in brief

    prompt = build_user_prompt(WriteRequest("제주도 흑돼지 맛집", experience_notes="3월 방문"), bp)
    assert "3월 방문" in prompt and "분석 결과" in prompt
    assert "일반적인 네이버 상위노출 기준" in build_user_prompt(WriteRequest("x"), None)
