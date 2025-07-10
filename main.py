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
    """ 워처 메인 루프
    - 환율 조회 및 분석
    - 전략별 신호 분석 및 알림 전송
    - DB 연결 및 관리
    """
    print(f"[{now_kst()}] 🏁 워처 시작")
    # 초기 시작 메시지 전송
    # 로컬 환경에서만 시작 메시지 전송
    # (배포 환경에서는 이미 시작 메시지가 전송되었으므로 중복 방지)
    if ENVIRONMENT == "local":
        await send_start_message()

    conn = await connect_to_db()
    prev_rate = None
    prev_short_avg, prev_long_avg = None, None
    upper_streak = 0
    lower_streak = 0
    prev_upper_level = 0
    prev_lower_level = 0
    last_scraped_date = None  # 스크랩 시간 중복 방지

    try:
        while True:
            try:
                now = now_kst()

                if is_weekend():
                    print(f"[{now}] ⏸️ 주말, 알림 일시 정지 중...")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                # ✅ 오전 11시대 스크랩 조건 확인
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
                        await send_telegram(err_msg)

                # ✅ 환율 조회
                rate = get_usdkrw_rate()
                if rate:
                    print(f"[{now}] 📈 환율: {rate}")
                    await store_rate(conn, rate)
                    rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

                    # ✅ 이전 이벤트 중 30분 이내 반등/되돌림 감지
                    reversal_msgs = await check_breakout_reversals(conn, rate, now)
                    for r_msg in reversal_msgs:
                        await send_telegram(r_msg)

                    # ✅ 예상 범위 벗어남 감지
                    expected_range = await get_today_expected_range(conn)
                    e_msg = analyze_expected_range(rate, expected_range, now)

                    # ✅ 점프 / 크로스 전략
                    j_msg = analyze_jump(prev_rate, rate)
                    c_msg, prev_short_avg, prev_long_avg = analyze_crossover(rates, prev_short_avg, prev_long_avg)

                    # ✅ 볼린저 전략 분석 (다중 메시지 + streak 업데이트 포함)
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

                    # ✅ 복합 전략 분석 및 메시지 전송
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