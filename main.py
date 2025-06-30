import asyncio
import os
import requests
import asyncpg
from datetime import datetime
import time
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
CHECK_INTERVAL = 200           # 3분 20초
MOVING_AVERAGE_PERIOD = 45     # 볼린저: 2.5시간
SHORT_TERM_PERIOD = 90         # 단기 평균선 (골든/데드 크로스 비교 대상): 5시간
LONG_TERM_PERIOD = 306         # 장기 평균선 (골든/데드 크로스 기준선): 17시간
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
def get_usdkrw_rate(retries=3, delay=2):
    """
    환율 API 호출: 실패 시 최대 `retries`만큼 재시도
    :param retries: 최대 재시도 횟수
    :param delay: 실패 후 대기 시간 (초)
    :return: 환율 (float) 또는 None
    """
    if not ACCESS_KEY:
        print("❌ ACCESS_KEY가 설정되지 않았습니다.")
        return None

    url = f"https://api.exchangerate.host/live?access_key={ACCESS_KEY}&currencies=KRW"

    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            data = res.json()
            rate = data.get("quotes", {}).get("USDKRW")
            if rate is not None:
                return float(rate)
            else:
                print(f"⚠️ 응답에 USDKRW 정보 없음 (시도 {attempt})")
        except Exception as e:
            print(f"❌ API 호출 오류 (시도 {attempt}): {e}")

        if attempt < retries:
            print(f"⏳ {delay}초 후 재시도...")
            time.sleep(delay)

    print("🚫 모든 시도 실패 - 환율 조회 불가")
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
        message = f"📈 볼린저 밴드 상단 돌파!\n이동평균: {avg:.2f}\n현재: {current:.2f}\n상단: {upper:.2f}"
    elif current < lower:
        status = "lower_breakout"
        message = f"📉 볼린저 밴드 하단 이탈!\n이동평균: {avg:.2f}\n현재: {current:.2f}\n하단: {lower:.2f}"
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
        return f"{symbol} \n현재: {current:.2f}\n이전: {prev:.2f}\n변동: {diff:.2f}"
    return None

# 골든/데드 크로스 분석
def analyze_cross(rates, prev_short_avg, prev_long_avg):
    """
    골든/데드크로스 감지 및 메시지 생성

    골든크로스: 단기 이동평균선이 장기선을 상향 돌파 → 매수 시그널  
    데드크로스: 단기 이동평균선이 장기선을 하향 돌파 → 매도 시그널
    """
    if len(rates) < LONG_TERM_PERIOD:
        return None, prev_short_avg, prev_long_avg

    # 현재 이동평균 계산
    short_ma = mean(rates[-SHORT_TERM_PERIOD:])
    long_ma = mean(rates[-LONG_TERM_PERIOD:])
    signal = None

    if prev_short_avg is not None and prev_long_avg is not None:
        crossed_up = short_ma > long_ma and prev_short_avg <= prev_long_avg
        crossed_down = short_ma < long_ma and prev_short_avg >= prev_long_avg

        if crossed_up:
            signal = (
                "🟢 *골든크로스 발생!* 장기 상승 전환 신호입니다.\n"
                "📈 단기 평균선이 장기 평균선을 상향 돌파했어요.\n"
                "💡 *매수 시그널입니다.*\n"
                f"📊 이동평균선 비교\n단기: {short_ma:.2f} > 장기: {long_ma:.2f}"
            )
        elif crossed_down:
            signal = (
                "🔴 *데드크로스 발생!* 하락 전환 가능성이 있습니다.\n"
                "📉 단기 평균선이 장기 평균선을 하향 돌파했어요.\n"
                "💡 *매도 시그널입니다.*\n"
                f"📊 이동평균선 비교\n단기: {short_ma:.2f} < 장기: {long_ma:.2f}"
            )

    return signal, short_ma, long_ma

# 복합 전략 분석
def analyze_combo(b_msg, j_msg, c_msg):
    """
    복합 전략 분석 (2개 이상 일치 시 텔레그램 시각화 메시지 생성 + 강도 점수화)
    """

    signals = {
        "📊 볼린저 밴드": b_msg,
        "⚡ 급변 감지": j_msg,
        "🔁 이동평균선 크로스": c_msg
    }

    active_signals = {k: v for k, v in signals.items() if v}
    match_count = len(active_signals)

    if match_count < 2:
        return None  # 전략 2개 이상 일치해야 복합 분석 진행

    # 전략별 가중치 (조정 가능)
    weights = {
        "📊 볼린저 밴드": 30,
        "⚡ 급변 감지": 20,
        "🔁 이동평균선 크로스": 50
    }
    total_score = sum(weights.get(k, 0) for k in active_signals)

    # 점수 기반 헤더
    if total_score >= 80:
        header = "🔥 *[강력한 복합 전략 감지]*"
    elif total_score >= 60:
        header = "🔍 *[주의할 복합 전략 감지]*"
    else:
        header = "⚠️ *[약한 복합 전략 신호]*"

    # 상세 전략 요약
    detail_lines = [f"{k}\n{v}" for k, v in active_signals.items()]
    summary = "\n\n".join(detail_lines)

    # 방향성 판단 키워드
    buy_keywords = {"하단", "하락", "골든크로스", "급반등", "반전", "저점"}
    sell_keywords = {"상단", "상승", "데드크로스", "급락", "고점"}

    def contains_keywords(msg, keywords):
        if not msg:
            return False
        return any(kw in msg for kw in keywords)

    buy_score = sum(contains_keywords(v, buy_keywords) for v in active_signals.values())
    sell_score = sum(contains_keywords(v, sell_keywords) for v in active_signals.values())

    # 방향성 판별
    if buy_score > 0 and sell_score == 0:
        action_type = "buy"
        action_line = "🟢 *매수 진입 타이밍으로 판단됩니다.*"
    elif sell_score > 0 and buy_score == 0:
        action_type = "sell"
        action_line = "🔴 *매도 고려 타이밍으로 판단됩니다.*"
    elif buy_score > 0 and sell_score > 0:
        action_type = "conflict"
        action_line = (
            "⚠️ *전략 간 방향성이 상충됩니다.*\n"
            "💡 서로 다른 시그널이 동시에 감지되어, 섣부른 진입보다는 관망이 권장됩니다."
        )
    else:
        action_type = "neutral"
        action_line = "ℹ️ *명확한 방향성이 없습니다. 관망을 권장합니다.*"

    # 점수 시각화 바
    score_bar = get_score_bar(
        score=total_score,
        signal_type=action_type,
        max_score=100,
        bar_length=20
    )

    # 전체 메시지 조합
    full_message = (
        f"{header}\n\n"
        f"{summary}\n\n"
        f"{action_line}\n\n"
        f"🧮 신호 점수: *{total_score}점*\n"
        f"{score_bar}"
    )

    return {
        "message": full_message,
        "type": action_type,
        "score": total_score,
        "match_count": match_count,
        "details": active_signals
    }

# 점수 시각화 바 생성
def get_score_bar(score, signal_type="neutral", max_score=100, bar_length=10):
    """
    텔레그램 메시지용 색상 이모지 기반 시각화 바 + 신호 방향 텍스트 포함
    """
    filled_len = int(round(bar_length * score / float(max_score)))

    fill_chars = {
        "buy": "🟩",
        "sell": "🟥",
        "conflict": "🟨",
        "neutral": "⬜"
    }
    empty_char = "⬛"
    fill_char = fill_chars.get(signal_type, "⬜")

    bar_body = fill_char * filled_len + empty_char * (bar_length - filled_len)

    direction_label = {
        "buy": "🟢 매수 신호 강도",
        "sell": "🔴 매도 신호 강도",
        "conflict": "⚠️ 전략간 방향성 충돌 강도",
        "neutral": "⬜ 신호 강도"
    }.get(signal_type, "⬜ 신호 강도")

    return f"{direction_label}\n{bar_body} {score}점"

# 연속 상단/하단 돌파 + 크로스/급변 조건에 따른 종합 판단
def analyze_streak_logic(upper_streak, lower_streak, cross_signal, jump_signal):
    """
    연속 상단/하단 돌파 + 크로스/급변 조건에 따른 종합 판단
    """

    is_golden = cross_signal and "골든크로스" in cross_signal
    is_dead = cross_signal and "데드크로스" in cross_signal
    is_crash = jump_signal and "급하락" in jump_signal
    is_surge = jump_signal and "급상승" in jump_signal

    # ✅ 1. 상단 돌파 + 골든크로스
    if upper_streak >= 3 and is_golden:
        return (
            "🔥 *강력한 매수 신호!* 최근 3회 이상 연속 상단 돌파와\n"
            "골든크로스가 함께 감지되었습니다.\n"
            "💡 *상승 추세 진입 가능성이 높습니다.*"
        )

    # ✅ 2. 상단 돌파 반복 단계별 대응 (추격매수 주의)
    if upper_streak >= 7 and not is_golden and not is_crash:
        return (
            "🚨 *상단 과열 경고!* 상단 돌파가 7회 이상 반복 중입니다.\n"
            "📈 단기 고점 가능성이 높으며 급락 위험에 주의가 필요합니다.\n"
            "💡 *익절 및 리스크 점검을 권장합니다.*"
        )
    elif upper_streak >= 5 and not is_golden and not is_crash:
        return (
            "⚠️ *과열 조짐:* 상단 돌파가 5회 이상 반복 중입니다.\n"
            "📈 추세가 이어질 수 있지만 과매수 구간일 수 있습니다.\n"
            "💡 *보수적 대응을 추천합니다.*"
        )
    elif upper_streak >= 3 and not is_golden and not is_crash:
        return (
            "👀 *관망 신호:* 연속 상단 돌파가 감지되었지만\n"
            "추가 상승의 명확한 근거는 부족합니다.\n"
            "⚠️ *추격 매수는 신중히 판단하세요.*"
        )

    # ✅ 3. 상단 돌파 중 급하락
    if upper_streak >= 2 and is_crash:
        return (
            "⚠️ *가짜 돌파 주의!* 상단 돌파 이후 급하락이 감지되었습니다.\n"
            "📉 고점 반전 가능성에 유의하세요."
        )

    # ✅ 4. 하단 이탈 + 데드크로스
    if lower_streak >= 3 and is_dead:
        return (
            "🔻 *하락 경고 신호:* 최근 3회 이상 연속 하단 이탈과 함께\n"
            "데드크로스가 감지되었습니다.\n"
            "💡 *추세적 하락 가능성에 유의하세요.*"
        )

    # ✅ 5. 하단 이탈 반복 단계별 대응
    if lower_streak >= 7 and not is_dead and not is_surge:
        return (
            "🚨 *강력한 하락 경고!* 하단 이탈이 7회 이상 반복되고 있습니다.\n"
            "📉 단기 하락 확증 가능성이 높으며 손절 기준 점검이 필요합니다.\n"
            "💡 *추가 손실 방지에 대비하세요.*"
        )
    elif lower_streak >= 5 and not is_dead and not is_surge:
        return (
            "⚠️ *지속적 하락 조짐:* 하단 이탈이 5회 이상 반복되고 있습니다.\n"
            "📉 반등 징후 없이 하락세 지속 시 주의가 필요합니다.\n"
            "💡 *진입 자제 및 보수적 대응 권장.*"
        )
    elif lower_streak >= 3 and not is_dead and not is_surge:
        return (
            "🧊 *하단 이탈 반복 감지됨.*\n"
            "아직 명확한 추가 하락 근거는 없지만 주의가 필요합니다.\n"
            "⚠️ 저점 확인 전까지 관망을 추천합니다."
        )

    # ✅ 6. 하단 이탈 + 급반등
    if lower_streak >= 2 and is_surge and not is_golden:
        return (
            "📈 *급반등 주의:* 하단 이탈 중 갑작스러운 급상승이 감지되었습니다.\n"
            "💡 일시적 반등일 수 있으며 확인이 필요합니다."
        )

    # ✅ 7. 하단 이탈 → 급반등 → 골든크로스
    if lower_streak >= 2 and is_surge and is_golden:
        return (
            "🟢 *바닥 반등 + 골든크로스 감지!*\n"
            "📈 하단 이탈 이후 급반등과 골든크로스가 동시에 나타났습니다.\n"
            "💡 *단기 저점 탈출 및 반전 가능성이 있습니다.*"
        )

    # ✅ 8. 상단 돌파 + 골든크로스 이후 급하락
    if upper_streak >= 2 and is_golden and is_crash:
        return (
            "⚠️ *과열 후 급락 조짐:* 상단 돌파 + 골든크로스 이후 급하락 발생.\n"
            "📉 고점 반전 가능성. 단기 리스크 확대에 주의하세요."
        )

    return None

# 주말 확인 함수
def is_weekend():
    """토요일(5), 일요일(6)에는 True 반환"""
    now = datetime.now(pytz.timezone("Asia/Seoul"))
    return now.weekday() >= 5

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
        f"⏱️ 확인 주기: {CHECK_INTERVAL // 60}분 {CHECK_INTERVAL % 60}초마다 체크합니다\n"
        "🌙 *단, 주말 전체와 평일 오전 2시부터 7시까지는 알림이 일시 중단됩니다.*"
    )

    conn = await connect_to_db()
    prev_rate = None
    prev_short_avg, prev_long_avg = None, None
    upper_streak = 0
    lower_streak = 0

    while True:
        if is_weekend():
            print(f"[{datetime.now()}] ⏸️ 주말, API 호출 중지 중...")
            await asyncio.sleep(CHECK_INTERVAL)
            continue

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
            c_msg, prev_short_avg, prev_long_avg = analyze_cross(rates, prev_short_avg, prev_long_avg)

            # streak 관리
            if b_status == "upper_breakout":
                upper_streak += 1
                lower_streak = 0
            elif b_status == "lower_breakout":
                lower_streak += 1
                upper_streak = 0
            else:
                upper_streak = 0
                lower_streak = 0

            # 개별 알림
            if b_message: await send_telegram(b_message)
            if j_msg: await send_telegram(j_msg)
            if c_msg: await send_telegram(c_msg)

            # 조합 전략 분석 및 시각화 전송
            combo_result = analyze_combo(b_message, j_msg, c_msg)
            if combo_result:
                await send_telegram(combo_result["message"])

            # 연속 전략 분석
            streak_msg = analyze_streak_logic(
                upper_streak, lower_streak,
                cross_signal=c_msg,
                jump_signal=j_msg
            )
            if streak_msg:
                await send_telegram(streak_msg)

            prev_rate = rate

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())