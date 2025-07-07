import asyncio
from datetime import datetime
from config import CHECK_INTERVAL, LONG_TERM_PERIOD
from strategies.utils.streak import get_streak_advisory
from utils import is_weekend, now_kst, is_scrape_time
from fetcher import get_usdkrw_rate, fetch_expected_range
from db import (
    connect_to_db, close_db_connection,
    store_rate, get_recent_rates, store_expected_range, get_today_expected_range
)
from notifier import send_telegram, send_start_message
from strategies import (
    analyze_bollinger,
    analyze_jump,
    analyze_crossover,
    analyze_combo,
    analyze_expected_range
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
    # 스크랩 시간 중복 실행 방지를 위한 상태 변수
    last_scraped_date = None


    try:
        while True:
            now = now_kst()
            if is_weekend():
                print(f"[{now}] ⏸️ 주말, 알림 일시 정지 중...")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            # ✅ 오전 11시대 스크랩 조건 확인
            # if is_scrape_time(last_scraped_date):
            #     try:
            #         # 예상 환율 레인지 스크래핑 및 저장
            #         result = await store_expected_range(conn)

            #         # 텔레그램 알림 메시지 구성 및 발송
            #         msg = (
            #             "📊 *오늘의 예상 환율 레인지*\n"
            #             f"• 하단: *{result['low']:.2f}원*\n"
            #             f"• 상단: *{result['high']:.2f}원*\n"
            #             f"출처: {result['source']}"
            #         )
            #         await send_telegram(msg)

            #         last_scraped_date = now.date()
            #     except Exception as e:
            #         await send_telegram(f"⚠️ 예상 환율 레인지 스크래핑 실패: {e}")

            rate = get_usdkrw_rate()
            if rate:
                print(f"[{now}] 📈 환율: {rate}")
                await store_rate(conn, rate)
                rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

                # 예상 범위 벗어남 감지
                expected_range = await get_today_expected_range(conn)
                e_msg = analyze_expected_range(rate, expected_range)
                if e_msg:
                    await send_telegram(e_msg)

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

                # streak 기반 추가 경고 판단 (✅ 복합 조건 없어도 수행됨)
                new_upper_level, new_lower_level, streak_msg = get_streak_advisory(
                    upper_streak, lower_streak,
                    cross_msg=c_msg,
                    jump_msg=j_msg,
                    prev_upper=prev_upper_level,
                    prev_lower=prev_lower_level
                )

                if streak_msg:
                    await send_telegram(f"🧭 *동일 신호 반복 알림:*\n{streak_msg}")
                    prev_upper_level = new_upper_level
                    prev_lower_level = new_lower_level

                # 복합 전략 분석 및 메시지 전송
                result = analyze_combo(
                    b_status, b_msg, j_msg, c_msg, e_msg,
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

    finally:
        await close_db_connection(conn)
        print(f"[{datetime.now()}] 🛑 워처 종료, DB 연결 닫힘")

if __name__ == "__main__":
    asyncio.run(run_watcher())