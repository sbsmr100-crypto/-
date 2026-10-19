"""웹 화면: streamlit run app.py"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from blog_assistant.pipeline import add_reference
from blog_assistant.references import SOURCES, ReferenceStore
from blog_assistant.scraper import post_from_text
from blog_assistant.thumbnail import render_html, render_page
from blog_assistant.writer import RefusedError, WriteRequest, char_count, draft_to_markdown, plan_thumbnails, write_draft

st.set_page_config(page_title="블로그 글쓰기 비서", page_icon="✍️", layout="wide")
st.title("✍️ 비즈니스·경제 블로그 비서")
st.caption("상위노출·홈판 글을 레퍼런스로 쌓고 → 키워드를 주면 홈판 썸네일 안과 2,000자 이내 원고를 만듭니다.")

with st.sidebar:
    st.header("API 키")
    for name, secret in (("ANTHROPIC_API_KEY", True), ("NAVER_CLIENT_ID", False), ("NAVER_CLIENT_SECRET", True)):
        v = st.text_input(name, value=os.environ.get(name, ""), type="password" if secret else "default")
        if v:
            os.environ[name] = v
    st.caption("네이버 키는 '검색 상위글 실시간 분석'에만 필요합니다.")

store = ReferenceStore()
tab_add, tab_list, tab_write = st.tabs(["① 레퍼런스 추가", "② 레퍼런스 보기", "③ 원고·썸네일"])

with tab_add:
    c1, c2, c3 = st.columns([2, 1, 1])
    kw = c1.text_input("키워드", key="ref_kw", placeholder="예: 금리 인하")
    source = c2.radio("노출 위치", SOURCES, horizontal=True)
    rank = c3.number_input("시작 순위 (모르면 0)", 0, 100, 0)
    note = st.text_input("메모 (선택)", placeholder="예: 크리에이터 어드바이저 유입 1위, 경제 주제판 노출")
    mode = st.radio("입력 방식", ["URL", "본문 붙여넣기"], horizontal=True,
                    help="URL로 수집이 안 되면(비공개·차단) 글을 복사해 붙여 넣으세요.")
    with_insight = st.checkbox("Claude로 노출 이유 분석 (썸네일 포함)", value=True)

    if mode == "URL":
        urls = st.text_area("블로그 URL (한 줄에 하나, 순위 순서대로)", height=140)
        if st.button("추가·분석", type="primary", disabled=not kw):
            lines = [u.strip() for u in urls.splitlines() if u.strip()]
            for i, url in enumerate(lines):
                with st.spinner(f"[{i + 1}/{len(lines)}] {url}"):
                    try:
                        path = add_reference(kw, source, url=url, rank=(rank + i) if rank else None,
                                             note=note, with_insight=with_insight, store=store)
                        st.success(f"저장: {path.name}")
                    except Exception as e:
                        st.error(f"{url}: {e}")
    else:
        title = st.text_input("글 제목")
        url = st.text_input("URL (선택)")
        body = st.text_area("본문 (소제목은 '## '로 시작, 사진 자리는 [사진] 한 줄)", height=260)
        images = st.number_input("본문 이미지 수 (위에 [사진]을 안 넣었다면)", 0, 100, 0)
        if st.button("추가·분석", type="primary", disabled=not (kw and title and body)):
            with st.spinner("분석 중…"):
                try:
                    post = post_from_text(title, body, url=url, image_count=images)
                    path = add_reference(kw, source, post=post, rank=rank or None, note=note,
                                         with_insight=with_insight, store=store)
                    st.success(f"저장: {path.name}")
                except Exception as e:
                    st.error(str(e))

with tab_list:
    refs = store.all()
    if not refs:
        st.info("아직 레퍼런스가 없습니다. ① 탭에서 추가하세요.")
    else:
        flt = st.text_input("키워드로 찾기")
        if flt:
            refs = store.related(flt, limit=1000)
        st.dataframe(pd.DataFrame([{
            "키워드": r["keyword"], "위치": r["source"], "순위": r.get("rank"), "제목": r["title"],
            "글자수": r["stats"].get("char_count"), "이미지": r["stats"].get("image_count"),
            "분석": "✓" if r.get("insight") else "", "URL": r["url"],
        } for r in refs]), hide_index=True, use_container_width=True,
            column_config={"URL": st.column_config.LinkColumn()})
        for r in refs[:30]:
            ins = r.get("insight")
            if not ins:
                continue
            with st.expander(f"[{r['source']}] {r['keyword']} · {r['title']}"):
                if r.get("thumbnail_url"):
                    st.image(r["thumbnail_url"], width=200)
                st.markdown("**노출 이유**\n" + "\n".join(f"- {x}" for x in ins["why_exposed"]))
                st.markdown(f"**검색 의도**: {ins['search_intent']}\n\n**제목**: {ins['title_analysis']}\n\n"
                            f"**도입부**: {ins['intro_hook']}\n\n**구성**: {ins['structure_analysis']}\n\n"
                            f"**시의성**: {ins['timeliness']}")
                th = ins["thumbnail"]
                if th["seen"]:
                    st.markdown(f"**썸네일**: 「{th['text_on_image']}」 · {th['layout']} · {th['colors']} · "
                                f"{th['typography']} → {th['why_it_works']}")
                st.markdown("**약점(이길 틈)**\n" + "\n".join(f"- {x}" for x in ins["weaknesses"]))
                st.markdown("**적용할 규칙**\n" + "\n".join(f"- {x}" for x in ins["reusable_lessons"]))

with tab_write:
    c1, c2 = st.columns([3, 1])
    keyword = c1.text_input("메인 키워드", key="write_kw", placeholder="예: 금리 인하 대출 갈아타기")
    limit = c2.number_input("최대 글자 수(공백 포함)", 800, 5000, 2000, step=100)
    notes = st.text_area("내 관점·경험·꼭 넣을 사실", height=110,
                         placeholder="예: 30대 직장인, 변동금리 주담대 3억. 은행 상담 받아본 내용, 중도상환수수료 1.2%…")
    extra = st.text_input("추가 요청 (선택)")
    related = store.related(keyword, limit=12) if keyword else []
    st.caption(f"참고할 레퍼런스: {len(related)}개 " + (f"(같은 키워드 {sum(r['keyword'] == keyword for r in related)}개)" if keyword else ""))

    if st.button("원고 + 썸네일 만들기", type="primary", disabled=not keyword):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY가 필요합니다 (사이드바).")
            st.stop()
        try:
            with st.spinner("원고 작성 중… (분량 초과 시 자동으로 줄입니다)"):
                draft = write_draft(WriteRequest(keyword, notes, extra, int(limit)), related)
            with st.spinner("썸네일 안 만드는 중…"):
                plan = plan_thumbnails(keyword, draft, related)
        except RefusedError as e:
            st.error(str(e))
            st.stop()
        st.session_state.update(draft=draft, plan=plan, draft_kw=keyword)

    if st.session_state.get("draft") and st.session_state.get("draft_kw") == keyword:
        draft, plan = st.session_state["draft"], st.session_state["plan"]
        st.subheader("🖼 홈판 썸네일 안")
        cols = st.columns(len(plan.ideas))
        for col, idea in zip(cols, plan.ideas):
            with col:
                components.html(render_html(idea, size=300), height=310)
                st.markdown(f"**{idea.concept}**\n\n이미지: {idea.visual}\n\n색: 배경 `{idea.background}` · 글자 "
                            f"`{idea.text_color}` · 강조 `{idea.accent_color}`\n\n근거: {idea.rationale}")
        st.markdown("\n".join(f"- {t}" for t in plan.tips))
        st.download_button("썸네일 시안 HTML", render_page(plan.ideas, draft.title), file_name=f"{keyword}_썸네일.html")

        with_space, no_space = char_count(draft.body)
        st.subheader("📝 원고")
        st.caption(f"공백 포함 {with_space}자 / 공백 제외 {no_space}자 (한도 {limit}자)")
        st.markdown(f"### {draft.title}")
        st.markdown(draft.body)
        st.markdown(" ".join("#" + h.lstrip("#") for h in draft.hashtags))
        with st.expander("제목 후보 · 직접 채울 항목 · 적용한 규칙"):
            st.markdown(draft_to_markdown(draft).split("---", 1)[1])
        st.download_button("원고 다운로드 (.md)", draft_to_markdown(draft), file_name=f"{keyword}.md")
