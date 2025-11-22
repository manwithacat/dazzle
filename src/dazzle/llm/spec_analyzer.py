"""
Specification analyzer for DAZZLE.

Analyzes natural language specifications and extracts structured information
for DSL generation.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .api_client import LLMAPIClient, LLMProvider
from .models import (
    SpecAnalysis,
    StateMachine,
    CRUDAnalysis,
    BusinessRule,
    MissingSpecification,
    QuestionCategory,
)


logger = logging.getLogger(__name__)


class SpecAnalyzer:
    """
    Analyzes natural language specifications using LLMs.

    Extracts:
    - State machines and transitions
    - CRUD completeness
    - Business rules
    - Clarifying questions
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize spec analyzer.

        Args:
            provider: LLM provider to use
            model: Model name (optional, uses defaults)
            api_key: API key (optional, reads from env)
            **kwargs: Additional arguments for LLMAPIClient
        """
        self.client = LLMAPIClient(
            provider=provider,
            model=model,
            api_key=api_key,
            **kwargs
        )

    def analyze(
        self,
        spec_content: str,
        spec_path: Optional[str] = None
    ) -> SpecAnalysis:
        """
        Analyze a specification and return structured analysis.

        Args:
            spec_content: The specification text (markdown, plain text, etc.)
            spec_path: Optional path to spec file (for error reporting)

        Returns:
            SpecAnalysis with state machines, CRUD analysis, questions, etc.

        Raises:
            ValueError: If analysis fails or returns invalid data
        """
        if spec_path is None:
            spec_path = "SPEC.md"

        logger.info(f"Analyzing specification: {spec_path}")
        logger.debug(f"Spec size: {len(spec_content)} characters")

        # Call LLM API
        raw_analysis = self.client.analyze_spec(spec_content, spec_path)

        # Parse and validate
        try:
            analysis = self._parse_analysis(raw_analysis)
            logger.info(f"Analysis complete: {self._get_analysis_summary(analysis)}")
            return analysis
        except Exception as e:
            logger.error(f"Failed to parse analysis: {e}")
            raise ValueError(f"Failed to parse LLM analysis: {e}")

    def _parse_analysis(self, raw_data: Dict[str, Any]) -> SpecAnalysis:
        """
        Parse raw LLM output into SpecAnalysis model.

        Args:
            raw_data: Dict from LLM API

        Returns:
            Validated SpecAnalysis instance

        Raises:
            ValueError: If data doesn't match expected schema
        """
        try:
            # Parse state machines
            state_machines = [
                StateMachine(**sm) for sm in raw_data.get('state_machines', [])
            ]

            # Parse CRUD analysis
            crud_analysis = [
                CRUDAnalysis(**crud) for crud in raw_data.get('crud_analysis', [])
            ]

            # Parse business rules
            business_rules = [
                BusinessRule(**rule) for rule in raw_data.get('business_rules', [])
            ]

            # Parse missing specifications
            missing_specs = [
                MissingSpecification(**missing)
                for missing in raw_data.get('missing_specifications', [])
            ]

            # Parse clarifying questions
            question_categories = [
                QuestionCategory(**cat)
                for cat in raw_data.get('clarifying_questions', [])
            ]

            # Create SpecAnalysis
            analysis = SpecAnalysis(
                state_machines=state_machines,
                crud_analysis=crud_analysis,
                business_rules=business_rules,
                missing_specifications=missing_specs,
                clarifying_questions=question_categories,
            )

            return analysis

        except Exception as e:
            logger.error(f"Failed to parse analysis data: {e}")
            logger.debug(f"Raw data keys: {raw_data.keys()}")
            raise

    def _get_analysis_summary(self, analysis: SpecAnalysis) -> str:
        """Get a human-readable summary of analysis results."""
        sm_count = len(analysis.state_machines)
        entity_count = len(analysis.crud_analysis)
        rule_count = len(analysis.business_rules)
        question_count = analysis.get_question_count()

        return (
            f"{sm_count} state machines, "
            f"{entity_count} entities, "
            f"{rule_count} business rules, "
            f"{question_count} questions"
        )

    def estimate_cost(self, spec_content: str) -> float:
        """
        Estimate the cost of analyzing a specification.

        Args:
            spec_content: The specification text

        Returns:
            Estimated cost in USD
        """
        spec_size_kb = len(spec_content) / 1024
        return self.client.estimate_cost(spec_size_kb)


def analyze_spec_file(
    spec_path: Path,
    provider: LLMProvider = LLMProvider.ANTHROPIC,
    **kwargs
) -> SpecAnalysis:
    """
    Convenience function to analyze a spec file.

    Args:
        spec_path: Path to specification file
        provider: LLM provider to use
        **kwargs: Additional arguments for SpecAnalyzer

    Returns:
        SpecAnalysis instance

    Raises:
        FileNotFoundError: If spec file doesn't exist
        ValueError: If analysis fails
    """
    if not spec_path.exists():
        raise FileNotFoundError(f"Specification file not found: {spec_path}")

    spec_content = spec_path.read_text()

    analyzer = SpecAnalyzer(provider=provider, **kwargs)
    return analyzer.analyze(spec_content, str(spec_path))
