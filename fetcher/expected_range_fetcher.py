from curl_cffi import requests # 변경
from bs4 import BeautifulSoup
import re
from datetime import datetime
import pytz
import time as pytime
from typing import Optional

def fetch_expected_range():
    # 헤더는 그대로 두거나 최소화해도 됨 (impersonate가 알아서 처리함)
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://news.einfomax.co.kr/",
    }
    
    search_url = (
        "https://news.einfomax.co.kr/news/articleList.html?sc_area=A&view_type=sm&sc_word=%ED%99%98%EC%9C%A8+%EC%98%88%EC%83%81+%EB%A0%88%EC%9D%B8%EC%A7%80"
    )

    # requests.Session() 대신 curl_cffi 사용
    session = requests.Session()

    def _get(url: str, *, timeout: int = 15, retries: int = 3):
        last_err: Optional[Exception] = None
        for i in range(retries):
            try:
                # impersonate="chrome" 옵션이 핵심입니다.
                r = session.get(
                    url, 
                    headers=headers, 
                    impersonate="chrome", 
                    timeout=timeout, 
                    allow_redirects=True
                )
                if r.status_code >= 400:
                    r.raise_for_status()
                return r
            except Exception as e:
                last_err = e
                print(f"Retry {i+1} failed: {e}")
                pytime.sleep(1)
        raise last_err

    # ... (나머지 로직은 동일) ...
    res = _get(search_url)
    
    # 디버깅용 로그 (배포 환경에서 확인용)
    if "예상" not in res.text and "레인지" not in res.text:
        print(f"⚠️ 경고: 검색 결과 페이지가 의심스럽습니다. Status: {res.status_code}")
        # print(res.text[:500]) # HTML 앞부분 확인
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # 2. 최신 기사 링크 추출 (배포 환경에서 HTML 구조/차단 페이지 대응)
    article_tag = (
        soup.select_one("ul.type2 li a")
        or soup.select_one("ul.type1 li a")
        or soup.select_one("div#section-list li a")
        or soup.select_one("div.list li a")
        or soup.select_one("div.listing li a")
    )

    href = article_tag.get("href") if article_tag else None
    if not href:
        # Railway/클라우드 환경에서 차단/리다이렉트/비정상 HTML인지 빠르게 확인할 수 있게 일부 출력
        snippet = soup.get_text("\n", strip=True)[:400]
        print("[EXPECTED_RANGE] search page status=", res.status_code)
        print("[EXPECTED_RANGE] search page snippet=", snippet)
        raise ValueError("❌ 기사 링크를 찾을 수 없습니다.")

    # 절대/상대 URL 모두 처리
    if href.startswith("http"):
        article_url = href
    else:
        article_url = "https://news.einfomax.co.kr" + href

    article_res = _get(article_url)
    article_res.raise_for_status()
    article_soup = BeautifulSoup(article_res.text, "html.parser")

    # 배포 환경에서 종종 200으로 차단 페이지가 내려오는 경우가 있어, 본문이 비정상적으로 짧으면 차단 의심
    body_text = article_soup.get_text("\n", strip=True)
    if len(body_text) < 300:
        print("[EXPECTED_RANGE] article page status=", article_res.status_code)
        print("[EXPECTED_RANGE] article page snippet=", body_text[:400])

    # 4. 기사 날짜 확인
    meta_time = article_soup.find("meta", {"property": "article:published_time"})
    if not meta_time or not meta_time.get("content"):
        raise ValueError("❌ 기사 날짜를 찾을 수 없습니다.")
    article_date = datetime.strptime(meta_time["content"].split("T")[0], "%Y-%m-%d").date()

    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    if article_date != today:
        raise ValueError(f"📅 오늘 기사 아님: {article_date}")

    # 5. 전체 기사 텍스트 추출
    full_text = body_text

    # 6. 정규식으로 예상 레인지 추출 (쉼표 포함 숫자 대응)
    range_matches = re.findall(
        r"예상\s*레인지\s*[:：]?\s*([\d,\.]+)\s*[~\-]\s*([\d,\.]+)",
        full_text
    )
    if not range_matches:
        raise ValueError("❌ 예상 환율 범위를 찾을 수 없습니다.")

    # 7. 쉼표 제거 및 float 변환
    ranges = []
    for low, high in range_matches:
        try:
            low_clean = float(low.replace(",", ""))
            high_clean = float(high.replace(",", ""))
            ranges.append((low_clean, high_clean))
        except ValueError:
            continue

    if not ranges:
        raise ValueError("❌ 유효한 숫자 형식의 범위를 추출하지 못했습니다.")

    # 8. 가장 넓은 범위 계산
    low = min(l for l, _ in ranges)
    high = max(h for _, h in ranges)

    print("✅ 스크래핑된 예상 환율 레인지:", ranges)

    return {
        "date": today,
        "low": low,
        "high": high,
        "source": article_url,
    }