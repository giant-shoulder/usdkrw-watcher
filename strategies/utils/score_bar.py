
def get_score_bar(score, signal_type="neutral", max_score=100, bar_length=10):
    filled = int(round(bar_length * score / max_score))
    chars = {
        "buy": "🟩", "sell": "🟥", "conflict": "🟨", "neutral": "⬜"
    }
    fill = chars.get(signal_type, "⬜")
    empty = "⬛"
    direction = {
        "buy": "🟢 매수 신호 강도", "sell": "🔴 매도 신호 강도",
        "conflict": "⚠️ 전략간 방향성 충돌 강도", "neutral": "⬜ 신호 강도"
    }.get(signal_type, "⬜ 신호 강도")

    return f"{direction}\n{fill * filled}{empty * (bar_length - filled)} {score}점"


from typing import Union

def make_score_gauge(label: str, score: Union[int, float], width: int = 10) -> str:
    """
    Colored 10-block gauge.
    - SELL (매도): red blocks (🟥) with black empties (⬛)
    - BUY (매수):  blue blocks (🟦) with black empties (⬛)
    - HOLD/Other: white blocks (⬜) with black empties (⬛)
    The `label` is inspected to infer the color (supports Korean/English keywords and icons).
    """
    try:
        v = int(round(float(score)))
    except Exception:
        v = 0
    v = max(0, min(100, v))
    filled_n = round(v / (100 / width))
    empty_n = width - filled_n

    s = label or ""
    lower = s.lower()
    is_sell = ("매도" in s) or ("sell" in lower) or ("💸" in s) or ("🔴" in s)
    is_buy  = ("매수" in s) or ("buy" in lower)  or ("🛒" in s) or ("🔵" in s)

    if is_sell:
        filled = "🟥" * filled_n
    elif is_buy:
        filled = "🟦" * filled_n
    else:
        filled = "⬜" * filled_n

    empty = "⬛" * empty_n
    return f"{filled}{empty} {v}점"