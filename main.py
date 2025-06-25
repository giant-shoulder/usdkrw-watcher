import asyncio
import os
import requests
import asyncpg
from datetime import datetime
import pytz
from statistics import mean, stdev
from telegram import Bot
from dotenv import load_dotenv

load_dotenv(override=True)

# 환경 변수
DB_URL = os.environ.get("SUPABASE_DB_URL")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ACCESS_KEY = os.environ.get("EXCHANGERATE_API_KEY")
CHAT_IDS = os.environ.get("CHAT_IDS", "").split(",")

bot = Bot(token=TELEGRAM_TOKEN)

# 설정
CHECK_INTERVAL = 260  # 4분 20초
MOVING_AVERAGE_PERIOD = 36     # 볼린저: 2.5시간
SHORT_TERM_PERIOD = 72         # 골든: 5시간
LONG_TERM_PERIOD = 240         # 데드: 17시간
JUMP_THRESHOLD = 1.0           # 급등/락 기준

bollinger_streak = 0  # 연속 상단 돌파 카운터

# 데이터베이스 연결
async def connect_to_db():
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_host = os.environ.get("DB_HOST")
    db_port = os.environ.get("DB_PORT", "5432")
    db_name = os.environ.get("DB_NAME")

    if not all([db_user, db_password, db_host, db_name]):
        raise ValueError("❗ 환경변수 누락: DB_USER, DB_PASSWORD, DB_HOST, DB_NAME")

    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    # ✅ 실제 연결은 이걸 사용
    # db_url 그대로 사용

    # 🔒 로그 출력 시 비밀번호는 마스킹
    masked_url = f"postgresql://{db_user}:*****@{db_host}:{db_port}/{db_name}"
    print(f"📡 DB 연결 시도 중: {masked_url}")

    conn = await asyncpg.connect(dsn=db_url, statement_cache_size=0)  # 🔧 여기 추가
    return conn

# 환율 가져오기 (API)
def get_usdkrw_rate():
    if not ACCESS_KEY:
        return None
    url = f"https://api.exchangerate.host/live?access_key={ACCESS_KEY}&currencies=KRW"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        return float(data["quotes"]["USDKRW"]) if "quotes" in data and "USDKRW" in data["quotes"] else None
    except Exception as e:
        print("❌ API 오류:", e)
        return None

# 환율 저장 (DB)
async def store_rate(conn, rate):
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    await conn.execute("INSERT INTO rates (timestamp, rate) VALUES ($1, $2)", now, rate)

# 최근 환율 조회 (최신 240개 - 약 17시간)
async def get_recent_rates(conn, limit):
    rows = await conn.fetch("SELECT rate FROM rates ORDER BY timestamp DESC LIMIT $1", limit)
    return [r['rate'] for r in reversed(rows)]

# 텔레그램 알림
async def send_telegram(message):
    hour = datetime.now(pytz.timezone("Asia/Seoul")).hour
    if 2 <= hour < 7:
        return
    for cid in CHAT_IDS:
        try:
            await bot.send_message(chat_id=cid.strip(), text=message)
        except Exception as e:
            print(f"❌ 전송 실패 ({cid}):", e)

# 볼린저 밴드 분석
def analyze_bollinger(rates, current):
    if len(rates) < MOVING_AVERAGE_PERIOD:
        return None, None
    avg = mean(rates)
    std = stdev(rates)
    upper = avg + 2 * std
    lower = avg - 2 * std

    if current > upper:
        status = "upper_breakout"
        message = f"📈 볼린저 밴드 상단 돌파!(매도 검토 시점)\n이동평균: {avg:.2f}\n현재: {current:.2f}\n상단: {upper:.2f}"
    elif current < lower:
        status = "lower_breakout"
        message = f"📉 볼린저 밴드 하단 이탈!(매수 유효 시점)\n이동평균: {avg:.2f}\n현재: {current:.2f}\n하단: {lower:.2f}"
    else:
        status, message = None, None

    return status, message

# 급등/급락 분석
def analyze_jump(prev, current):
    if prev is None:
        return None
    diff = current - prev
    if abs(diff) >= JUMP_THRESHOLD:
        symbol = "🔺📈 단기 급상승!" if diff > 0 else "🔵📉 단기 급하락!"
        return f"{symbol} \n이전: {prev:.2f}\n현재: {current:.2f}\n변동: {diff:.2f}"
    return None

# 골든/데드 크로스 분석
def analyze_cross(rates, prev_s, prev_l):
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_s, prev_l
    short = mean(rates[-SHORT_TERM_PERIOD:])
    long = mean(rates[-LONG_TERM_PERIOD:])
    signal = None
    if prev_s and prev_l:
        if short > long and prev_s <= prev_l:
            return f"🟢 골든크로스 발생! 장기 상승 전환 신호입니다.\n단기: {short:.2f} > 장기: {long:.2f}", short, long
        elif short < long and prev_s >= prev_l:
            return f"🔴 데드크로스 발생! 하락 전환 가능성.\n단기: {short:.2f} < 장기: {long:.2f}", short, long
    return signal, short, long

# 복합 전략 분석
def analyze_combo(b_msg, j_msg, c_msg):
    signals = {
        "bollinger": b_msg,
        "jump": j_msg,
        "cross": c_msg
    }

    active_signals = {k: v for k, v in signals.items() if v}
    match_count = len(active_signals)

    if match_count < 2:
        return None  # 2개 이상 일치해야 복합 전략 알림

    header = "📊 복합 전략 감지 (2개 일치)" if match_count == 2 else "🚨 강력한 복합 전략 감지 (3개 일치)"

    detail_lines = [v for v in active_signals.values()]
    summary = "\n".join(detail_lines)

    # 방향성 판단 (매수/매도)
    is_buy = all("하단" in v or "하락" in v or "골든크로스" in v for v in detail_lines)
    is_sell = all("상단" in v or "상승" in v or "데드크로스" in v for v in detail_lines)

    if is_buy:
        action_line = "🟢 매수 진입 타이밍으로 판단됩니다."
    elif is_sell:
        action_line = "🔴 매도 고려 타이밍으로 판단됩니다."
    else:
        action_line = "⚠️ 전략 간 상충이 있어 주의가 필요합니다."

    return f"{header}\n{summary}\n\n{action_line}"

# 연속 상단 돌파 + 골든크로스/급락 분석
def analyze_streak_logic(streak, cross_signal, jump_signal):
    if streak >= 3 and cross_signal == "🟢 골든크로스 발생":
        return "🔥 강력한 매수 신호: 연속 상단 돌파 + 골든크로스"
    elif streak >= 3 and not jump_signal:
        return "👀 관망 필요: 연속 상단 돌파만 감지됨 (추격매수 주의)"
    elif streak >= 1 and jump_signal and "급하락" in jump_signal:
        return "⚠️ 단기 조정 가능성: 상단 돌파 후 급하락"
    return None

# 메인 루프
async def main():
    await send_telegram(
        "👋 USD/KRW 환율 모니터링을 시작합니다!\n\n"
        "📊 [알림 기준 안내]\n"
        "• 📉 *환율이 평소보다 많이 떨어지거나*\n"
        "• 📈 *갑자기 크게 오르거나*\n"
        "• 🔁 *최근 평균선이 장기 평균선을 뚫고 올라가거나 내려갈 때*\n"
        "➡️ 이런 변화가 생기면 텔레그램으로 바로 알려드려요!\n\n"
        "📦 전략 설명:\n"
        "• 볼린저 밴드: 최근 2.5시간 기준, 평소보다 너무 낮거나 높을 때\n"
        "• 급격한 변동: 바로 직전보다 1원 이상 오르거나 내릴 때\n"
        "• 골든/데드크로스: 단기 평균(5시간)이 장기 평균(17시간)보다 크거나 작아질 때\n"
        "• 조합 전략: 위 조건 중 2가지 이상이 동시에 나타나면 추가 알림 발송\n\n"
        f"⏱️ 확인 주기: {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 체크합니다"
    )

    conn = await connect_to_db()
    prev_rate = None
    prev_sma, prev_lma = None, None
    global bollinger_streak

    while True:
        rate = get_usdkrw_rate()
        rate = get_usdkrw_rate()
        if rate:
            print(f"📈 API 조회된 환율: {rate}")
        else:
            print("❌ 환율 조회 실패 (None 반환됨)")
        if rate:
            await store_rate(conn, rate)
            rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

            b_status, b_message = analyze_bollinger(rates, rate)
            j_msg = analyze_jump(prev_rate, rate)
            c_msg, prev_sma, prev_lma = analyze_cross(rates, prev_sma, prev_lma)

            # streak 관리
            if b_status == "upper_breakout":
                bollinger_streak += 1
            else:
                bollinger_streak = 0

            # 개별 알림
            if b_message: await send_telegram(b_message)
            if j_msg: await send_telegram(j_msg)
            if c_msg: await send_telegram(c_msg)

            # 조합
            combo = analyze_combo(b_message, j_msg, c_msg)
            if combo: await send_telegram(combo)

            # 연속 돌파 + 분석
            streak_msg = analyze_streak_logic(bollinger_streak, c_msg, j_msg)
            if streak_msg: await send_telegram(streak_msg)

            prev_rate = rate

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())