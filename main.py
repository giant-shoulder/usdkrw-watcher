import asyncio
from datetime import datetime
from config import CHECK_INTERVAL, LONG_TERM_PERIOD
from utils import is_weekend
from db import connect_to_db, store_rate, get_recent_rates
from fetcher import get_usdkrw_rate
from notifier import send_telegram, send_start_message
from strategies import (
    analyze_bollinger,
    analyze_jump,
    analyze_crossover,
    analyze_combo
)

async def run_watcher():
    await send_start_message()

    conn = await connect_to_db()
    prev_rate = None
    prev_short_avg, prev_long_avg = None, None
    upper_streak = 0
    lower_streak = 0
    prev_upper_level = 0
    prev_lower_level = 0

    while True:
        if is_weekend():
            print(f"[{datetime.now()}] ⏸️ 주말, 알림 일시 정지 중...")
            await asyncio.sleep(CHECK_INTERVAL)
            continue

        rate = get_usdkrw_rate()
        if rate:
            print(f"[{datetime.now()}] 📈 환율: {rate}")
            await store_rate(conn, rate)
            rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

            # 전략별 분석
            b_status, b_msg = analyze_bollinger(rates, rate, prev=prev_rate)
            j_msg = analyze_jump(prev_rate, rate)
            c_msg, prev_short_avg, prev_long_avg = analyze_crossover(
                rates, prev_short_avg, prev_long_avg
            )

            # streak 추적
            if b_status == "upper_breakout":
                upper_streak += 1
                lower_streak = 0
            elif b_status == "lower_breakout":
                lower_streak += 1
                upper_streak = 0
            else:
                upper_streak = 0
                lower_streak = 0

            # 단일 전략 메시지 전송
            for msg in [b_msg, j_msg, c_msg]:
                if msg:
                    await send_telegram(msg)

            # 통합 전략 분석
            result = analyze_combo(
                b_status, b_msg, j_msg, c_msg,
                upper_streak, lower_streak,
                prev_upper_level, prev_lower_level
            )

            if result:
                prev_upper_level = result["new_upper_level"]
                prev_lower_level = result["new_lower_level"]
                await send_telegram(result["message"])

            prev_rate = rate
        else:
            print(f"[{datetime.now()}] ❌ 환율 조회 실패")

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_watcher())