# strategies/message_templates.py
from typing import List

KR_COLOR_HEAD = {
    "buy":  "🔴 🛒 매수 (Buy)",
    "sell": "🔵 💸 매도 (Sell)",
    "hold": "⚪ ⏸ 관망 (Hold)",
}

KR_STRENGTH_TITLE = {
    "buy":  "🔴 매수 신호 강도",
    "sell": "🔵 매도 신호 강도",
    "hold": "⚪ 관망 신호 강도",
}

def build_combo_message(kind: str, pct: int, bullets: List[str], gauge: str) -> str:
    """kind in {'buy','sell','hold'}"""
    head = KR_COLOR_HEAD.get(kind, KR_COLOR_HEAD["hold"])
    strength = KR_STRENGTH_TITLE.get(kind, KR_STRENGTH_TITLE["hold"])
    header_line = f"*{head} ({pct}/100)*"
    body = "\n".join(bullets) if bullets else "- (근거 없음)"
    return (
        f"{header_line}\n\n"
        f"📌 핵심 근거\n{body}\n\n"
        f"{strength}\n{gauge}"
    )