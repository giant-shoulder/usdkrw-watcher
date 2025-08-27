# strategies/decision_gates.py
from dataclasses import dataclass
from typing import Dict, Tuple

import os
DEBUG_DECISION = os.getenv("DECISION_DEBUG", "0") == "1"

@dataclass
class PriceCtx:
    price: float
    atr: float | None
    near_event: bool = False
    prev_same_decision: bool = False

@dataclass
class GateConfig:
    p_base: float = 0.60       # 확률 임계
    margin_min: float = 0.10   # 1,2위 확률 차
    agree_lo: int = 2          # 합의 개수(기본)
    agree_lo_vol: int = 3      # 저변동 합의
    p_lo_vol: float = 0.65     # 저변동 확률
    p_hi_vol: float = 0.57     # 고변동 확률

def decide_with_gates(structs: Dict[str, Tuple[int, float, str]],
                      probs: Dict[str, float],
                      ctx: PriceCtx,
                      cfg: GateConfig = GateConfig()) -> tuple[str, str]:
    """returns (action: 'buy'|'sell'|'hold', reason)"""
    # 활성 신호 ≥2 검증
    active = [k for k,(d,c,_) in structs.items() if d != 0 and c > 0]
    if len(active) < 2:
        return "hold", "단일 신호"

    # 합의 개수 (신뢰도>=0.5인 실질 기여 신호만 집계)
    pos = sum(1 for (d, c, _e) in structs.values() if d > 0 and c >= 0.5)
    neg = sum(1 for (d, c, _e) in structs.values() if d < 0 and c >= 0.5)
    agree = max(pos, neg)

    # 변동성 레짐
    p_th = cfg.p_base
    need_agree = cfg.agree_lo
    if ctx.atr and ctx.price:
        vol = (ctx.atr / ctx.price)
        if vol <= 0.0003:  # 0.03%
            p_th = cfg.p_lo_vol
            need_agree = cfg.agree_lo_vol
        elif vol >= 0.0007:  # 0.07%
            p_th = cfg.p_hi_vol

    if agree < need_agree:
        return "hold", "합의 부족"

    # 확률/마진
    ordered = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    top, p_top = ordered[0]
    p2 = ordered[1][1] if len(ordered) > 1 else 0.0
    if p_top < p_th or (p_top - p2) < cfg.margin_min:
        return "hold", "확신 부족"

    # 이벤트 근접 시 1틱 추가 확인 요구
    if ctx.near_event and not ctx.prev_same_decision:
        return "hold", "이벤트 근접"

    if DEBUG_DECISION:
        print(f"[GATES] active={len(active)} agree={agree} p_th={p_th:.2f} need_agree={need_agree} probs={probs}")
    return top, "ok"