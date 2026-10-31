"""Strict model-output contracts and JSON-serializable LangGraph state."""
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict
from pydantic import ConfigDict, Field
from .models import Model


class StrictOutput(Model):
    model_config = ConfigDict(extra="forbid", strict=True)


class NumberEvidence(StrictOutput):
    value: str
    source: str  # Exact numeric substring, not an invented citation.


class ExtractedRequirement(StrictOutput):
    capability: str
    source: str


class ExtractedInquiry(StrictOutput):
    requirements: List[ExtractedRequirement]
    budget: Optional[NumberEvidence]
    users: Optional[NumberEvidence]
    requested_days: Optional[NumberEvidence]
    discount: Optional[NumberEvidence]


class CapabilityMatch(StrictOutput):
    capability: str
    product_id: str


class SolutionSelection(StrictOutput):
    product_ids: List[str]
    matches: List[CapabilityMatch]


class DraftSection(StrictOutput):
    heading: Literal["Overview", "Recommended solution", "Commercial terms", "Delivery and governance"]
    fact_ids: List[str]


class GroundedDraft(StrictOutput):
    """The model edits structure, never the commercial facts or promises."""
    sections: List[DraftSection]


class TraceEvent(Model):
    sequence: int
    node: str
    input_summary: str
    tool_name: str
    outcome: str
    error: Optional[str] = None
    elapsed_ms: int = Field(ge=0)
    attempt: int = 1


class AgentState(TypedDict, total=False):
    run_id: str
    request: Dict[str, Any]
    provider: Dict[str, Any]
    inquiry: Optional[Dict[str, Any]]
    requirements: List[Dict[str, Any]]
    extraction: Optional[Dict[str, Any]]
    supervisor_decision: str
    selected_products: List[str]
    quote: Optional[Dict[str, Any]]
    policy_findings: List[str]
    proposal: Optional[Dict[str, Any]]
    pending_approval: Optional[str]
    execution_results: Optional[Dict[str, Any]]
    verification_findings: List[str]
    errors: List[str]
    trace: List[Dict[str, Any]]
    phase: str
    status: str
    stop_status: Optional[str]
    supervisor_visits: int
    resume_requested: bool
    failed_node: Optional[str]
