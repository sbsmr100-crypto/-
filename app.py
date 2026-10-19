"""웹 화면: streamlit run app.py"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from blog_assistant.analyzer import blueprint_to_brief
from blog_assistant.pipeline import analyze_keyword
from blog_assistant.writer import RefusedError, WriteRequest, stream_post

st.set_page_config(page_title="네이버 블로그 글쓰기 비서", page_icon="✍️", layout="wide")
st.title("✍️ 네이버 블로그 상위노출 글쓰기 비서")
st.caption("키워드 상위노출 글과 홈판 인기글을 분석해서, 그 패턴대로 새 원고를 써 드립니다.")

with st.sidebar:
    st.header("API 키")
    naver_id = st.text_input("NAVER_CLIENT_ID", value=os.environ.get("NAVER_CLIENT_ID", ""))
    naver_secret = st.text_input("NAVER_CLIENT_SECRET", value=os.environ.get("NAVER_CLIENT_SECRET", ""), type="password")
    anthropic_key = st.text_input("ANTHROPIC_API_KEY", value=os.environ.get("ANTHROPIC_API_KEY", ""), type="password")
    for k, v in {"NAVER_CLIENT_ID": naver_id, "NAVER_CLIENT_SECRET": naver_secret, "ANTHROPIC_API_KEY": anthropic_key}.items():
        if v:
            os.environ[k] = v
    st.markdown("네이버 키 발급: [developers.naver.com](https://developers.naver.com/apps) → 검색 API")

col1, col2 = st.columns([2, 1])
with col1:
    keyword = st.text_input("메인 키워드", placeholder="예: 제주도 흑돼지 맛집")
with col2:
    top_n = st.slider("분석할 상위 글 수", 3, 30, 10)

homefeed = st.text_area(
    "홈판/인기글 URL (선택, 한 줄에 하나)",
    placeholder="네이버 블로그 홈·주제별 인기글에서 본 비슷한 주제의 글 주소를 붙여 넣으면 함께 분석합니다.",
    height=90,
)
use_search = st.checkbox("네이버 검색 상위 글 자동 수집", value=True)

with st.expander("글 설정", expanded=True):
    c1, c2 = st.columns(2)
    post_type = c1.selectbox("글 유형", ["정보+후기형", "내돈내산 후기", "정보성(가이드/총정리)", "맛집/카페 리뷰", "여행 코스", "제품 비교/추천"])
    tone = c2.selectbox("말투", ["친근한 존댓말(~요체)", "전문가 느낌 존댓말(~습니다체)", "편한 반말 일기체"])
    notes = st.text_area(
        "내 실제 경험/정보 메모 (중요!)",
        placeholder="방문 날짜, 가격, 위치, 장단점, 느낌 등. 실제 경험이 많을수록 D.I.A. 로직에서 유리하고, 비워 두면 [직접 입력] 칸으로 남겨 둡니다.",
        height=120,
    )
    extra = st.text_input("추가 요청 (선택)", placeholder="예: 주차 정보 꼭 넣어줘, 아이 동반 관점으로")
    c3, c4 = st.columns(2)
    sponsored = c3.checkbox("협찬/광고 글")
    effort = c4.select_slider("작성 품질(생각 깊이)", ["low", "medium", "high", "xhigh"], value="high")

analyze_btn, write_btn = st.columns(2)
do_analyze = analyze_btn.button("1️⃣ 상위글 분석", use_container_width=True)
do_write = write_btn.button("2️⃣ 분석 + 원고 작성", type="primary", use_container_width=True)

if (do_analyze or do_write) and not keyword.strip():
    st.warning("키워드를 입력해 주세요.")
    st.stop()

if do_analyze or (do_write and st.session_state.get("keyword") != keyword):
    status = st.status("수집·분석 중…", expanded=True)
    try:
        bp, collected = analyze_keyword(
            keyword.strip(),
            top_n=top_n,
            extra_urls=homefeed.splitlines(),
            use_search=use_search,
            on_progress=status.write,
        )
    except Exception as e:
        status.update(label="수집 실패", state="error")
        st.error(str(e))
        st.stop()
    st.session_state.update(keyword=keyword, blueprint=bp, errors=collected.errors)
    status.update(label=f"분석 완료: {len(collected.posts)}개 글", state="complete", expanded=False)

bp = st.session_state.get("blueprint") if st.session_state.get("keyword") == keyword else None

for url, err in st.session_state.get("errors", []):
    st.caption(f"⚠️ 건너뜀: {url} — {err}")

if bp is not None:
    st.subheader("📊 분석 결과")
    m = st.columns(5)
    m[0].metric("권장 글자 수", f"{bp.target_chars:,}자")
    m[1].metric("권장 이미지", f"{bp.target_images}장")
    m[2].metric("키워드 반복", f"{bp.target_keyword_count}회")
    m[3].metric("소제목", f"{bp.target_headings}개")
    m[4].metric("제목에 키워드", f"{int(bp.keyword_in_title_ratio * 100)}%")

    t1, t2, t3 = st.tabs(["글별 상세", "연관 키워드·제목 패턴", "요약 브리프"])
    with t1:
        df = pd.DataFrame(
            [
                {
                    "제목": s.title, "글자수": s.char_count, "이미지": s.image_count, "소제목": s.heading_count,
                    "키워드": s.keyword_count, "1000자당": s.keyword_density, "문단평균": s.avg_paragraph_len,
                    "동영상": s.video_count, "URL": s.url,
                }
                for s in bp.posts
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True, column_config={"URL": st.column_config.LinkColumn()})
    with t2:
        a, b = st.columns(2)
        a.markdown("**공통 연관 키워드** (등장한 글 수)")
        a.dataframe(pd.DataFrame(bp.related_keywords, columns=["단어", "글 수"]), hide_index=True)
        b.markdown("**제목 패턴**")
        b.dataframe(pd.DataFrame(bp.title_patterns, columns=["패턴", "글 수"]), hide_index=True)
    with t3:
        st.code(blueprint_to_brief(bp), language="markdown")

if do_write:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY가 필요합니다 (사이드바).")
        st.stop()
    if bp is None:
        st.info("분석 데이터 없이 일반 상위노출 기준으로 작성합니다.")
    st.subheader("📝 원고")
    req = WriteRequest(keyword.strip(), post_type, tone, notes, extra, sponsored)
    try:
        text = st.write_stream(stream_post(req, bp, effort=effort))
    except RefusedError as e:
        st.error(str(e))
        st.stop()
    st.session_state["draft"] = text

if st.session_state.get("draft"):
    st.download_button("원고 다운로드 (.md)", st.session_state["draft"], file_name=f"{keyword or 'post'}.md")
