# 네이버 블로그 상위노출 글쓰기 비서

키워드를 넣으면 **네이버 검색 상위노출 글**과 **홈판(블로그 홈·주제별 인기글)에서 바이럴된 글**을 수집·분석해서,
그 패턴(분량, 이미지 수, 키워드 반복·배치, 제목 패턴, 소제목 구성, 연관 키워드)에 맞춰 Claude가 새 원고를 써 줍니다.

## 동작 방식

1. **수집** — 네이버 검색 API(정확도순)로 키워드 상위 블로그 글을 찾고, 직접 붙여 넣은 홈판 인기글 URL과 함께 본문을 가져옵니다.
2. **분석** — 글마다 글자 수, 문단 길이, 이미지/동영상/지도/소제목 수, 키워드 반복 횟수와 위치, 제목 패턴, 블록 흐름을 계산하고,
   여러 글에 공통으로 등장하는 **연관 키워드**를 뽑아 '설계도'를 만듭니다. (LLM 없이 계산 → 결과가 일정)
3. **작성** — 설계도 + 내 실제 경험 메모를 바탕으로 제목 후보 5개, 본문(사진 위치 표시 포함), 해시태그, 발행 전 체크리스트를 생성합니다.
   - 상위 글 문장을 베끼지 않고 구조만 참고 → 유사문서 위험 회피
   - 없는 경험·가격은 지어내지 않고 `[직접 입력: …]` 칸으로 남김 → D.I.A.+ (경험 정보) 대응

> 홈판 노출 글은 공식 API가 없어서 자동 수집하지 않습니다. 블로그 홈/인기글에서 본 비슷한 주제의 글 주소를 붙여 넣으면 함께 분석합니다.

## 준비

```bash
pip install -r requirements.txt
export NAVER_CLIENT_ID=...        # https://developers.naver.com/apps → 애플리케이션 등록 → 검색 API
export NAVER_CLIENT_SECRET=...
export ANTHROPIC_API_KEY=...      # https://console.anthropic.com
```

## 사용법

### 웹 화면
```bash
streamlit run app.py
```
키워드 입력 → (선택) 홈판 URL 붙여넣기 → 경험 메모 작성 → **분석 + 원고 작성**.

### 터미널
```bash
# 분석 + 원고 작성
python -m blog_assistant.cli "제주도 흑돼지 맛집" --notes "3월 방문, 1인 2만5천원, 주차 가능" -o post.md

# 분석 결과만 보기
python -m blog_assistant.cli "제주도 흑돼지 맛집" --analyze-only --save-analysis analysis.json

# 검색 없이 홈판 인기글만 분석
python -m blog_assistant.cli "제주도 흑돼지 맛집" --no-search --urls-file homefeed_urls.txt
```

## 구조

| 파일 | 역할 |
|---|---|
| `blog_assistant/naver_search.py` | 네이버 검색 API(블로그) 호출 |
| `blog_assistant/scraper.py` | 블로그 본문 수집·파싱 (스마트에디터 ONE / 구 에디터) |
| `blog_assistant/analyzer.py` | 글별 지표 + 종합 설계도(Blueprint) |
| `blog_assistant/writer.py` | Claude 원고 생성 (스트리밍) |
| `blog_assistant/pipeline.py` | 수집 → 분석 연결 |
| `app.py` / `blog_assistant/cli.py` | 웹 화면 / 터미널 |

## 참고

- 원고는 Claude Opus 5.5(`claude-opus-5-5`)로 생성하며, 모델이 요청을 거절할 경우 다른 모델로 자동 재시도(server-side fallback)하도록 켜져 있습니다.
- 수집 시 글 사이에 0.5초 간격을 둡니다. 과도한 요청은 피하세요.
- 네이버 페이지 구조가 바뀌면 `scraper.py`의 선택자를 수정해야 할 수 있습니다.

## 테스트
```bash
python -m pytest -q
```
