from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ProductRecord:
    name: str
    price: str
    article: str
    collected_at: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunResult:
    ok: bool
    products_collected: int
    message: str
    collected_at: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
