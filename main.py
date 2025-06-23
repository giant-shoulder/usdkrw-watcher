import asyncio
import os
import sqlite3
import requests
from datetime import datetime
import pytz
from statistics import mean, stdev
from telegram import Bot
from dotenv import load_dotenv
load_dotenv(override=True)  # ✅ 이미 등록된 환경 변수도 덮어씀

# === 설정 ===
DB_FILE = "usdkrw_rates.db"
CHECK_INTERVAL = 260  # 4분20초
MOVING_AVERAGE_PERIOD = 16  # 약 5일치 (30분 간격)
JUMP_THRESHOLD = 1.0  # 급등락 기준

# 텔레그램 & API 설정
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
chat_ids = os.environ.get("CHAT_IDS", "").split(",")

bot = Bot(token=TELEGRAM_TOKEN)

# === DB 초기화 ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                rate REAL NOT NULL
            );
        """)
        conn.commit()

# === 환율 저장 ===
def store_rate(rate):
    now = datetime.now(pytz.timezone("Asia/Seoul")).isoformat()
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO rates (timestamp, rate) VALUES (?, ?)", (now, rate))
        conn.commit()

# === 최근 환율 가져오기 ===
def get_recent_rates(limit):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT rate FROM rates ORDER BY id DESC LIMIT ?", (limit,))
        return [row[0] for row in cursor.fetchall()][::-1]

# === 환율 가져오기 (exchangerate.host)
def get_usdkrw_rate():
    access_key = os.environ.get("EXCHANGERATE_API_KEY")
    if not access_key:
        print("❗ 환경변수 'EXCHANGERATE_API_KEY' 누락")
        return None
    
    url = f"https://api.exchangerate.host/live?access_key={access_key}&currencies=KRW"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        if "quotes" in data and "USDKRW" in data["quotes"]:
            return float(data["quotes"]["USDKRW"])
        else:
            print("❗ quotes 누락:", data)
            return None
    except Exception as e:
        print("❌ API 오류:", e)
        return None

# === 텔레그램 전송 ===
async def send_telegram(msg):
    now = datetime.now(pytz.timezone("Asia/Seoul")).hour
    if 2 <= now < 7:
        print(f"🕑 {now}시 - 알림 제한 시간입니다.")
        return
    for cid in chat_ids:
        try:
            await bot.send_message(chat_id=cid.strip(), text=msg)
            print(f"✅ 전송 완료 → {cid}")
        except Exception as e:
            print(f"❌ 전송 실패 ({cid}): {e}")

# === 분석 함수 ===
def analyze_signals(rates, current_rate):
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None

    ma = mean(rates)
    std = stdev(rates)
    upper = ma + 2 * std
    lower = ma - 2 * std

    messages = []

    # 📉 매수 시그널
    if current_rate < lower and current_rate < ma:
        messages.append(f"🔵📉 매수 시그널 감지!\n현재: {current_rate:.2f}원\n"
                        f"이동평균: {ma:.2f}원\n하단밴드: {lower:.2f}원")

    # 📈 매도 시그널
    elif current_rate > upper and current_rate > ma:
        messages.append(f"🔺📈 매도 시그널 감지!\n현재: {current_rate:.2f}원\n"
                        f"이동평균: {ma:.2f}원\n상단밴드: {upper:.2f}원")

    return messages

# === 메인 루프 ===
async def main():
    print("🔄 USD/KRW 환율 모니터링 시작...")

    # 🆕 전략 설명 포함 메시지
    await send_telegram(
        "👋 USD/KRW 환율 모니터링을 시작합니다!\n\n"
        "📊 전략 안내\n"
        "・4분20초 간격 실시간 조회\n"
        "・5일치 데이터 기반 이동평균 및 볼린저 밴드 계산\n"
        "・📉 매수 알림: 환율이 하단 밴드 이탈 + 평균보다 낮을 때\n"
        "・📈 매도 알림: 환율이 상단 밴드 돌파 + 평균보다 높을 때\n"
        "・⚡ 급변 알림: 4분20초 내 ±1원 이상 변동 시\n\n"
        "※ 새벽 2시~7시는 알림이 일시 중단됩니다. \n"
        "(데이터 조회는 계속 진행됩니다.)"
    )

    last_rate = None
    while True:
        now = datetime.now(pytz.timezone("Asia/Seoul"))
        
        current_rate = get_usdkrw_rate()
        if current_rate:
            print(f"📌 현재 환율: {current_rate:.2f}원")
            store_rate(current_rate)
            recent_rates = get_recent_rates(MOVING_AVERAGE_PERIOD)

            # 📊 이동평균 + 볼린저 밴드 기반 매수/매도 알림
            signals = analyze_signals(recent_rates, current_rate)
            if signals:
                for msg in signals:
                    await send_telegram(msg)

            # ⚡ 급격한 변동
            if last_rate:
                diff = current_rate - last_rate
                if diff > 0:
                    emoji_text = "🔺📈 급변 상승 감지!"  # 상승
                else:
                    emoji_text = "🔵📉 급변 하락 감지!"  # 하락 + 파란색 원

                await send_telegram(
                    f"{emoji_text}\n"
                    f"현재: {current_rate:.2f}원\n"
                    f"이전: {last_rate:.2f}원\n"
                    f"변동: {diff:.2f}원"
                )

            last_rate = current_rate

        await asyncio.sleep(CHECK_INTERVAL)

# === 실행 ===
if __name__ == "__main__":
    init_db()
    asyncio.run(main())