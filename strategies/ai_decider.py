from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import math

# Minimal, dependency-free online logistic model

@dataclass
class Sample:
    x: Dict[str, float]
    y: int  # +1 buy, -1 sell, 0 hold

class AIDecider:
    """
    Lightweight online logistic classifier with 3 heads (buy/sell/hold) via one-vs-rest.
    - No external libraries required.
    - Can be updated online with feedback (labels) via SGD.
    - Uses features derived from structured signals.
    """
    def __init__(self, lr: float = 0.05):
        self.lr = lr
        # weights per class
        self.W: Dict[str, Dict[str, float]] = {
            "buy": {}, "sell": {}, "hold": {"bias": 0.0}
        }
        # sensible cold-start priors: favor HOLD unless 2+ strong agreeing signals
        self.W["buy"] = {"bias": -0.8}
        self.W["sell"] = {"bias": -0.8}
        # interaction priors
        # lower_break + golden ⇒ buy
        self.W["buy"].update({
            "expected_dir_+1": 0.6,
            "boll_dir_+1": 0.25,
            "cross_type_golden": 0.6,
            "agree_count": 0.3,
        })
        # upper_break + dead ⇒ sell
        self.W["sell"].update({
            "expected_dir_-1": 0.6,
            "boll_dir_-1": 0.25,
            "cross_type_dead": 0.6,
            "agree_count": 0.3,
        })

    def _dot(self, w: Dict[str, float], x: Dict[str, float]) -> float:
        s = w.get("bias", 0.0)
        for k, v in x.items():
            s += w.get(k, 0.0) * v
        return s

    def _sigmoid(self, z: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-20, min(20, z))))

    def _proba(self, x: Dict[str, float]) -> Dict[str, float]:
        logits = {c: self._dot(self.W[c], x) for c in self.W}
        # softmax-ish from logistic heads
        exps = {c: math.exp(max(-20, min(20, logits[c]))) for c in logits}
        Z = sum(exps.values()) or 1.0
        return {c: exps[c] / Z for c in exps}

    def predict(self, features: Dict[str, float]) -> Tuple[str, Dict[str, float]]:
        p = self._proba(features)
        # choose best class with margin threshold to avoid over-eager trades
        best = max(p.items(), key=lambda kv: kv[1])[0]
        conf = p[best]
        action = best if conf >= 0.55 else "hold"
        return action, p

    def update(self, features: Dict[str, float], label: str):
        # one-vs-rest logistic regression SGD
        y_map = {"buy": 0.0, "sell": 0.0, "hold": 0.0}
        if label in y_map:
            y_map[label] = 1.0
        p = self._proba(features)
        for c in self.W:
            err = y_map[c] - p[c]
            self.W[c]["bias"] = self.W[c].get("bias", 0.0) + self.lr * err
            for k, v in features.items():
                self.W[c][k] = self.W[c].get(k, 0.0) + self.lr * err * v

# --- Feature builder ---

def build_features(structs: Dict[str, tuple]) -> Dict[str, float]:
    """Turn structured strategy outputs into a flat numeric dict."""
    x: Dict[str, float] = {"bias": 1.0}
    agree = 0
    dirs = []
    for key, (d, c, _ev) in structs.items():
        if d != 0 and c > 0:
            dirs.append(d)
            x[f"{key}_dir_{d:+d}"] = 1.0 * c
            x[f"{key}_conf"] = c
    if any(d > 0 for d in dirs) or any(d < 0 for d in dirs):
        agree = max(sum(1 for d in dirs if d > 0), sum(1 for d in dirs if d < 0))
    x["agree_count"] = float(agree)
    return x