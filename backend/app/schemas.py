from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class ExerciseCreate(BaseModel):
    id: str = Field(min_length=3, max_length=80)
    title: str = Field(min_length=3, max_length=200)
    scenario: str = Field(min_length=10)
    exercise_date: date
    duration_minutes: int = Field(gt=0, le=1440)
    objectives: list[dict] = Field(default_factory=list)
    criteria: list[str] = Field(default_factory=list)
    evaluator_roles: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    expected_milestones: list[dict] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not all(ch.isalnum() or ch in "-_" for ch in value):
            raise ValueError("ID may contain only letters, numbers, hyphens, and underscores")
        return value


class FindingReview(BaseModel):
    decision: str
    reviewer: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=3000)


class FindingEdit(BaseModel):
    title: str = Field(min_length=4, max_length=240)
    observation: str = Field(min_length=4, max_length=4000)
    interpretation: str = Field(min_length=4, max_length=4000)
    reviewer: str = Field(min_length=2, max_length=120)


class ActionUpdate(BaseModel):
    owner: str | None = Field(default=None, max_length=160)
    priority: str = "medium"
    due_date: date | None = None
    acceptance_criteria: str = Field(min_length=8, max_length=4000)
    reviewer: str = Field(min_length=2, max_length=120)

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value: str) -> str:
        if value not in {"low", "medium", "high", "critical"}:
            raise ValueError("Priority must be low, medium, high, or critical")
        return value


class ActionReview(BaseModel):
    decision: str
    reviewer: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=3000)


class ActionClosure(BaseModel):
    closure_evidence: str = Field(min_length=12, max_length=4000)
    reviewer: str = Field(min_length=2, max_length=120)


class TranscriptIngest(BaseModel):
    transcript: str = Field(min_length=2)
    source_name: str = "evaluator-transcript.txt"
    language: str = "en"
    model_version: str = "pre-generated"
    segments: list[dict] = Field(default_factory=list)
