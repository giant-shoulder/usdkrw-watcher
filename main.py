import asyncio
import os
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service  # ✅ 필수!
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from playwright.async_api import async_playwright

from telegram import Bot
from datetime import datetime
import pytz

# 📌 설정
INVESTING_URL = "https://www.investing.com/currencies/usd-krw"
CHECK_INTERVAL = 180  # 3분마다 확인
ALERT_THRESHOLD = 0.5  # 0.5원 이상 변동 시 알림
last_rate = None

# 텔레그램 설정
# TELEGRAM_TOKEN = '7886487476:AAGVZNaFtUdzqR5o9AWbBNHFV5bJy4ph2sM'
# CHAT_IDS = ['7650730456', '70421286']

# railway 환경 변수에서 토큰과 채팅 ID 가져오기
# 텔레그램 봇 토큰
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# 여러 사용자 chat_id 목록 (쉼표로 구분하여 환경변수에 저장: 예 "123,456,789")
chat_id_list_str = os.environ.get("CHAT_IDS", "")
chat_ids = chat_id_list_str.split(",") if chat_id_list_str else []

bot = Bot(token=TELEGRAM_TOKEN)

# ✅ 환율 가져오기
def get_usd_krw():
    try:
        options = Options()
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1280,800')

        # ✅ 올바른 방식: Service 클래스로 wrapping
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        driver.get("https://www.investing.com/currencies/usd-krw")

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "span[data-test='instrument-price-last']"))
        )

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        rate_tag = soup.find("span", {"data-test": "instrument-price-last"})
        if rate_tag:
            return float(rate_tag.text.replace(',', ''))
        return None
    except Exception as e:
        print("❌ 환율 가져오기 실패:", e)
        return None
    
def get_usd_krw_by_requests():
    try:
        url = "https://www.investing.com/currencies/usd-krw"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.google.com",
        }

        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        rate_tag = soup.find("span", {"data-test": "instrument-price-last"})

        if rate_tag:
            rate = float(rate_tag.text.replace(',', ''))
            print(f"✅ 환율 추출 성공: {rate}원")
            return rate
        else:
            print("❗ 환율 태그를 찾을 수 없습니다.")
            return None

    except Exception as e:
        print("❌ requests 방식 실패:", e)
        return None
    


async def get_usd_krw_playwright():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.investing.com/currencies/usd-krw", timeout=30000)

            # 👉 'visible' 대신 'attached'로 상태 변경
            selector = "div[data-test='instrument-price-last']"
            await page.wait_for_selector(selector, timeout=20000, state='attached')

            # inner_text 추출
            rate_str = await page.locator(selector).inner_text()
            await browser.close()

            rate = float(rate_str.replace(',', ''))
            print(f"✅ 환율 추출 성공: {rate}원")
            return rate

    except Exception as e:
        print("❌ 환율 가져오기 실패:", e)
        return None
    
async def get_usd_krw_from_naver():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            url = "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"
            print(f"🌐 접속 중: {url}")
            await page.goto(url, timeout=30000)

            await page.wait_for_selector("span.value", timeout=10000)
            rate_str = await page.locator("span.value").inner_text()

            rate = float(rate_str.replace(',', ''))
            print(f"✅ 현재 환율: {rate}원")
            await browser.close()
            return rate

    except Exception as e:
        print("❌ 환율 가져오기 실패:", e)
        return None

def get_usd_krw_exchange_rate():
    ACCESS_KEY = "0314d1fcbedcebe9b2febd2cae0f8958"
    url = f"http://api.exchangerate.host/live?access_key={ACCESS_KEY}&currencies=KRW"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 보호적 접근
        if "quotes" in data and "USDKRW" in data["quotes"]:
            rate = float(data["quotes"]["USDKRW"])
            print(f"💵 환율: {rate}")
            return rate
        else:
            print("❗ quotes 항목이 없음:", data)
            return None

    except Exception as e:
        print("❌ API 요청 실패:", e)
        return None

# ✅ 텔레그램 메시지 발송
# 알림 전송 함수 내부에 시간 체크 추가
async def send_telegram_message(message):
    # 한국 시간 기준으로 현재 시간 확인
    now = datetime.now(pytz.timezone('Asia/Seoul'))
    current_hour = now.hour

    # 새벽 1시부터 7시까지는 알림 차단
    if 1 <= current_hour < 7:
        print(f"🕐 현재 시각 {current_hour}시 - 알림 발송 시간 아님")
        return

    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id.strip(), text=message)
            print(f"✅ 전송 완료 → {chat_id}")
        except Exception as e:
            print(f"❌ 전송 실패 ({chat_id}): {e}")

# ✅ 메인 루프
async def main():
    global last_rate
    print("🔄 환율 모니터링 시작...")
    await send_telegram_message(f"👋 USD/KRW 환율 모니터링을 시작합니다!\n환율 변동 폭이 {CHECK_INTERVAL/60}분 단위로 {ALERT_THRESHOLD}원 이상일 때 알림을 드립니다.")

    while True:
        current_rate = get_usd_krw_exchange_rate()
        if current_rate:
            print(f"💵 현재 환율: {current_rate}원")
            if last_rate is not None:
                diff = abs(current_rate - last_rate)
                if diff >= ALERT_THRESHOLD:
                    msg = f"💱 환율 변동 감지!\n현재: {current_rate:.2f}원\n이전: {last_rate:.2f}원\n변동: {current_rate - last_rate:.2f}원"
                    await send_telegram_message(msg)
            last_rate = current_rate
        await asyncio.sleep(CHECK_INTERVAL)

# ✅ 실행
if __name__ == "__main__":
    asyncio.run(main())