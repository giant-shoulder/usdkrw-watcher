from datetime import datetime, timedelta
from statistics import mean, stdev
from config import MOVING_AVERAGE_PERIOD
from io import BytesIO
from datetime import datetime
import matplotlib.pyplot as plt
from pytz import timezone
from strategies.utils.score_bar import make_score_gauge
from strategies.ai_decider import AIDecider

# === Trend classification thresholds (tunable) ===
BANDWIDTH_TIGHT = 0.20   # 횡보로 볼 변동 폭(원)
DIFF_STRONG     = 0.20   # 강한 상승/하락으로 볼 종가-시가 차이(원)
DIFF_WEAK       = 0.10   # 약한 방향성 최소 임계(원)
PROX_NEAR       = 0.10   # 종가가 고저점에 근접했다고 보는 거리(원)
PULLBACK_DIST   = 0.30   # 급등/급락 후 되돌림 판단 거리(원)

# === AI feature builder for 30분 요약 ===
# AIDecider는 다음 키들을 인식함: expected_dir_±1, boll_dir_±1, cross_type_golden/dead, agree_count
# 여기서는 시계열 통계로 유사 신호를 구성해 전달한다.

def _build_ai_features_30min(diff: float, slope_10min: float, high: float, low: float, end_rate: float) -> dict:
    x: dict[str, float] = {"bias": 1.0}
    band = max(0.01, high - low)
    pos_from_low = (end_rate - low) / band  # 0(저점)~1(고점)

    # 예상 범위 유사 신호: 상단/하단 쏠림
    if pos_from_low >= 0.65:
        x["expected_dir_+1"] = float(f"{pos_from_low:.3f}")  # 상단 근접할수록 강함
    elif pos_from_low <= 0.35:
        x["expected_dir_-1"] = float(f"{(1.0 - pos_from_low):.3f}")

    # 볼린저 유사 신호: 고점/저점 근접 + 방향성 일치
    near_high = (high - end_rate) <= PROX_NEAR
    near_low = (end_rate - low) <= PROX_NEAR
    if near_high and (diff > 0 or slope_10min > 0):
        x["boll_dir_+1"] = 0.6
    if near_low and (diff < 0 or slope_10min < 0):
        x["boll_dir_-1"] = 0.6

    # 크로스 유사 신호: 최근 10분 기울기 부호/크기
    if slope_10min >= DIFF_WEAK:
        x["cross_type_golden"] = min(1.0, abs(slope_10min) / 0.5)
    elif slope_10min <= -DIFF_WEAK:
        x["cross_type_dead"] = min(1.0, abs(slope_10min) / 0.5)

    # 합의 카운트: 상방/하방 신호 중 큰 쪽 개수
    ups = sum(1 for k in x if k.endswith("_dir_+1") or k.endswith("golden"))
    dns = sum(1 for k in x if k.endswith("_dir_-1") or k.endswith("dead"))
    x["agree_count"] = float(max(ups, dns))
    return x


async def get_recent_major_events(conn, current_time) -> list[str]:
    """
    breakout_events 테이블 기반 최근 30분 주요 이벤트 요약
    - 상단 돌파 / 하단 이탈 발생 시간과 기준선 정보 표시
    """
    cutoff_time = current_time - timedelta(minutes=30)
    query = """
        SELECT event_type, timestamp, threshold
        FROM breakout_events
        WHERE timestamp >= $1
        ORDER BY timestamp ASC
    """
    rows = await conn.fetch(query, cutoff_time)

    events = []
    for row in rows:
        etype = row["event_type"]
        ts = row["timestamp"].astimezone()
        hhmm = ts.strftime("%H:%M")
        if etype == "upper_breakout":
            events.append(f"{hhmm} 볼린저 상단 돌파 (기준선 {row['threshold']:.2f})")
        elif etype == "lower_breakout":
            events.append(f"{hhmm} 볼린저 하단 이탈 (기준선 {row['threshold']:.2f})")
    return events


def generate_30min_summary(
    start_time: datetime,
    end_time: datetime,
    rates: list[tuple[datetime, float]],
    major_events: list[str] = None
) -> str:
    """
    30분 간 환율 요약 메시지 생성
    - 추세 분석, 최근 10분 기울기, 변동폭 분석 포함
    - 주요 이벤트와 종합 해석 제공
    """

    if not rates:
        return "⏱️ 최근 30분 데이터가 없습니다."

    # 📌 데이터 정렬 및 기초 통계
    sorted_rates = sorted(rates, key=lambda x: x[0])
    start_rate = sorted_rates[0][1]
    end_rate = sorted_rates[-1][1]
    high = max(r[1] for r in sorted_rates)
    low = min(r[1] for r in sorted_rates)
    diff = round(end_rate - start_rate, 2)
    band_width = round(high - low, 2)

    # 📉 최근 10분 기울기
    ten_min_rates = [r for r in sorted_rates if (sorted_rates[-1][0] - r[0]).total_seconds() <= 600]
    slope_10min = round(ten_min_rates[-1][1] - ten_min_rates[0][1], 3) if len(ten_min_rates) >= 2 else 0.0

    # 📊 변동폭 해석
    if band_width >= 3.0:
        volatility = f"{band_width:.2f}원 (상대적으로 넓은 변동성)"
    elif band_width >= 1.5:
        volatility = f"{band_width:.2f}원 (보통 수준의 변동성)"
    else:
        volatility = f"{band_width:.2f}원 (좁은 변동성)"

    # 📈 추세 분류 (개선 버전: 혼합 패턴 인식)
    high_diff = round(high - end_rate, 2)  # 고점-종가 (양수면 고점 대비 밀림)
    low_diff  = round(end_rate - low, 2)   # 종가-저점 (양수면 저점 대비 여유)

    if band_width <= BANDWIDTH_TIGHT and abs(diff) <= DIFF_WEAK:
        trend = "횡보"
    elif diff >= DIFF_STRONG:
        # 전체적으로 상승이지만 최근 10분이 하락 전환했고, 고점에서 밀린 상태라면 → 상승 후 하락
        if slope_10min <= -DIFF_WEAK and high_diff >= PROX_NEAR:
            trend = "상승 후 하락"
        elif abs(high - end_rate) <= PROX_NEAR and slope_10min > 0:
            trend = "강한 상승"
        else:
            trend = "상승"
    elif diff <= -DIFF_STRONG:
        # 전체적으로 하락이지만 최근 10분이 반등했고, 저점에서 어느 정도 올라온 상태라면 → 하락 후 반등
        if slope_10min >= DIFF_WEAK and low_diff >= PROX_NEAR:
            trend = "하락 후 반등"
        elif abs(end_rate - low) <= PROX_NEAR and slope_10min < 0:
            trend = "강한 하락"
        else:
            trend = "하락"
    elif abs(diff) < DIFF_WEAK and (high - end_rate) >= PULLBACK_DIST:
        trend = "급등 후 조정"
    elif abs(diff) < DIFF_WEAK and (end_rate - low) >= PULLBACK_DIST:
        trend = "급락 후 반등"
    else:
        trend = "혼조"

    # 🤖 AI 기반 추세 보정: 확신이 높을 때(>=0.60) 규칙 기반 판정을 덮어쓴다
    try:
        ai_feats = _build_ai_features_30min(diff=diff, slope_10min=slope_10min, high=high, low=low, end_rate=end_rate)
        ai = AIDecider()
        ai_action, ai_probs = ai.predict(ai_feats)
        ai_conf = max(ai_probs.get("buy", 0.0), ai_probs.get("sell", 0.0), ai_probs.get("hold", 0.0))
        if ai_conf >= 0.60:
            if ai_action == "buy":
                trend = "상승"
            elif ai_action == "sell":
                trend = "하락"
            else:
                trend = "횡보"
    except Exception:
        pass  # AI 적용 중 오류가 나도 요약 생성은 지속

    # 🧭 추세별 이모지
    trend_emojis = {
        "강한 상승": "🚀📈",
        "강한 하락": "🛬📉",
        "상승": "📈",
        "하락": "📉",
        "상승 후 하락": "📈↘️",
        "하락 후 반등": "📉↗️",
        "급등 후 조정": "🔺📉",
        "급락 후 반등": "🔻📈",
        "혼조": "🔀",
        "횡보": "➖",
    }
    trend_emoji = trend_emojis.get(trend, "📊")

    # 💡 종합 해석
    advice_map = {
        "강한 상승": "강한 상승 추세 → 분할 매수 또는 추세 추종 고려",
        "강한 하락": "강한 하락 추세 → 반등 전까지 보수적 접근",
        "상승": "상승 흐름 유지 → 관망 후 소량 매수 고려",
        "하락": "하락 흐름 유지 → 관망 권장",
        "상승 후 하락": "상승세가 꺾이는 신호 → 단기 조정 주의",
        "하락 후 반등": "반등 시도 진행 → 추세 전환 여부 확인",
        "급등 후 조정": "급등 후 되돌림 진행 중 → 추세 전환 가능성 주의",
        "급락 후 반등": "급락 후 단기 반등 → 추세 지속 여부 확인 필요",
        "혼조": "단기 등락 반복 → 관망 우선",
        "횡보": "변동성 낮음 → 관망 유지",
    }
    advice = advice_map[trend]

    # 📝 주요 이벤트 정리
    events_text = "\n".join(f"- {e}" for e in major_events) if major_events else "해당 없음"

    return (
        f"⏱️ *최근 30분 환율 요약 ({start_time.strftime('%H:%M')} ~ {end_time.strftime('%H:%M')})*\n\n"
        f"{trend_emoji} *추세*: {trend}\n"
        f"- 30분 전: {start_rate:.2f} → 현재: {end_rate:.2f}원 "
        f"({'+' if diff > 0 else ''}{diff:.2f}원, 최근10분 기울기 {slope_10min:+.3f})\n\n"
        f"📊 *변동폭*: 최고 {high:.2f} / 최저 {low:.2f}\n"
        f"- 변동 폭: {volatility}\n\n"
        f"📌 *주요 이벤트*\n{events_text}\n\n"
        f"💡 *종합 해석*: {advice}\n\n"
    )




def generate_30min_chart(rates: list[tuple[datetime, float]]) -> BytesIO | None:
    """
    30분간 USD/KRW 환율 추이 그래프 생성
    - 상승: 빨강, 하락: 파랑, 횡보: 회색
    - 시작/종료 시점 강조 표시
    - 데이터 부족 시 None 반환
    """

    # ✅ 데이터 유효성 검사
    if not rates or len(rates) < 2:
        print("⏸️ 차트 생성 건너뜀: 데이터가 부족합니다.")
        return None

    KST = timezone("Asia/Seoul")

    times = [r[0].astimezone(KST).strftime("%H:%M") for r in rates]
    values = [r[1] for r in rates]

    # ✅ 모든 값이 동일한 경우 (차트는 생성하지만 경고 표시)
    if max(values) == min(values):
        print("⚠️ 모든 환율 값이 동일합니다 – 평평한 차트가 생성됩니다.")

    # ✅ 추세에 따른 색상 설정 (표시 정밀도 고려: 2자리 반올림 기준)
    EPS = 0.005  # 0.01원 표시 기준에서 동치 판단 여유
    start_v = round(values[0], 2)
    end_v = round(values[-1], 2)
    if end_v - start_v > EPS:
        color = "red"   # 상승
    elif start_v - end_v > EPS:
        color = "blue"  # 하락
    else:
        color = "gray"  # 횡보 (표시상 동일로 간주)

    # ✅ 포인트 주석 함수 정의
    def annotate_point(x, y, label, align="right"):
        ha = "right" if align == "right" else "left"
        size = 60 if align == "right" else 80
        plt.scatter(x, y, color=color, s=size, edgecolors="black", zorder=5)
        plt.text(
            x, y, f"{label:.2f}", fontsize=9, color="black", ha=ha, va="bottom",
            bbox=dict(facecolor="white", edgecolor="gray", boxstyle="round,pad=0.2")
        )

    # ✅ 차트 그리기
    plt.figure(figsize=(6, 3))
    plt.plot(times, values, marker="o", linewidth=2, color=color)
    plt.xticks(rotation=45)
    plt.title("USD/KRW Last 30 min")  # 영어 제목 유지
    plt.xlabel("Time")
    plt.ylabel("KRW")
    plt.grid(True)

    # ✅ 시작점, 종료점 강조
    annotate_point(times[0], values[0], round(values[0], 2), align="right")
    annotate_point(times[-1], values[-1], round(values[-1], 2), align="left")

    # ✅ 메모리 버퍼에 저장
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close()

    print(f"✅ 차트 생성 완료 (데이터 {len(values)}건)")
    return buf
