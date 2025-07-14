import asyncio
from datetime import datetime
from config import CHECK_INTERVAL, ENVIRONMENT, LONG_TERM_PERIOD
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
    analyze_expected_range,
    check_breakout_reversals
)


async def run_watcher():
    print(f"[{now_kst()}] 🏁 워처 시작")
    await send_start_message()

    conn = await connect_to_db()
    prev_rate = None
    upper_streak = 0
    lower_streak = 0
    prev_upper_level = 0
    prev_lower_level = 0
    last_scraped_date = None

    # ✅ 이동평균선 상태를 메모리로 관리
    temp_state = {
        "short_avg": None,
        "long_avg": None,
        "type": None,  # "golden" | "dead" | None
    }

    try:
        while True:
            try:
                now = now_kst()

                if is_weekend():
                    print(f"[{now}] ⏸️ 주말, 알림 일시 정지 중...")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                # ✅ 오전 11시대 스크랩
                if is_scrape_time(last_scraped_date):
                    try:
                        result = fetch_expected_range()
                        msg = (
                            "📊 *오늘의 예상 환율 레인지*\n"
                            f"• 하단: *{result['low']:.2f}원*\n"
                            f"• 상단: *{result['high']:.2f}원*\n"
                            f"출처: {result['source']}"
                        )
                        print(msg)
                        await store_expected_range(conn, now.date(), result["low"], result["high"], result["source"])
                        await send_telegram(msg)
                        last_scraped_date = now.date()
                    except Exception as e:
                        err_msg = f"⚠️ 예상 환율 레인지 스크래핑 실패:\n{e}"
                        print(err_msg)
                        await send_telegram(err_msg, target_chat_ids=["7650730456"])

                # ✅ 환율 조회
                rate = get_usdkrw_rate()
                if rate:
                    print(f"[{now}] 📈 환율: {rate}")
                    await store_rate(conn, rate)
                    rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

                    # ✅ 되돌림 감지
                    reversal_msgs = await check_breakout_reversals(conn, rate, now)
                    for r_msg in reversal_msgs:
                        await send_telegram(r_msg)

                    # ✅ 전략별 분석
                    expected_range = await get_today_expected_range(conn)
                    e_msg = analyze_expected_range(rate, expected_range, now)
                    j_msg = analyze_jump(prev_rate, rate)

                    # ✅ 크로스오버 리팩토링 적용
                    c_msg, temp_state["short_avg"], temp_state["long_avg"], temp_state["type"] = analyze_crossover(
                        rates=rates,
                        prev_short_avg=temp_state["short_avg"],
                        prev_long_avg=temp_state["long_avg"],
                        prev_signal_type=temp_state["type"],
                        prev_price=prev_rate,
                        current_price=rate
                    )

                    # ✅ 볼린저 분석
                    b_status, b_msgs, upper_streak, lower_streak, prev_upper_level, prev_lower_level = await analyze_bollinger(
                        conn=conn,
                        rates=rates,
                        current=rate,
                        prev=prev_rate,
                        prev_upper=prev_upper_level,
                        prev_lower=prev_lower_level,
                        cross_msg=c_msg,
                        jump_msg=j_msg
                    )

                    # ✅ 개별 전략 메시지 수집
                    single_msgs = [msg for msg in [j_msg, c_msg, e_msg] if msg]
                    single_msgs.extend(b_msgs)

                    # ✅ 콤보 전략 분석 및 메시지 전송
                    combo_result = analyze_combo(
                        b_status,
                        b_msgs[0] if b_msgs else None,
                        j_msg,
                        c_msg,
                        e_msg,
                        upper_streak,
                        lower_streak,
                        prev_upper_level,
                        prev_lower_level,
                    )

                    if combo_result:
                        prev_upper_level = combo_result["new_upper_level"]
                        prev_lower_level = combo_result["new_lower_level"]
                        await send_telegram(combo_result["message"])
                    else:
                        for msg in single_msgs:
                            await send_telegram(msg)

                    # ✅ 이전 환율 갱신
                    prev_rate = rate

                else:
                    print(f"[{datetime.now()}] ❌ 환율 조회 실패")

            except Exception as e:
                print(f"[{now_kst()}] ❌ 루프 내부 오류: {e}")

            await asyncio.sleep(CHECK_INTERVAL)

    finally:
        await close_db_connection(conn)
        print(f"[{datetime.now()}] 🛑 워처 종료, DB 연결 닫힘")


if __name__ == "__main__":
    asyncio.run(run_watcher())