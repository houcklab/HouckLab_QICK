"""Problem: one finding from resolving or validating, tied to a block and field."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Problem:
    level: str                     # error | warning | info
    message: str
    block_id: Optional[str] = None
    field: Optional[str] = None
    block_name: Optional[str] = None

    def __str__(self) -> str:
        where = self.block_name or ""
        if self.field:
            where += f".{self.field}" if where else self.field
        return f"[{self.level}] {where + ': ' if where else ''}{self.message}"


def has_errors(problems) -> bool:
    return any(p.level == "error" for p in problems)
