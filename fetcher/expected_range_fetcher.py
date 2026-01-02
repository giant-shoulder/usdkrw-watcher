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
        "https://news.einfomax.co.kr/news/articleList.html?sc_area=A&view_type=sm&sc_word=%ED%99%98%EC%9C%A8+%EC%98%88%EC%83%81"
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

    # 2. 검색 결과에서 기사 후보 링크 여러 개 수집 (배포 환경에서 첫 번째가 무관/유료(단말기) 기사일 수 있음)
    def _normalize_article_url(href: str) -> str:
        if not href:
            return ""
        href = href.strip()
        if href.startswith("http"):
            return href
        return "https://news.einfomax.co.kr" + href

    # 가능한 목록 셀렉터들에서 a[href]를 최대한 많이 모은다.
    link_selectors = [
        "ul.type2 li a[href]",
        "ul.type1 li a[href]",
        "div#section-list li a[href]",
        "div.list li a[href]",
        "div.listing li a[href]",
        "div.article-list a[href]",
        "a[href*='/news/articleView.html']",
    ]

    candidates: list[str] = []
    for sel in link_selectors:
        for a in soup.select(sel):
            href = a.get("href")
            url = _normalize_article_url(href)
            if not url:
                continue
            # 중복 제거
            if url not in candidates:
                candidates.append(url)

    if not candidates:
        snippet = soup.get_text("\n", strip=True)[:400]
        print("[EXPECTED_RANGE] search page status=", res.status_code)
        print("[EXPECTED_RANGE] search page snippet=", snippet)
        raise ValueError("❌ 기사 링크를 찾을 수 없습니다.")

    # 검색 결과 페이지가 의심스러울 때(키워드 미포함/차단 HTML) 후보를 더 넓게 잡되 로그 남김
    if "예상" not in res.text and "레인지" not in res.text and "범위" not in res.text:
        print(f"⚠️ 경고: 검색 결과 페이지가 의심스럽습니다. Status: {res.status_code}")

    # 3. 후보 기사들을 순회하며 '예상 레인지/범위' 패턴이 실제로 존재하는 기사만 채택
    #    (유료 단말기 안내 문구/무관 기사/차단 페이지는 스킵)
    PAYWALL_HINTS = [
        "인포맥스 금융정보 단말기",
        "무단전재",
        "AI 학습 및 활용 금지",
    ]

    article_url = None
    article_soup = None
    body_text = None

    max_probe = min(12, len(candidates))
    for idx, url in enumerate(candidates[:max_probe], start=1):
        try:
            print(f"[EXPECTED_RANGE] probe {idx}/{max_probe}: {url}")
            r = _get(url)
            r.raise_for_status()
            s = BeautifulSoup(r.text, "html.parser")

            # 본문 텍스트 추출
            tmp_body = None
            try:
                tmp_body = _extract_article_text(s)
            except Exception:
                tmp_body = s.get_text("\n", strip=True)

            # 유료/단말기 안내 페이지는 스킵
            if any(hint in (tmp_body or "") for hint in PAYWALL_HINTS) and "예상" not in (tmp_body or ""):
                print("[EXPECTED_RANGE] skip: paywall/terminal-only or irrelevant")
                continue

            # 범위 패턴을 기사별로 선검증 (regex는 아래에서 동일 patterns로 재사용)
            probe_text = tmp_body or ""
            probe_patterns = [
                r"예상\s*(?:환율\s*)?(?:레인지|범위)",
                r"환율\s*예상\s*(?:레인지|범위)",
            ]
            if not any(re.search(p, probe_text) for p in probe_patterns):
                print("[EXPECTED_RANGE] skip: keyword pattern not found")
                continue

            # 후보 채택
            article_url = url
            article_soup = s
            body_text = tmp_body
            break
        except Exception as e:
            print(f"[EXPECTED_RANGE] probe error: {type(e).__name__} - {e}")
            continue

    if not article_url or not article_soup:
        raise ValueError("❌ 기사 링크를 찾았지만, 예상 레인지/범위 패턴이 있는 기사를 찾지 못했습니다.")

    article_res = None  # 아래 코드에서 status/snippet 로깅용 변수를 유지하려면 None 처리

    def _extract_article_text(soup: BeautifulSoup) -> str:
        """Extract main article text as reliably as possible.

        Einfomax pages sometimes include a lot of navigation/boilerplate; also some environments
        may receive a 'block/interstitial' HTML with 200. We try common article containers first.
        """
        candidates = [
            "div#article-view-content-div",          # common on many Korean news CMS
            "div#articleBody",                      # fallback
            "section#article-view-content-div",     # variant
            "div.article-body",                     # generic
            "div.view_cont",                        # generic
            "article",                              # last resort
        ]
        for sel in candidates:
            el = soup.select_one(sel)
            if el:
                txt = el.get_text("\n", strip=True)
                if txt and len(txt) > 200:
                    return txt
        return soup.get_text("\n", strip=True)

    def _debug_context(text: str, keyword: str, width: int = 200) -> str:
        i = text.find(keyword)
        if i < 0:
            return ""
        start = max(0, i - width)
        end = min(len(text), i + len(keyword) + width)
        return text[start:end]

    # 배포 환경에서 종종 200으로 차단/안내 페이지가 내려오는 경우가 있어, 본문이 비정상적으로 짧으면 차단 의심
    if len(body_text) < 300:
        status = getattr(article_res, "status_code", "n/a")
        print("[EXPECTED_RANGE] article page status=", status)
        print("[EXPECTED_RANGE] article page snippet=", body_text[:400])

    # Railway에서만 재현되는 '정상 200인데 내용이 다른' 케이스를 빠르게 판별
    if ("접근" in body_text and "차단" in body_text) or ("Forbidden" in body_text) or ("Cloudflare" in body_text):
        print("[EXPECTED_RANGE] ⚠️ possible block/interstitial page detected")

    # 4. 기사 날짜 확인
    meta_time = article_soup.find("meta", {"property": "article:published_time"})
    content = meta_time.get("content") if meta_time else None
    if not content:
        # fallback: try other common meta/name fields
        meta_alt = (
            article_soup.find("meta", {"name": "article:published_time"})
            or article_soup.find("meta", {"name": "pubdate"})
            or article_soup.find("meta", {"property": "og:updated_time"})
        )
        content = meta_alt.get("content") if meta_alt else None

    if not content:
        raise ValueError("❌ 기사 날짜를 찾을 수 없습니다.")

    article_date = datetime.strptime(content.split("T")[0], "%Y-%m-%d").date()

    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    if article_date != today:
        raise ValueError(f"📅 오늘 기사 아님: {article_date}")

    # 5. 전체 기사 텍스트 추출
    full_text = body_text

    # 6. 정규식으로 예상 레인지 추출 (표기 변형 대응)
    # - '예상 레인지', '예상레인지', '예상 범위', '예상환율 레인지' 등
    # - 구분자: ~, -, –
    # - 단위: '원' 유무
    patterns = [
        r"예상\s*(?:환율\s*)?(?:레인지|범위)\s*[:：]?\s*([\d,\.]+)\s*[~\-–]\s*([\d,\.]+)\s*원?",
        r"(?:레인지|범위)\s*[:：]?\s*([\d,\.]+)\s*[~\-–]\s*([\d,\.]+)\s*원?\s*(?:로|으로)?\s*예상",
    ]

    range_matches = []
    for pat in patterns:
        found = re.findall(pat, full_text)
        if found:
            range_matches.extend(found)

    if not range_matches:
        # Debug: Railway에서 본문은 받아왔는데 키워드/형식이 달라 실패하는 케이스
        ctx1 = _debug_context(full_text, "예상", 250)
        ctx2 = _debug_context(full_text, "레인지", 250)
        ctx3 = _debug_context(full_text, "범위", 250)
        print("[EXPECTED_RANGE] ❌ regex miss - contexts:")
        if ctx1:
            print("[EXPECTED_RANGE] ...around '예상'...\n", ctx1)
        if ctx2:
            print("[EXPECTED_RANGE] ...around '레인지'...\n", ctx2)
        if ctx3:
            print("[EXPECTED_RANGE] ...around '범위'...\n", ctx3)

        # Fallback: 키워드가 있는 경우, 주변에서 '숫자~숫자' 형태를 한 번 더 탐색
        window_text = "\n".join([t for t in [ctx1, ctx2, ctx3] if t]) or full_text
        fallback = re.findall(r"([\d,\.]{3,})\s*[~\-–]\s*([\d,\.]{3,})", window_text)
        if fallback:
            range_matches = fallback
        else:
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