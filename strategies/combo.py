from typing import Optional, Dict, Tuple
from strategies.summary import make_score_gauge

# === 가중치 설정 (환경에 따라 조정 가능) ===
WEIGHTS: Dict[str, float] = {
    "boll": 0.35,
    "cross": 0.30,
    "jump": 0.20,
    "expected": 0.15,
}

# 문자열 파싱을 위한 키워드(구조화 신호가 없을 때만 사용)
POS_WORDS = ("상단", "급등", "골든", "강세", "매수")
NEG_WORDS = ("하단", "급락", "데드", "약세", "매도")


def _direction_from_text(msg: str) -> int:
    """텍스트에서 방향 추정: +1 매수, -1 매도, 0 중립"""
    if not msg:
        return 0
    pos = any(w in msg for w in POS_WORDS)
    neg = any(w in msg for w in NEG_WORDS)
    if pos and not neg:
        return +1
    if neg and not pos:
        return -1
    return 0


def _confidence_from_text(msg: str) -> float:
    """텍스트에서 신뢰도(0~1) 추정: 확정/신뢰도/정량표기(z, 스프레드, ATR 등)를 반영"""
    if not msg:
        return 0.0
    conf = 0.6
    low_hits = ("신뢰도 낮음" in msg)
    high_hits = ("확정" in msg) or ("신뢰도 높음" in msg)
    mid_hits = ("신뢰도 중간" in msg)
    if low_hits:
        conf = 0.3
    if mid_hits:
        conf = max(conf, 0.6)
    if high_hits:
        conf = max(conf, 0.9)
    # 정량 키워드가 있으면 신뢰도 하한을 올림
    if any(tag in msg for tag in ("z=", "스프레드", "ATR=")):
        conf = max(conf, 0.75)
    # 예상범위 레벨(🟥/🟧/🟨) 반영
    if "🟥" in msg:
        conf = max(conf, 0.9)
    elif "🟧" in msg:
        conf = max(conf, 0.75)
    elif "🟨" in msg:
        conf = max(conf, 0.65)
    return min(1.0, max(0.0, conf))


def _to_struct(msg: str) -> Tuple[int, float, str]:
    """문자열 메시지를 (direction, confidence, evidence)로 정규화"""
    if not msg:
        return (0, 0.0, "")
    d = _direction_from_text(msg)
    c = _confidence_from_text(msg)
    return (d, c, msg)


def _score_to_pct(signed_score: float) -> int:
    """-1..+1 → 0..100 정규화"""
    return int(min(100, max(0, round(50 + signed_score * 50))))


def analyze_combo(
    b_status: Optional[str],
    b_msg: Optional[str],
    j_msg: Optional[str],
    c_msg: Optional[str],
    e_msg: Optional[str],
    upper_streak: int,
    lower_streak: int,
    prev_upper_level: float,
    prev_lower_level: float,
    *,
    b_struct: Optional[dict] = None,
    j_struct: Optional[dict] = None,
    c_struct: Optional[dict] = None,
    e_struct: Optional[dict] = None,
):
    """
    종합 콤보 분석
    - 구조화 신호(b_struct, j_struct, c_struct, e_struct)가 제공되면 이를 우선 사용
    - 없으면 문자열 파싱으로 보조
    - 가중합 스코어 → 방향/점수 산출
    - 메시지 템플릿: 결론 → 핵심 근거(최대 3개) → 점수 게이지
    """

    # 활성 신호 수집 (문자열)
    signals = {
        "📊 볼린저 밴드": ("boll", b_msg),
        "⚡ 급변 감지": ("jump", j_msg),
        "🔁 이동평균선 크로스": ("cross", c_msg),
        "📡 예상 범위 이탈": ("expected", e_msg),
    }
    active_signals = {k: v for k, v in signals.items() if v[1]}
    if not active_signals and not any([b_struct, j_struct, c_struct, e_struct]):
        return None

    # 구조화 신호 우선 매핑
    struct_map: Dict[str, Tuple[int, float, str]] = {}
    if b_struct:
        struct_map["boll"] = (
            b_struct.get("direction", 0),
            b_struct.get("confidence", 0.0),
            b_struct.get("evidence", ""),
        )
    if j_struct:
        struct_map["jump"] = (
            j_struct.get("direction", 0),
            j_struct.get("confidence", 0.0),
            j_struct.get("evidence", ""),
        )
    if c_struct:
        struct_map["cross"] = (
            c_struct.get("direction", 0),
            c_struct.get("confidence", 0.0),
            c_struct.get("evidence", ""),
        )
    if e_struct:
        struct_map["expected"] = (
            e_struct.get("direction", 0),
            e_struct.get("confidence", 0.0),
            e_struct.get("evidence", ""),
        )

    # 구조화가 없으면 문자열 파싱으로 대체
    structs: Dict[str, Tuple[int, float, str]] = {}
    for _label, (key, msg) in active_signals.items():
        if key in struct_map:
            structs[key] = struct_map[key]
        else:
            structs[key] = _to_struct(msg)

    # 가중 합산 스코어 (-1..+1)
    raw = 0.0
    total_w = 0.0
    for key, (d, c, _e) in structs.items():
        w = WEIGHTS.get(key, 0.0)
        raw += w * d * c
        total_w += w
    signed = raw / total_w if total_w > 0 else 0.0

    # 충돌 페널티: 서로 다른 부호의 강한 신호가 공존할 때 약화
    dirs = [d for (d, _c, _e) in structs.values() if d != 0]
    if len(dirs) >= 2 and (min(dirs) < 0 < max(dirs)):
        signed *= 0.7

    # 방향/점수 해석
    if signed > 0.10:
        signal_type = "상승 전환"
    elif signed < -0.10:
        signal_type = "하락 전환"
    else:
        signal_type = None

    if not signal_type:
        return None

    score = signed  # -1..+1
    pct = _score_to_pct(score)

    # === 결론 헤드라인 (사고/파는 의미가 명확한 아이콘으로 교체) ===
    headline = {
        "상승 전환": "🛒 매수 (Buy)",   # 구매 아이콘
        "하락 전환": "💸 매도 (Sell)",  # 현금 유출 아이콘
    }.get(signal_type, "⏸ 관망 (Hold)")

    # === 핵심 근거 상위 2~3개 선별 ===
    key_emojis = {"boll": "📊", "cross": "🔁", "jump": "⚡", "expected": "📡"}
    contribs = []
    for key, (d, c, ev) in structs.items():
        w = WEIGHTS.get(key, 0.0)
        contribs.append((w * abs(d) * c, key, ev))
    contribs.sort(reverse=True)
    top = contribs[:3]

    bullets = []
    for _score, key, ev in top:
        if not ev:
            continue
        bullets.append(f"- {key_emojis.get(key, '•')} {ev}")

    # === 점수 게이지 (매수=파란색, 매도=빨간색, 관망=회색) ===
    # 신호 라벨 (게이지 타이틀용)
    strength_title = {
        "상승 전환": "🔵 매수 신호 강도",
        "하락 전환": "🔴 매도 신호 강도",
    }.get(signal_type, "⚪ 관망 신호 강도")

    gauge_line = make_score_gauge(headline, pct)

    message = (
        f"{headline} ({pct}/100)\n\n"
        f"📌 핵심 근거\n" + ("\n".join(bullets) if bullets else "- (근거 없음)") + "\n\n"
        f"{strength_title}\n"
        f"{gauge_line}"
    )

    # 레벨 업데이트 (기본 로직 유지)
    new_upper_level = prev_upper_level
    new_lower_level = prev_lower_level
    if signal_type == "상승 전환":
        new_upper_level += 0.1
    elif signal_type == "하락 전환":
        new_lower_level -= 0.1

    return {
        "message": message,
        "type": "buy" if signal_type == "상승 전환" else ("sell" if signal_type == "하락 전환" else "neutral"),
        "score": pct,
        "new_upper_level": new_upper_level,
        "new_lower_level": new_lower_level,
    }