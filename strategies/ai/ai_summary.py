# -*- coding: utf-8 -*-
"""
Natural-language composer for 30-minute USD/KRW summaries.

Expose a single entry point:
    compose_freeform_30m(...): -> (trend_text, advice_text)

This mirrors the interface we used earlier so `strategies/summary.py` can import
and use it directly:

    from strategies.ai.ai_summary import compose_freeform_30m

Later, you can swap the internals to call an LLM while keeping the signature.
"""
from __future__ import annotations
from typing import Dict, Optional, Tuple
import os
import json
import re
from textwrap import dedent

LLM_SUMMARY_DEBUG = os.getenv("LLM_SUMMARY_DEBUG", "0") == "1"

from openai import OpenAI

def _llm_compose_freeform_30m(
    *,
    start_rate: float,
    end_rate: float,
    high: float,
    low: float,
    diff: float,
    band_width: float,
    slope_10min: float,
    ai_probs: dict | None = None,
):
    if os.getenv("USE_LLM_SUMMARY", "0") != "1":
        return None

    if not os.getenv("OPENAI_API_KEY"):
        if LLM_SUMMARY_DEBUG:
            print("[LLM_SUMMARY] missing OPENAI_API_KEY")
        return None

    model = os.getenv("LLM_SUMMARY_MODEL", "gpt-4o-mini")
    max_tokens = int(os.getenv("LLM_SUMMARY_MAXTOK", "220"))

    sys_msg = dedent(
        """
        당신은 한국어로 응답하는 외환 요약가입니다. 아래 원달러(USD/KRW) 데이터로 30분 요약을 작성합니다.
        출력은 반드시 JSON 한 개 객체로만:
        {"trend_text":"...","advice_text":"..."}

        규칙:
        - trend_text: 반드시 제목(타이틀)처럼 간결하게 작성합니다. '... 흐름' 형태로 끝내고 장황한 설명은 넣지 않습니다.
          예) "상승 후 하락 흐름", "상승 후 횡보 흐름", "좁은 변동성 속 방향성 약화 흐름".
        - advice_text: 정확히 2문장으로 작성하되, 각 문장은 정중한 어미("...하시길 바랍니다.", "...하십시오." 등)로 끝나도록 합니다.
          ① 첫 문장: 진입/관망/청산 등 행동 지침(조건부 포함).
          ② 두 번째 문장: 리스크 관리(손절/분할/포지션 관리 등)를 강조.
          숫자·백분율은 쓰지 말고, 과장/확정(반드시/확실히 등)은 금지합니다.
        - USD/KRW라는 표기는 메시지에 직접 쓰지 않습니다(상위 포맷에서 처리).
        - JSON 외의 여분 텍스트/코드펜스 금지.
        """
    ).strip()

    # --- Derived features to help the LLM understand the intra-30m shape ---
    band = max(0.01, high - low)
    start_rel = (start_rate - low) / band  # 0..1
    end_rel = (end_rate - low) / band      # 0..1
    # swing magnitudes relative to band
    swing_up = max(0.0, high - max(start_rate, end_rate)) / band
    swing_down = max(0.0, min(start_rate, end_rate) - low) / band
    shape_hint = None
    # Heuristic: if net down but there was a sizeable upswing within the window → likely "상승 후 하락"
    if end_rate < start_rate and swing_up >= 0.30:
        shape_hint = "상승 후 하락"
    # If net up but sizeable downswing → likely "하락 후 상승"
    elif end_rate > start_rate and swing_down >= 0.30:
        shape_hint = "하락 후 상승"

    payload = {
        "start_rate": round(start_rate, 2),
        "end_rate": round(end_rate, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "diff": round(diff, 2),
        "band_width": round(band_width, 2),
        "slope_10min": round(slope_10min, 3),
        "ai_probs": ai_probs or {},
        # Derived helpers
        "band": round(band, 2),
        "start_pos": round(start_rel, 3),
        "end_pos": round(end_rel, 3),
        "swing_up_ratio": round(swing_up, 3),
        "swing_down_ratio": round(swing_down, 3),
        "shape_hint": shape_hint or "",
    }

    user_msg = f"""
    최근 30분 원달러 환율 데이터:
    {json.dumps(payload, ensure_ascii=False)}

    출력 형식(JSON):
    {{"trend_text":"...", "advice_text":"..."}}
    """.strip()

    client = OpenAI()
    try:
        resp = client.responses.create(
            model=model,
            input=f"SYSTEM:\n{sys_msg}\n\nUSER:\n{user_msg}",
            reasoning={"effort": "medium"},
            text={"verbosity": "medium"}
        )
        content_json = resp.output_text.strip()
    except Exception as e:
        if LLM_SUMMARY_DEBUG:
            print("[LLM_SUMMARY] Responses API failed:", e)
        return None

    try:
        text = re.sub(r"^```(json)?\s*|\s*```$", "", content_json.strip())
        if not text.strip().startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end+1]
        data = json.loads(text)
        trend = str(data.get("trend_text", "")).strip()
        advice = str(data.get("advice_text", "")).strip()
        # print("[LLM_SUMMARY] parsed:", {"trend": trend, "advice": advice})
        if trend and advice:
            return trend[:240], advice[:240]
    except Exception:
        if LLM_SUMMARY_DEBUG:
            preview = (content_json or "").strip()[:200]
            print("[LLM_SUMMARY] JSON parse failed, raw=", preview)

    return None

def compose_freeform_30m(
    *,
    start_rate: float,
    end_rate: float,
    high: float,
    low: float,
    diff: float,
    band_width: float,
    slope_10min: float,
    ai_probs: Optional[Dict[str, float]] = None,
    diff_weak: float = 0.05,
    bandwidth_tight: float = 1.50,
) -> Tuple[str, str]:
    """
    Build natural-language (trend_text, advice_text) for 30-minute summaries.
    - diff_weak: threshold (KRW) for near-flat movement
    - bandwidth_tight: threshold (KRW) for narrow-band classification

    You can later replace the body with an LLM call while keeping the same
    signature and return type.
    """
    llm_out = _llm_compose_freeform_30m(
        start_rate=start_rate,
        end_rate=end_rate,
        high=high,
        low=low,
        diff=diff,
        band_width=band_width,
        slope_10min=slope_10min,
        ai_probs=ai_probs,
    )
    if llm_out is not None:
        return llm_out

    up = diff > 0
    abs_diff = abs(diff)
    band = max(0.01, high - low)
    pos_from_low = (end_rate - low) / band  # 0..1

    # Volatility bucket text
    if band_width >= 3.0:
        vol_txt = "넓은 변동성"
    elif band_width >= 1.5:
        vol_txt = "보통 변동성"
    else:
        vol_txt = "좁은 변동성"

    # AI probability hint (optional)
    prob_txt = ""
    if ai_probs:
        pb = ai_probs.get("buy", 0.0)
        ps = ai_probs.get("sell", 0.0)
        ph = ai_probs.get("hold", 0.0)
        p_max = max(pb, ps, ph)
        if p_max >= 0.60:
            if p_max == pb:
                prob_txt = f" (AI 확신 {int(round(pb*100))}%)"
            elif p_max == ps:
                prob_txt = f" (AI 확신 {int(round(ps*100))}%)"
            else:
                prob_txt = f" (AI 확신 {int(round(ph*100))}%)"

    # Trend description
    if abs_diff < diff_weak and band_width <= bandwidth_tight:
        trend_text = f"횡보에 가깝습니다 — {vol_txt} 속 가격이 크게 벗어나지 않았습니다{prob_txt}."
    else:
        dir_txt = "상승" if up else "하락"
        if (up and slope_10min > diff_weak) or ((not up) and slope_10min < -diff_weak):
            slope_txt = "최근 10분은 추가로 가속 중"
        elif (up and slope_10min < 0) or ((not up) and slope_10min > 0):
            slope_txt = "최근 10분은 둔화 조짐"
        else:
            slope_txt = "최근 10분 변화는 제한적"
        pos_txt = "상단 근처" if pos_from_low >= 0.7 else ("중단" if pos_from_low >= 0.3 else "하단 근처")
        if diff == 0:
            diff_str = "0"
        else:
            diff_str = f"{diff:+.2f}"
        trend_text = (
            f"30분 동안 {dir_txt} 흐름입니다({diff_str}원). "
            f"현재는 {pos_txt}에 위치했고, {slope_txt}입니다 — {vol_txt}{prob_txt}."
        )

    # Advice text
    if up:
        if slope_10min <= -diff_weak:
            advice_text = "상승 후 눌림이 진행 중입니다. 성급한 추격 매수보다 조정 확인이 유리합니다."
        elif band_width >= 3.0 and pos_from_low >= 0.8:
            advice_text = "상단 과열 구간 접근 — 분할 접근 또는 이익 실현 검토."
        else:
            advice_text = "상승 흐름 유지 — 보수적으로 분할 매수 또는 관망 후 진입 고려."
    else:
        if slope_10min >= diff_weak:
            advice_text = "하락 후 반등 시도 — 성급한 매도보단 반등 강도 확인이 선행되어야 합니다."
        elif band_width >= 3.0 and pos_from_low <= 0.2:
            advice_text = "하단 과매도 구간 접근 — 반등 가능성 염두에 둔 관망/분할 매수 후보."
        else:
            advice_text = "하락 흐름 유지 — 무리한 진입보다 관망을 권고합니다."

    return trend_text, advice_text