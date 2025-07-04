import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import re

def fetch_expected_range():
    """
    einformax 기사에서 오늘 날짜 기준 예상 환율 범위들을 스크랩해,
    가장 넓은 범위로 정리한 결과를 반환합니다.
    """
    search_url = (
        "https://news.einfomax.co.kr/news/articleList.html"
        "?sc_area=A&view_type=sm&sc_word=%ED%99%98%EC%9C%A8+%EC%98%88%EC%83%81+%EB%A0%88%EC%9D%B8%EC%A7%80"
    )

    res = requests.get(search_url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    article_tag = soup.select_one("ul.type2 li a")
    if not article_tag:
        raise ValueError("기사 링크를 찾을 수 없습니다.")

    article_url = "https://news.einfomax.co.kr" + article_tag.get("href")
    article_res = requests.get(article_url)
    article_res.raise_for_status()
    article_soup = BeautifulSoup(article_res.text, "html.parser")

    content = article_soup.select_one("div#article-view-content-div").text
    range_matches = re.findall(r"예상\s*레인지\s*[:：]?\s*(\d{3,4}\.\d{2})\s*~\s*(\d{3,4}\.\d{2})", content)

    if not range_matches:
        raise ValueError("예상 환율 범위를 찾을 수 없습니다.")

    lows = [float(low) for low, _ in range_matches]
    highs = [float(high) for _, high in range_matches]

    low = min(lows)
    high = max(highs)
    date = datetime.now(pytz.timezone("Asia/Seoul")).date()

    return {
        "date": date,
        "low": low,
        "high": high,
        "source": article_url
    }