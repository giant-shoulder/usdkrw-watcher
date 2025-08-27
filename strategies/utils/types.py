# strategies/types.py
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

@dataclass
class StructSignal:
    key: str
    direction: int          # +1 / -1 / 0
    confidence: float       # 0..1
    evidence: str

StructsMap = Dict[str, Tuple[int, float, str]]  # (direction, confidence, evidence)

@dataclass
class ComboResult:
    message: str
    type: str               # 'buy'|'sell'|'neutral'
    score: int              # 0..100
    new_upper_level: float
    new_lower_level: float