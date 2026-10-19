# 비즈니스·경제 블로그 비서 (네이버)

**레퍼런스를 쌓고 → 키워드를 주면 홈판 썸네일 안 + 2,000자 이내 원고**를 만드는 도구입니다.

```
크리에이터 어드바이저에서 키워드별 상위노출·홈판 글 찾기
   ↓  ① 레퍼런스 추가 (URL 또는 본문 붙여넣기)
지표 계산 + Claude가 "왜 노출됐는지" 분석 (썸네일 이미지 포함) → references/*.json 에 누적
   ↓  ③ 키워드 입력
관련 레퍼런스의 '노출 이유·적용할 규칙·썸네일 패턴'을 근거로
   → 홈판 썸네일 3안 (문구·색·배치 + HTML 시안)
   → 원고 (공백 포함 2,000자 이내, 넘으면 자동으로 줄임)
```

## 준비

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # 필수
export NAVER_CLIENT_ID=...          # 선택: 검색 상위글 실시간 분석할 때만
export NAVER_CLIENT_SECRET=...
```

## 웹 화면

```bash
streamlit run app.py
```

| 탭 | 하는 일 |
|---|---|
| ① 레퍼런스 추가 | 키워드 · 노출 위치(상위노출/홈판) · 순위 · 메모 + URL 여러 개. 수집이 안 되는 글은 본문 붙여넣기 |
| ② 레퍼런스 보기 | 쌓인 글 목록, 글별 노출 이유·썸네일 분석·약점·적용할 규칙 |
| ③ 원고·썸네일 | 키워드 + 내 관점/경험 메모 → 썸네일 3안 + 원고 |

## 터미널

```bash
# 레퍼런스 쌓기
python -m blog_assistant.cli ref add URL1 URL2 URL3 -k "금리 인하" -s 상위노출 --rank 1
python -m blog_assistant.cli ref add URL -k "금리 인하" -s 홈판 --note "경제 주제판 노출"
python -m blog_assistant.cli ref import refs.csv     # 열: keyword,source,rank,url,note
python -m blog_assistant.cli ref list -k "금리 인하"

# 원고 + 썸네일
python -m blog_assistant.cli write "금리 인하 대출 갈아타기" --notes "30대 직장인, 변동금리 주담대 관점" -o out
# → out.md, out_thumbnails.html
```

## 원고 원칙 (비즈니스·경제)

- 공백 포함 2,000자 이내 (`[사진: …]` 표시는 제외하고 셈). 초과하면 최대 2번 자동으로 줄입니다.
- 확실하지 않은 수치·금리·정책은 지어내지 않고 `[직접 입력: 최신 ○○ 수치, 기준일·출처]`로 남깁니다.
- 레퍼런스 문장은 베끼지 않고 노출 이유와 구조만 적용합니다 (유사문서 방지).
- 매수·매도 권유는 하지 않습니다.

## 구조

| 파일 | 역할 |
|---|---|
| `blog_assistant/scraper.py` | 블로그 본문·대표 썸네일 수집, 붙여넣은 본문 파싱 |
| `blog_assistant/analyzer.py` | 글별 지표 (글자수, 이미지, 키워드 배치, 제목 패턴…) |
| `blog_assistant/insights.py` | Claude 노출 이유 분석 (썸네일 이미지 포함) |
| `blog_assistant/references.py` | 레퍼런스 저장·관련도 순 조회 (`references/`) |
| `blog_assistant/writer.py` | 원고(분량 제한) + 썸네일 안 생성 |
| `blog_assistant/thumbnail.py` | 썸네일 안 HTML 시안 |
| `blog_assistant/naver_search.py`, `pipeline.py` | 네이버 검색 API, 수집 연결 |

`references/`에는 남의 글 전문은 저장하지 않고 지표·소제목·도입부 일부·분석 결과만 저장합니다.

## 테스트
```bash
python -m pytest -q
```
