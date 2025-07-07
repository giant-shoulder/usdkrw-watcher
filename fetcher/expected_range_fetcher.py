import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import pytz

def fetch_expected_range():
    """
    연합인포맥스에서 '오늘 외환딜러 환율 예상레인지' 기사를 스크래핑하여
    가장 넓은 환율 범위를 반환합니다.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    search_url = (
        "https://news.einfomax.co.kr/news/articleList.html"
        "?sc_area=A&view_type=sm&sc_word=%ED%99%98%EC%9C%A8+%EC%98%88%EC%83%81+%EB%A0%88%EC%9D%B8%EC%A7%80"
    )

    # 1. 기사 검색 페이지 요청
    res = requests.get(search_url, headers=headers)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # 2. 최신 기사 링크 추출
    article_tag = soup.select_one("ul.type2 li a")
    if not article_tag or not article_tag.get("href"):
        raise ValueError("❌ 기사 링크를 찾을 수 없습니다.")
    article_url = "https://news.einfomax.co.kr" + article_tag["href"]

    # 3. 기사 본문 요청
    article_res = requests.get(article_url, headers=headers)
    article_res.raise_for_status()
    article_soup = BeautifulSoup(article_res.text, "html.parser")

    # 4. 기사 날짜 확인
    meta_time = article_soup.find("meta", {"property": "article:published_time"})
    if not meta_time or not meta_time.get("content"):
        raise ValueError("❌ 기사 날짜를 찾을 수 없습니다.")
    article_date = datetime.strptime(meta_time["content"].split("T")[0], "%Y-%m-%d").date()

    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    if article_date != today:
        raise ValueError(f"📅 오늘 기사 아님: {article_date}")

    # 5. 전체 기사 텍스트 추출
    full_text = article_soup.get_text(separator="\n", strip=True)

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