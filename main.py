import asyncio
from datetime import datetime, timedelta
from config import CHECK_INTERVAL, ENVIRONMENT, LONG_TERM_PERIOD, SUMMARY_INTERVAL
from db.repository import get_recent_rates_for_summary
from strategies.summary import get_recent_major_events
from strategies.utils.streak import get_streak_advisory
from utils import is_weekend, now_kst, is_scrape_time
from fetcher import get_usdkrw_rate, fetch_expected_range
from db import (
    connect_to_db, close_db_connection,
    store_rate, get_recent_rates, store_expected_range, get_today_expected_range
)
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


# ✅ 30분 요약용 변수
last_summary_sent = None           # 마지막 요약 발송 시각 (정각 기준)
rate_buffer = []  # 최근 30분 환율 데이터 버퍼 [(timestamp, rate), ...]


async def run_watcher():
    global last_summary_sent, rate_buffer

    print(f"[{now_kst()}] 🏁 워처 시작")
    await send_start_message()

    conn = await connect_to_db()
    prev_rate = None
    upper_streak = 0
    lower_streak = 0
    prev_upper_level = 0
    prev_lower_level = 0
    last_scraped_date = None

    # ✅ 이동평균선, 볼린저 상태 메모리 관리
    temp_state = {
        "short_avg": None,    # 단기 이동평균선
        "long_avg": None,     # 장기 이동평균선
        "type": None,         # "golden" | "dead" | None
        "b_status": None,     # 볼린저 현재 상태
    }

    try:
        while True:
            try:
                now = now_kst()

                # ✅ 주말 정지 로직
                if is_weekend():
                    print(f"[{now}] ⏸️ 주말, 알림 일시 정지 중...")
                    await asyncio.sleep(CHECK_INTERVAL)
                    continue

                # ✅ 오전 11시대 예상 환율 레인지 스크랩
                if is_scrape_time(last_scraped_date):
                    try:
                        result = fetch_expected_range()
                        msg = (
                            "📊 *오늘의 전문가 예상 환율 범위*\n\n"
                            "📌 *주요 외환시장 전문 딜러 전망*\n"
                            f"- 예상 하단: *{result['low']:.2f}원*\n"
                            f"- 예상 상단: *{result['high']:.2f}원*\n\n"
                            "💡 이 수치는 국내외 주요 은행과 외환 전문 딜러들이 제시한 전망으로,\n"
                            "   오늘 환율 흐름을 가늠하는 *신뢰도 높은 참고 지표*입니다.\n"
                            f"(출처: {result['source']})"
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

                    # 최근 LONG_TERM_PERIOD(17시간) 환율 데이터
                    rates = await get_recent_rates(conn, LONG_TERM_PERIOD)

                    # ✅ 30분 내 반등/되돌림(예측 검증)
                    reversal_msgs = await check_breakout_reversals(conn, rate, now)
                    for r_msg in reversal_msgs:
                        await send_telegram(r_msg)

                    # ✅ 개별 전략 분석
                    expected_range = await get_today_expected_range(conn)
                    e_msg = analyze_expected_range(rate, expected_range, now)
                    j_msg = analyze_jump(prev_rate, rate)

                    # ✅ 이동평균선 크로스 분석
                    c_msg, temp_state["short_avg"], temp_state["long_avg"], temp_state["type"] = analyze_crossover(
                        rates=rates,
                        prev_short_avg=temp_state["short_avg"],
                        prev_long_avg=temp_state["long_avg"],
                        prev_signal_type=temp_state["type"],
                        prev_price=prev_rate,
                        current_price=rate
                    )

                    # ✅ 볼린저 밴드 분석
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
                    temp_state["b_status"] = b_status  # 볼린저 상태 저장

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
                        # 콤보 발생 시 반복 레벨 갱신
                        prev_upper_level = combo_result["new_upper_level"]
                        prev_lower_level = combo_result["new_lower_level"]
                        await send_telegram(combo_result["message"])
                    else:
                        # 콤보 없을 때 개별 전략 메시지 전송
                        for msg in single_msgs:
                            await send_telegram(msg)

                    # ✅ 이전 환율 갱신
                    prev_rate = rate

                    # ✅ 정시(00,30분) 요약 발송 (CHECK_INTERVAL 오차 허용)
                    target_minutes = [0, 30]
                    nearest_minute = min(target_minutes, key=lambda m: abs(now.minute - m))

                    if abs(now.minute - nearest_minute) * 60 + now.second <= (CHECK_INTERVAL // 2):
                        rounded_now = now.replace(minute=nearest_minute, second=0, microsecond=0)

                        if last_summary_sent != rounded_now:
                            try:
                                # ✅ DB에서 최근 30분 데이터 조회
                                since = now - timedelta(seconds=SUMMARY_INTERVAL)
                                recent_rates = await get_recent_rates_for_summary(conn, since)

                                if recent_rates:  # ✅ 데이터가 있을 경우에만 발송
                                    major_events = await get_recent_major_events(conn, now)

                                    # ✅ 요약 메시지 생성 및 발송
                                    summary_msg = generate_30min_summary(
                                        start_time=since,
                                        end_time=now,
                                        rates=recent_rates,
                                        major_events=major_events
                                    )
                                    await send_telegram(summary_msg)

                                    # ✅ 차트 생성 및 발송
                                    chart_buf = generate_30min_chart(recent_rates)
                                    if chart_buf and chart_buf.getbuffer().nbytes > 0:
                                        await send_photo(chart_buf)
                                        print(f"[{now}] ✅ 차트 전송 완료 ({rounded_now.strftime('%H:%M')})")
                                    else:
                                        print(f"[{now}] ⏸️ 차트 전송 건너뜀: 데이터 부족 또는 빈 이미지")

                                    last_summary_sent = rounded_now
                                    print(f"[{now}] ✅ 운영 모드: 30분 요약 발송 완료 ({rounded_now.strftime('%H:%M')})")
                                else:
                                    print(f"[{now}] ⏸️ 30분 요약 발송 건너뜀: 최근 30분 데이터 없음")

                            except Exception as e:
                                print(f"[{now}] ❌ 운영 모드: 요약 발송 실패 → {e}")
                        else:
                            print(f"[{now}] ⏸️ 운영 모드: 이미 {rounded_now.strftime('%H:%M')}에 발송됨, 건너뜀")
                    else:
                        print(f"[{now}] ⏸️ 운영 모드: 정각/30분 ±{CHECK_INTERVAL//2}초 범위 아님")



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