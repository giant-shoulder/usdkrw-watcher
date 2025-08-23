# strategies/jump.py

from config import JUMP_THRESHOLD
from strategies.utils.signal_utils import atr_from_rates

REL_JUMP = 0.6   # ATR 대비 60% 이상 움직이면 급변
COOLDOWN_TICKS = 3

_last_jump_time = None

def analyze_jump(prev, current, highs=None, lows=None, closes=None, now=None):
    """
    급변 감지
    Returns: (message_or_none, struct_or_none)
      struct = {
        "key": "jump",
        "direction": +1 | -1 | 0,
        "confidence": float(0~1),
        "evidence": str,
        "meta": {"diff": float, "atr": float}
      }
    """
    if prev is None:
        return None, None

    diff = round(current - prev, 2)
    atr = atr_from_rates(highs or [], lows or [], closes or [], period=14)
    if not atr:
        atr = JUMP_THRESHOLD  # 백업: 기존 절대임계

    threshold = max(JUMP_THRESHOLD, REL_JUMP * atr)

    if abs(diff) >= threshold:
        global _last_jump_time
        if _last_jump_time and now and (now - _last_jump_time).seconds < COOLDOWN_TICKS * 200:
            return None, None  # 루프 간격(200s) 기준 쿨다운
        _last_jump_time = now

        is_up = diff > 0
        direction_text = "급등" if is_up else "급락"
        evidence = (
            f"{direction_text} 감지: {diff:+.2f}원 (ATR={atr:.2f})\n"
            f"💱 환율: {prev:.2f}원 → {current:.2f}원 ({diff:+.2f}원)"
        )
        msg = f"{'📈' if is_up else '📉'} {evidence}"

        struct = {
            "key": "jump",
            "direction": +1 if is_up else -1,
            "confidence": 0.7,  # 임계 초과 시 기본 신뢰도
            "evidence": evidence,
            "meta": {"diff": float(f"{diff:.2f}"), "atr": float(f"{atr:.2f}")},
        }
        return msg, struct

    return None, None