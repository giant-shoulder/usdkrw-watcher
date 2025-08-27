from typing import Optional, Dict, Tuple
from strategies.utils.score_bar import make_score_gauge
import math
from strategies.ai.ai_decider import AIDecider, build_features, llm_decide_explain
from strategies.decision_gates import decide_with_gates, PriceCtx
from utils.message_templates import build_combo_message
from strategies.utils.types import ComboResult
from strategies.feedback import log_decision
from datetime import datetime, timedelta
from config import COOLDOWN_SECONDS, DEBOUNCE_REQUIRED, HYSTERESIS_P_DELTA, HYSTERESIS_AGREE_DELTA

# Module-level state for debounce/cooldown
_last_action: str | None = None      # 'buy'|'sell'|'hold'
_last_action_time: datetime | None = None
_prev_ai_action: str | None = None   # 직전 틱의 AI 1차 판단
_prev_same_count: int = 0

# === 가중치 설정 (환경에 따라 조정 가능) ===
WEIGHTS: Dict[str, float] = {
    "boll": 0.30,
    "cross": 0.35,
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
    """Nonlinear mapping: -1..+1 → ≈5..95 using tanh to avoid exaggerated extremes."""
    return int(round(50 + 45 * math.tanh(signed_score / 0.6)))


def make_decision(
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
    # --- new optional runtime context ---
    current_price: Optional[float] = None,
    current_atr: Optional[float] = None,
    near_event: bool = False,
    prev_same_decision: Optional[bool] = None,
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

    # 🔒 단일 신호일 때는 콤보 판단(매수/매도)을 내리지 않음 → 개별 신호만 발송
    active_nonzero = [k for k, (d, c, _e) in structs.items() if d != 0 and c > 0]
    if len(active_nonzero) < 2:
        return None

    # === AI 기반 결론 + 게이트 적용 ===
    global _last_action, _last_action_time, _prev_ai_action, _prev_same_count

    feats = build_features(structs)
    ai_action, ai_probs = AIDecider().predict(feats)   # 'buy'|'sell'|'hold'

    # 실제 런타임 컨텍스트 연결 (가격/ATR/이벤트/연속판단)
    if prev_same_decision is None:
        prev_same_decision = (_prev_ai_action == ai_action)
    ctx = PriceCtx(price=current_price, atr=current_atr, near_event=near_event, prev_same_decision=bool(prev_same_decision))

    # 게이트 통과 여부 (가격/ATR/이벤트 컨텍스트가 생기면 ctx 채워 넣기)
    gate_action, gate_reason = decide_with_gates(structs, ai_probs, ctx)

    # 히스테리시스: 직전 확정 행동과 반대 전환이면 추가 확신 요구
    if gate_action in ("buy", "sell") and _last_action in ("buy", "sell") and gate_action != _last_action:
        p_top = ai_probs.get(gate_action, 0.0)
        # 보수적: 기본 0.60에 여유(HYSTERESIS_P_DELTA) 추가 요구
        if p_top < (0.60 + HYSTERESIS_P_DELTA):
            gate_action = "hold"
            gate_reason = "히스테리시스(추가 확신 대기)"

    now = datetime.now()

    # 디바운스: 전환 시 연속 동일 판단 필요
    if gate_action in ("buy", "sell"):
        if _prev_ai_action == gate_action:
            _prev_same_count += 1
        else:
            _prev_same_count = 1
        _prev_ai_action = gate_action

        need_same = max(1, DEBOUNCE_REQUIRED)
        if _prev_same_count < need_same:
            # 관망으로 예고 전환만 알림
            signal_type = "관망"
            pct = int(round(100 * ai_probs.get("hold", 0.0)))
            gate_reason = "전환 조짐(연속확인 대기)"
            # 관망 메시지로 진행
        else:
            # 쿨다운: 같은 방향 재발송 제한
            if _last_action == gate_action and _last_action_time and (now - _last_action_time) < timedelta(seconds=COOLDOWN_SECONDS):
                return None
            # 확정 방향 채택
            signal_type = "상승 전환" if gate_action == "buy" else "하락 전환"
            pct = int(round(100 * ai_probs.get(gate_action, 0.0)))
            _last_action = gate_action
            _last_action_time = now
    else:
        # 게이트 사유에 따른 관망
        signal_type = "관망"
        pct = int(round(100 * ai_probs.get("hold", 0.0)))
        # 디바운스 카운트 리셋
        _prev_ai_action = "hold"
        _prev_same_count = 0

    # === LLM 결론/설명 (선택) ===
    ai_reason_lines: list[str] = []
    try:
        llm_out = llm_decide_explain(
            structs=structs,
            ai_probs=ai_probs,
            gate_action=("buy" if signal_type == "상승 전환" else ("sell" if signal_type == "하락 전환" else "hold")),
            gate_reason=gate_reason if 'gate_reason' in locals() else None,
        )
    except Exception:
        llm_out = None

    if llm_out:
        llm_action = (llm_out.get("action") or "").lower()
        llm_score = llm_out.get("score")
        # 게이트/디바운스 로직은 유지하고, 표시용 액션/점수만 LLM으로 보강
        if llm_action in ("buy", "sell", "hold"):
            signal_type = {"buy": "상승 전환", "sell": "하락 전환", "hold": "관망"}[llm_action]
        if isinstance(llm_score, int):
            pct = max(0, min(100, llm_score))
        reasons = llm_out.get("reasons") or []
        if reasons:
            ai_reason_lines = ["🧠 전망 이유 (AI)"] + [f"- {r}" for r in reasons[:3]]

    # === 결론 헤드라인 (사고/파는 의미가 명확한 아이콘으로 교체) ===
    headline = {
        "상승 전환": "🔴 🛒 매수 (Buy)",   # KR convention: 상승=빨강
        "하락 전환": "🔵 💸 매도 (Sell)",  # KR convention: 하락=파랑
    }.get(signal_type, "⚪ ⏸ 관망 (Hold)")
    header_line = f"*{headline} ({pct}/100)*"

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

    # 관망 사유를 최초 라인에 표시 (있을 경우)
    if signal_type == "관망":
        reason = gate_reason if 'gate_reason' in locals() else None
        if reason:
            bullets = [f"- ℹ️ {reason}"] + bullets

    # === 점수 게이지 (매수=파란색, 매도=빨간색, 관망=회색) ===
    # 신호 라벨 (게이지 타이틀용)
    strength_title = {
        "상승 전환": "🔴 매수 신호 강도",
        "하락 전환": "🔵 매도 신호 강도",
    }.get(signal_type, "⚪ 관망 신호 강도")

    gauge_line = make_score_gauge(headline, pct)

    parts = [header_line, ""]
    if ai_reason_lines:
        parts.append("\n".join(ai_reason_lines))
        parts.append("")
    parts.append("📌 핵심 근거")
    parts.append("\n".join(bullets) if bullets else "- (근거 없음)")
    parts.append("")
    parts.append(strength_title)
    parts.append(gauge_line)
    message = "\n".join(parts)

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