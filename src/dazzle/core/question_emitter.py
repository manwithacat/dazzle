"""
DSL emitter for question specifications.

Converts QuestionSpec IR objects to DSL text for writing to .dsl files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.questions import QuestionSpec


def emit_question_dsl(question: QuestionSpec) -> str:
    """Serialize a QuestionSpec to DSL text."""
    from dazzle.core.ir.questions import QuestionStatus

    lines: list[str] = []

    lines.append(f'question {question.question_id} "{question.title}":')

    if question.description:
        lines.append(f'  "{question.description}"')

    if question.blocks:
        blocks_str = ", ".join(question.blocks)
        lines.append(f"  blocks: [{blocks_str}]")

    if question.raised_by:
        lines.append(f"  raised_by: {question.raised_by}")

    if question.status != QuestionStatus.OPEN:
        lines.append(f"  status: {question.status.value}")

    if question.resolution:
        lines.append(f'  resolution: "{question.resolution}"')

    return "\n".join(lines)


def get_next_question_id(questions: list[QuestionSpec]) -> str:
    """Determine the next question ID from a list of questions."""
    max_num = 0
    for q in questions:
        qid = q.question_id
        if qid.startswith("Q-"):
            try:
                num = int(qid[2:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"Q-{max_num + 1:03d}"


def append_questions_to_dsl(project_root: Path, questions: list[QuestionSpec]) -> Path:
    """Append question DSL blocks to ``dsl/questions.dsl``."""
    dsl_dir = project_root / "dsl"
    dsl_dir.mkdir(parents=True, exist_ok=True)

    questions_file = dsl_dir / "questions.dsl"
    blocks = [emit_question_dsl(q) for q in questions]
    new_text = "\n\n".join(blocks) + "\n"

    if questions_file.exists():
        existing = questions_file.read_text()
        if existing and not existing.endswith("\n"):
            existing += "\n"
        questions_file.write_text(existing + "\n" + new_text)
    else:
        questions_file.write_text(new_text)

    return questions_file
