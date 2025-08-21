# strategies/jump.py

from config import JUMP_THRESHOLD
from strategies.utils.signal_utils import atr_from_rates

REL_JUMP = 0.6   # ATR 대비 60% 이상 움직이면 급변
COOLDOWN_TICKS = 3

_last_jump_time = None

def analyze_jump(prev, current, highs=None, lows=None, closes=None, now=None):
    if prev is None: return None
    diff = round(current - prev, 2)
    atr = atr_from_rates(highs or [], lows or [], closes or [], period=14)
    if not atr: atr = JUMP_THRESHOLD  # 백업: 기존 절대임계

    if abs(diff) >= max(JUMP_THRESHOLD, REL_JUMP * atr):
        global _last_jump_time
        if _last_jump_time and now and (now - _last_jump_time).seconds < COOLDOWN_TICKS*200:
            return None  # 루프 간격(200s) 기준 쿨다운
        _last_jump_time = now
        direction = "급등" if diff > 0 else "급락"
        return f"{direction} 감지: {diff:+.2f}원 (ATR={atr:.2f})"
    return None