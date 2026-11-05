from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class ExerciseCreate(BaseModel):
    id: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    scenario: str = Field(min_length=10)
    exercise_date: date
    duration_minutes: int = Field(gt=0, le=1440)
    objectives: list[dict] = Field(default_factory=list, max_length=50)
    criteria: list[str] = Field(default_factory=list, max_length=100)
    evaluator_roles: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    expected_milestones: list[dict] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not all(ch.isalnum() or ch in "-_" for ch in value):
            raise ValueError("ID may contain only letters, numbers, hyphens, and underscores")
        return value

    @field_validator("objectives")
    @classmethod
    def valid_objectives(cls, value: list[dict]) -> list[dict]:
        seen: set[str] = set()
        allowed_rules = {"elapsed_time", "reported_duration", "event_presence", "required_field"}
        for objective in value:
            if not isinstance(objective, dict):
                raise ValueError("Each objective must be an object with an ID and text")
            identifier = objective.get("id")
            text = objective.get("text")
            if (
                not isinstance(identifier, str)
                or not identifier.strip()
                or not all(char.isalnum() or char in "-_" for char in identifier)
            ):
                raise ValueError(
                    "Each objective needs a safe ID using letters, numbers, hyphens, or underscores"
                )
            if identifier in seen:
                raise ValueError(f"Objective ID {identifier!r} is duplicated")
            seen.add(identifier)
            if not isinstance(text, str) or len(text.strip()) < 4 or len(text) > 2000:
                raise ValueError("Each objective needs text between 4 and 2,000 characters")
            rule = objective.get("evaluation_rule", objective.get("rule"))
            if rule is not None and not isinstance(rule, dict):
                raise ValueError("An objective evaluation rule must be an object")
            if isinstance(rule, dict):
                rule_type = rule.get("type")
                if rule_type not in allowed_rules:
                    raise ValueError(f"Unsupported objective rule type: {rule_type!r}")
                threshold = rule.get("threshold_seconds")
                if threshold is not None and (
                    not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0
                ):
                    raise ValueError("threshold_seconds must be a non-negative integer")
                for term_field in (
                    "start_terms",
                    "completion_terms",
                    "completion_claim_terms",
                    "claim_terms",
                    "terms",
                    "missing_terms",
                    "present_terms",
                    "field_terms",
                ):
                    terms = rule.get(term_field)
                    if terms is not None and (
                        not isinstance(terms, list)
                        or len(terms) > 20
                        or any(not isinstance(term, str) or len(term) > 200 for term in terms)
                    ):
                        raise ValueError(f"{term_field} must be a list of up to 20 short strings")
        return value


class ObjectivesUpdate(BaseModel):
    objectives: list[dict] = Field(max_length=50)
    criteria: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("objectives")
    @classmethod
    def valid_objectives(cls, value: list[dict]) -> list[dict]:
        return ExerciseCreate.valid_objectives(value)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


class ExerciseAccessGrant(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class FindingReview(BaseModel):
    decision: str
    note: str = Field(default="", max_length=3000)


class FindingEdit(BaseModel):
    title: str = Field(min_length=4, max_length=240)
    observation: str = Field(min_length=4, max_length=4000)
    interpretation: str = Field(min_length=4, max_length=4000)


class ActionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=240)
    owner: str | None = Field(default=None, max_length=160)
    priority: str = "medium"
    due_date: date | None = None
    acceptance_criteria: str = Field(min_length=8, max_length=4000)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str | None) -> str | None:
        if value is not None and len(value.strip()) < 4:
            raise ValueError("Action title must contain at least 4 non-space characters")
        return value.strip() if value is not None else None

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value: str) -> str:
        if value not in {"low", "medium", "high", "critical"}:
            raise ValueError("Priority must be low, medium, high, or critical")
        return value


class ActionReview(BaseModel):
    decision: str
    note: str = Field(default="", max_length=3000)


class ActionClosure(BaseModel):
    closure_evidence: str = Field(min_length=12, max_length=4000)


class TranscriptIngest(BaseModel):
    transcript: str = Field(min_length=2, max_length=1_000_000)
    source_name: str = Field(default="evaluator-transcript.txt", max_length=255)
    language: str = Field(default="en", max_length=50)
    model_version: str = Field(default="pre-generated", max_length=120)
    segments: list[dict] = Field(default_factory=list, max_length=10_000)
