
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