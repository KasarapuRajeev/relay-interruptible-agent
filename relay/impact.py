"""Explainable semantic impact scoring for interrupted plan dependencies."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal


ImpactAction = Literal["preserve", "cancel", "invalidate", "replan"]


CONCEPT_ALIASES = {
    "cost": {"budget", "price", "pricing", "cost", "amount", "affordability", "cheap"},
    "battery": {"battery", "endurance", "runtime", "power"},
    "performance": {"performance", "benchmark", "speed", "editing", "gaming", "compute"},
    "location": {"destination", "city", "location", "place", "country"},
    "time": {"duration", "day", "days", "schedule", "deadline", "time"},
    "topic": {"topic", "query", "subject", "research"},
    "priority": {"priority", "focus", "preference", "prefer", "prioritize"},
    "platform": {"os", "operating", "system", "windows", "android", "linux", "macos"},
}


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).lower().replace("_", " ")))


def _concepts(tokens: set[str]) -> set[str]:
    return {
        concept
        for concept, aliases in CONCEPT_ALIASES.items()
        if tokens.intersection(aliases)
    }


@dataclass(frozen=True, slots=True)
class ImpactDecision:
    target_id: str
    target_type: str
    action: ImpactAction
    score: float
    matched_dependencies: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_dependency(dependency: str, context_diff: Any) -> tuple[float, str | None]:
    """Score how strongly one dependency is affected by a structured context diff."""

    dependency_tokens = _tokens(dependency)
    dependency_concepts = _concepts(dependency_tokens)
    best_score = 0.0
    best_reason: str | None = None
    changes: dict[str, Any] = {
        **getattr(context_diff, "changed", {}),
        **{key: {"new": value} for key, value in getattr(context_diff, "added", {}).items()},
        **{key: {"old": value} for key, value in getattr(context_diff, "removed", {}).items()},
    }
    goal_only_change = set(changes) == {"goal"}
    for key, value in changes.items():
        key_tokens = _tokens(key)
        value_tokens = _tokens(value)
        changed_tokens = key_tokens | value_tokens
        if dependency == key:
            score, reason = 1.0, f"depends directly on changed constraint '{key}'"
        elif dependency_tokens.intersection(key_tokens):
            score, reason = 0.95, f"dependency name overlaps changed constraint '{key}'"
        elif dependency_concepts.intersection(_concepts(key_tokens)):
            score, reason = 0.9, f"dependency and '{key}' belong to the same semantic concept"
        elif dependency_tokens.intersection(changed_tokens):
            overlap = sorted(dependency_tokens.intersection(changed_tokens))
            score, reason = 0.78, f"changed value overlaps terms: {', '.join(overlap)}"
        elif dependency_concepts.intersection(_concepts(changed_tokens)):
            concepts = sorted(dependency_concepts.intersection(_concepts(changed_tokens)))
            score, reason = 0.7, f"changed value affects concept: {', '.join(concepts)}"
        elif goal_only_change:
            score, reason = 0.65, "the completed evidence belongs to the superseded goal"
        else:
            score, reason = 0.0, None
        if score > best_score:
            best_score, best_reason = score, reason
    return best_score, best_reason


def classify_impact(
    *,
    target_id: str,
    target_type: str,
    dependencies: list[str],
    context_diff: Any,
    active: bool = False,
    threshold: float = 0.6,
) -> ImpactDecision:
    """Return an explainable preserve/cancel/invalidate decision for one target."""

    matches: list[str] = []
    reasons: list[str] = []
    score = 0.0
    for dependency in dependencies:
        dependency_score, reason = score_dependency(dependency, context_diff)
        if dependency_score >= threshold:
            matches.append(dependency)
            if reason:
                reasons.append(reason)
        score = max(score, dependency_score)
    if score < threshold:
        return ImpactDecision(
            target_id=target_id,
            target_type=target_type,
            action="preserve",
            score=round(score, 2),
            matched_dependencies=[],
            reasons=["no material dependency on the changed context"],
        )
    action: ImpactAction = "cancel" if active else "invalidate"
    return ImpactDecision(
        target_id=target_id,
        target_type=target_type,
        action=action,
        score=round(score, 2),
        matched_dependencies=matches,
        reasons=reasons,
    )
