import asyncio
import os
import sqlite3
from datetime import datetime, timedelta
import requests
import pytz
from telegram import Bot

# === 설정 ===
CHECK_INTERVAL = 1800  # 30분
MOVING_AVERAGE_PERIOD = 16  # 5일치(30분 x 16)
ALERT_THRESHOLD = 0.5
JUMP_THRESHOLD = 2.0
DB_FILE = "exchange_rates.db"

# === 텔레그램 설정 ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
chat_ids = os.environ.get("CHAT_IDS", "").split(",") if os.environ.get("CHAT_IDS") else []
bot = Bot(token=TELEGRAM_TOKEN)

# === DB 초기화 ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            timestamp TEXT PRIMARY KEY,
            rate REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# === 환율 저장 ===
def store_rate(rate):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    now = datetime.now(pytz.timezone("Asia/Seoul")).isoformat()
    cur.execute("INSERT OR IGNORE INTO rates (timestamp, rate) VALUES (?, ?)", (now, rate))
    conn.commit()
    conn.close()

# === 환율 불러오기 ===
def load_recent_rates(limit=MOVING_AVERAGE_PERIOD):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT rate FROM rates ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in reversed(rows)]  # 최신 -> 과거 순으로 역전

# === 환율 가져오기 (CurrencyFreaks) ===
def get_usd_krw_exchange_rate():
    api_key = os.environ.get("CURRENCYFREAKS_API_KEY")
    url = f"https://api.currencyfreaks.com/latest?apikey={api_key}&symbols=KRW"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return float(data['rates']['KRW'])
    except Exception as e:
        print("❌ 환율 API 오류:", e)
        return None

# === 텔레그램 알림 ===
async def send_telegram_message(message):
    now = datetime.now(pytz.timezone('Asia/Seoul'))
    if 2 <= now.hour < 7:
        print("🕑 새벽 시간 - 알림 보류")
        return
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id.strip(), text=message)
            print(f"✅ 전송 완료: {chat_id}")
        except Exception as e:
            print(f"❌ 전송 실패: {e}")

# === 이동평균 계산 ===
def calculate_moving_average(rates):
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None
    return sum(rates[-MOVING_AVERAGE_PERIOD:]) / MOVING_AVERAGE_PERIOD

# === 메인 루프 ===
async def main():
    print("🔄 환율 모니터링 시작")
    await send_telegram_message("📡 USD/KRW 환율 모니터링 시작!")

    init_db()

    while True:
        now = datetime.now(pytz.timezone("Asia/Seoul"))
        if 2 <= now.hour < 7:
            print("🌙 새벽 시간 - 휴식 중")
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        rate = get_usd_krw_exchange_rate()
        if rate:
            print(f"📈 현재 환율: {rate:.2f}")
            store_rate(rate)
            recent_rates = load_recent_rates()
            avg = calculate_moving_average(recent_rates)

            if avg:
                deviation = rate - avg
                print(f"📊 이동평균: {avg:.2f}, 편차: {deviation:.2f}")
                if deviation <= -ALERT_THRESHOLD:
                    await send_telegram_message(
                        f"📉 매수 신호!\n현재 환율: {rate:.2f}원\n이동평균: {avg:.2f}원"
                    )
                elif deviation >= ALERT_THRESHOLD:
                    await send_telegram_message(
                        f"📈 매도 신호!\n현재 환율: {rate:.2f}원\n이동평균: {avg:.2f}원"
                    )

                # 📌 직전 값과 급변 감지
                if len(recent_rates) >= 2:
                    prev = recent_rates[-2]
                    diff = rate - prev
                    if diff >= JUMP_THRESHOLD:
                        await send_telegram_message(
                            f"🚨 급등 감지!\n이전: {prev:.2f}원 → 현재: {rate:.2f}원\n(+{diff:.2f}원)"
                        )
                    elif diff <= -JUMP_THRESHOLD:
                        await send_telegram_message(
                            f"🚨 급락 감지!\n이전: {prev:.2f}원 → 현재: {rate:.2f}원\n({diff:.2f}원)"
                        )

        await asyncio.sleep(CHECK_INTERVAL)

# === 실행 ===
if __name__ == "__main__":
    asyncio.run(main())