# strategies/feedback.py
import json
from datetime import datetime

def log_decision(db_conn, *, features: dict, probs: dict, action: str, reason: str, price: float):
    payload = {
        "ts": datetime.utcnow().isoformat(),
        "features": features, "probs": probs,
        "action": action, "reason": reason, "price": price,
    }
    # TODO: DB 테이블 저장; 파일로 우선 로깅 가능
    print("[AI-DECISION]", json.dumps(payload, ensure_ascii=False))