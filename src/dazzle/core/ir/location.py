"""Source location tracking for IR nodes.

Records the file, line, and column where a DSL construct was defined,
enabling source-mapped error messages and IDE navigation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SourceLocation(BaseModel):
    """Source position where a DSL construct was defined.

    Attributes:
        file: Path to the DSL file (relative or absolute)
        line: 1-indexed line number
        column: 1-indexed column number
    """

    file: str
    line: int
    column: int

    model_config = ConfigDict(frozen=True)

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"
