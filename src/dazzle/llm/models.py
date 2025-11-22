"""
Data models for LLM-assisted spec analysis.

These models represent the structured output from LLM analysis of natural language specs.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class QuestionPriority(str, Enum):
    """Priority level for clarifying questions."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BusinessRuleType(str, Enum):
    """Type of business rule."""
    VALIDATION = "validation"
    CONSTRAINT = "constraint"
    ACCESS_CONTROL = "access_control"
    CASCADE = "cascade"
    COMPUTED = "computed"


class StateTransition(BaseModel):
    """Represents a state machine transition."""
    from_state: str = Field(..., alias="from")
    to_state: str = Field(..., alias="to")
    trigger: str
    location: Optional[str] = None
    side_effects: List[str] = Field(default_factory=list)
    conditions: List[str] = Field(default_factory=list)
    who_can_trigger: Optional[str] = None

    class Config:
        populate_by_name = True


class ImpliedTransition(BaseModel):
    """Represents a transition that is implied but not explicitly defined."""
    from_state: str = Field(..., alias="from")
    to_state: str = Field(..., alias="to")
    reason: str
    question: str

    class Config:
        populate_by_name = True


class StateMachine(BaseModel):
    """Represents a state machine extracted from spec."""
    entity: str
    field: str
    states: List[str]
    transitions_found: List[StateTransition] = Field(default_factory=list)
    transitions_implied_but_missing: List[ImpliedTransition] = Field(default_factory=list)
    states_without_exit: List[str] = Field(default_factory=list)
    unreachable_states: List[str] = Field(default_factory=list)


class CRUDOperation(BaseModel):
    """Details about a CRUD operation."""
    found: bool
    location: Optional[str] = None
    who: Optional[str] = None
    question: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)
    filters_needed: List[str] = Field(default_factory=list)
    ui_needed: bool = True


class CRUDAnalysis(BaseModel):
    """CRUD completeness analysis for an entity."""
    entity: str
    operations_mentioned: Dict[str, CRUDOperation] = Field(default_factory=dict)
    missing_operations: List[str] = Field(default_factory=list)
    additional_operations: List[Dict[str, Any]] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)


class BusinessRule(BaseModel):
    """Business rule extracted from spec."""
    type: BusinessRuleType
    entity: str
    field: Optional[str] = None
    rule: str
    location: Optional[str] = None
    error_handling: Optional[str] = None
    implementation: Optional[str] = None


class QuestionOption(BaseModel):
    """An option for a clarifying question."""
    label: str
    description: str
    recommended: bool = False


class Question(BaseModel):
    """A clarifying question for the founder."""
    q: str
    context: str
    options: List[str]
    impacts: str
    id: Optional[str] = None


class QuestionCategory(BaseModel):
    """A category of related questions."""
    category: str
    priority: QuestionPriority
    questions: List[Question]


class MissingSpecification(BaseModel):
    """Something mentioned but not fully specified."""
    type: str  # e.g., "authentication", "notifications", "search"
    issue: str
    locations: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)


class SpecAnalysis(BaseModel):
    """Complete analysis of a specification."""
    state_machines: List[StateMachine] = Field(default_factory=list)
    crud_analysis: List[CRUDAnalysis] = Field(default_factory=list)
    business_rules: List[BusinessRule] = Field(default_factory=list)
    missing_specifications: List[MissingSpecification] = Field(default_factory=list)
    clarifying_questions: List[QuestionCategory] = Field(default_factory=list)

    def get_all_questions(self) -> List[Question]:
        """Get all questions across all categories."""
        questions = []
        for category in self.clarifying_questions:
            questions.extend(category.questions)
        return questions

    def get_high_priority_questions(self) -> List[Question]:
        """Get only high-priority questions."""
        questions = []
        for category in self.clarifying_questions:
            if category.priority == QuestionPriority.HIGH:
                questions.extend(category.questions)
        return questions

    def get_question_count(self) -> int:
        """Get total number of questions."""
        return sum(len(cat.questions) for cat in self.clarifying_questions)

    def get_state_machine_coverage(self) -> Dict[str, Any]:
        """Get coverage statistics for state machines."""
        total_transitions = sum(
            len(sm.transitions_found) + len(sm.transitions_implied_but_missing)
            for sm in self.state_machines
        )
        found_transitions = sum(len(sm.transitions_found) for sm in self.state_machines)
        missing_transitions = sum(len(sm.transitions_implied_but_missing) for sm in self.state_machines)

        return {
            'total_state_machines': len(self.state_machines),
            'total_transitions': total_transitions,
            'found_transitions': found_transitions,
            'missing_transitions': missing_transitions,
            'coverage_percent': (found_transitions / total_transitions * 100) if total_transitions > 0 else 100,
        }

    def get_crud_coverage(self) -> Dict[str, Any]:
        """Get CRUD completeness statistics."""
        total_entities = len(self.crud_analysis)
        total_operations = total_entities * 5  # C, R, U, D, List
        missing_count = sum(len(crud.missing_operations) for crud in self.crud_analysis)

        return {
            'total_entities': total_entities,
            'total_operations': total_operations,
            'missing_operations': missing_count,
            'coverage_percent': ((total_operations - missing_count) / total_operations * 100) if total_operations > 0 else 100,
        }
