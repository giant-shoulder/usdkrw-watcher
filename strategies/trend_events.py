from __future__ import annotations
from datetime import timedelta
from typing import Optional

# Module-level cooldown state
_last_trend_event_time = None
_last_trend_event_type = None  # 'up10' | 'down10'

async def detect_and_format_10min_trend_event(conn, now, atr_val: Optional[float]) -> Optional[str]:
    """
    Looks back 10 minutes and returns a formatted alert message if a strong up/down trend is detected.
    Cooldown: emits at most once per 10 minutes.
    """
    from db.repository import get_rates_in_block  # local import to avoid circular imports

    try:
        window_start = now - timedelta(minutes=10)
        recent_10 = await get_rates_in_block(conn, window_start, now)
        if not (recent_10 and len(recent_10) >= 3):
            return None

        # Normalize sequence to list of floats
        if isinstance(recent_10[0], (list, tuple)):
            seq = [float(r[1]) for r in recent_10]
        else:
            seq = [float(r) for r in recent_10]

        start_v, end_v = seq[0], seq[-1]
        change = round(end_v - start_v, 2)
        steps = [round(seq[i+1] - seq[i], 4) for i in range(len(seq)-1)]
        up_steps = sum(1 for s in steps if s > 0)
        down_steps = sum(1 for s in steps if s < 0)
        mono_ratio = max(up_steps, down_steps) / max(1, len(steps))

        # Thresholds
        atr_th = (atr_val or 0.0) * 1.5
        change_th = max(1.0, round(atr_th, 2))
        is_up10 = (change >= change_th and mono_ratio >= 0.8 and end_v > start_v)
        is_down10 = (abs(change) >= change_th and mono_ratio >= 0.8 and end_v < start_v)

        if not (is_up10 or is_down10):
            return None

        # Cooldown: 10 minutes between trend events
        global _last_trend_event_time, _last_trend_event_type
        if _last_trend_event_time and (now - _last_trend_event_time) < timedelta(minutes=10):
            return None

        typ = 'up10' if is_up10 else 'down10'
        arrow = '▲' if is_up10 else '▼'
        mult = (abs(change) / (atr_val or 1.0)) if atr_val else None
        mult_txt = f" ({mult:.1f}× ATR)" if mult is not None else ""
        msg = (
            f"📡 10분 연속 {'상승' if is_up10 else '하락'} 감지\n"
            f"💱 환율: {start_v:.2f}원 → {end_v:.2f}원 ({arrow} {abs(change):.2f}원){mult_txt}"
        )

        _last_trend_event_time = now
        _last_trend_event_type = typ
        return msg

    except Exception:
        return None