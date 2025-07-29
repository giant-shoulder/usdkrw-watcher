import asyncio
from datetime import datetime, timedelta

from config import CHECK_INTERVAL, ENVIRONMENT, LONG_TERM_PERIOD, SUMMARY_INTERVAL
from db.repository import (
    store_rate, get_recent_rates, store_expected_range,
    get_today_expected_range, get_recent_rates_for_summary
)
from strategies.summary import get_recent_major_events
from utils import is_weekend, now_kst, is_scrape_time
from fetcher import get_usdkrw_rate, fetch_expected_range
from notifier import send_telegram, send_start_message, send_photo
from strategies import (
    analyze_bollinger,
    analyze_jump,
    analyze_crossover,
    analyze_combo,
    analyze_expected_range,
    check_breakout_reversals,
    generate_30min_summary,
    generate_30min_chart
)

# 글로벌 상태 변수
last_summary_sent = None


async def run_watcher(db_pool):
    """
    환율 모니터링 메인 루프
    - 실시간 환율 수집 및 저장
    - 다양한 전략 분석 수행 및 Telegram 알림 전송
    - 30분 요약 메시지 및 차트 자동 전송
    """
    global last_summary_sent

    print(f"[{now_kst()}] 🏋️️ 워치 시작")
    await send_start_message()

    # 분석 상태 초기화
    prev_rate = None
    upper_streak = 0
    lower_streak = 0
    prev_upper_level = 0
    prev_lower_level = 0
    last_scraped_date = None

    temp_state = {
        "short_avg": None,
        "long_avg": None,
        "type": None,
        "b_status": None,
    }

    try:
        while True:
            try:
                now = now_kst()

                if is_weekend():
                    print(f"[{now}] ⏸️ 주말 감지됨. 루프 일시 중지 중...")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                async with db_pool.acquire() as conn:

                    if is_scrape_time(last_scraped_date):
                        try:
                            result = fetch_expected_range()
                            msg = (
                                "📊 *오늘의 환율 예상 범위 (전문가 제시)*\n\n"
                                "📌 *주요 외환 딜러들의 예측*\n"
                                f"- 예상 하단: *{result['low']:.2f}원*\n"
                                f"- 예상 상단: *{result['high']:.2f}원*\n\n"
                                "💡 이 수치는 주요 은행 및 글로벌 외환 딜러들이 제시한 예측값으로,\n"
                                "   하루 환율 흐름을 가늠할 수 있는 *신뢰도 높은 참고 지표*입니다.\n"
                                f"(출처: {result['source']})"
                            )

                            print(msg)
                            await store_expected_range(conn, datetime.now().date(), result["low"], result["high"], result["source"])
                            await send_telegram(msg)
                            last_scraped_date = now.date()
                        except Exception as e:
                            err_msg = f"⚠️ 예상 범위 스크래핑 실패: {e}"
                            print(err_msg)
                            await send_telegram(err_msg, target_chat_ids=["7650730456"])

                    rate = get_usdkrw_rate()
                    if rate:
                        print(f"[{now}] 📈 현재 환율: {rate}")
                        await store_rate(conn, rate)

                        rates = await get_recent_rates(conn, LONG_TERM_PERIOD)
                        reversal_msgs = await check_breakout_reversals(conn, rate, now)
                        for r_msg in reversal_msgs:
                            await send_telegram(r_msg)

                        expected_range = await get_today_expected_range(conn)
                        e_msg = analyze_expected_range(rate, expected_range, now)
                        j_msg = analyze_jump(prev_rate, rate)

                        c_msg, temp_state["short_avg"], temp_state["long_avg"], temp_state["type"] = analyze_crossover(
                            rates=rates,
                            prev_short_avg=temp_state["short_avg"],
                            prev_long_avg=temp_state["long_avg"],
                            prev_signal_type=temp_state["type"],
                            prev_price=prev_rate,
                            current_price=rate
                        )

                        b_status, b_msgs, upper_streak, lower_streak, prev_upper_level, prev_lower_level = await analyze_bollinger(
                            conn=conn,
                            rates=rates,
                            current=rate,
                            prev=prev_rate,
                            prev_upper=prev_upper_level,
                            prev_lower=prev_lower_level,
                            cross_msg=c_msg,
                            jump_msg=j_msg,
                            prev_status=temp_state.get("b_status")
                        )
                        temp_state["b_status"] = b_status

                        single_msgs = [msg for msg in [j_msg, c_msg, e_msg] if msg]
                        single_msgs.extend(b_msgs)

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

                        prev_rate = rate

                        # ✅ 30분 요약 및 그래프 생성 시점 판별
                        target_minutes = [0, 30]
                        nearest_minute = min(target_minutes, key=lambda m: abs(now.minute - m))

                        if abs(now.minute - nearest_minute) * 60 + now.second <= (CHECK_INTERVAL // 2):
                            rounded_now = now.replace(minute=nearest_minute, second=0, microsecond=0)

                            if last_summary_sent != rounded_now:
                                try:
                                    since = now - timedelta(seconds=SUMMARY_INTERVAL)
                                    recent_rates = await get_recent_rates_for_summary(conn, since)

                                    if recent_rates:
                                        major_events = await get_recent_major_events(conn, now)

                                        summary_msg = generate_30min_summary(
                                            start_time=since,
                                            end_time=now,
                                            rates=recent_rates,
                                            major_events=major_events
                                        )
                                        await send_telegram(summary_msg)

                                        chart_buf = generate_30min_chart(recent_rates)
                                        if chart_buf and chart_buf.getbuffer().nbytes > 0:
                                            await send_photo(chart_buf)
                                            print(f"[{now}] ✅ 차트 전송 완료 ({rounded_now.strftime('%H:%M')})")
                                        else:
                                            print(f"[{now}] ⏸️ 차트 전송 취소: 데이터 부족")

                                        last_summary_sent = rounded_now
                                        print(f"[{now}] ✅ 30분 요약 메시지 발송 완료 ({rounded_now.strftime('%H:%M')})")
                                    else:
                                        print(f"[{now}] ⏸️ 30분 요약 생략: 그리고 보내지 않음")
                                except Exception as e:
                                    print(f"[{now}] ❌ 요약 발송 실패: {e}")
                            else:
                                print(f"[{now}] ⏸️ 이미 {rounded_now.strftime('%H:%M')} 에 발송됨, 생략")
                        else:
                            print(f"[{now}] ⏸️ 요약 발송 시간 조건 무효")
                    else:
                        print(f"[{now}] ❌ 환율 조회 실패")

            except Exception as e:
                print(f"[{now_kst()}] ❌ 루프 내부 오류: {e}")

            await asyncio.sleep(CHECK_INTERVAL)

    finally:
        await db_pool.close()
        print(f"[{datetime.now()}] 🚭 워치 종료. DB 커넥션 종료 완료")