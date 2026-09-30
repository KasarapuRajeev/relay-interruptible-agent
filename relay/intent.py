"""Small deterministic baseline for intent and localized slot correction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


CITY_PATTERN = re.compile(
    r"\b(?:to|for|visit|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)
BUDGET_PATTERN = re.compile(
    r"(?:under|budget(?:\s+of)?|within)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", re.I
)
DAYS_PATTERN = re.compile(r"\b(\d+)\s*[- ]?days?\b", re.I)
SUBJECT_PATTERN = re.compile(
    r"\b(?:study|revise|prepare for)\s+(?:my\s+)?([a-z][a-z ]{1,30}?)(?:\s+exam|\s+for|[,.]|$)",
    re.I,
)
PRIORITY_PATTERN = re.compile(
    r"\b(?:prioriti[sz]e|focus on|prefer)\s+([a-z][a-z0-9 +&-]{1,40}?)(?:[,.]|$)", re.I
)
CANCEL_PATTERN = re.compile(r"\b(stop|cancel|never mind|forget it|abort)\b", re.I)
REPLACEMENT_COMMAND_PATTERN = re.compile(
    r"\b(?:compare|research|investigate|find|plan|create|make|calculate|check|show|"
    r"explain|write|study|travel|get|tell)\b",
    re.I,
)
RESEARCH_TRIGGER_PATTERN = re.compile(
    r"\b(?:research|find information(?:\s+(?:about|on))?|investigate|compare)\s+",
    re.I,
)
CALCULATION_PATTERN = re.compile(r"\b(?:calculate|compute|evaluate)\s+(.+)$", re.I)


@dataclass(slots=True)
class IntentUpdate:
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    corrected_slots: list[str] = field(default_factory=list)
    is_cancel: bool = False
    is_pause: bool = False
    confidence: float = 0.5


def _extract_slots(text: str) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    city = CITY_PATTERN.search(text)
    budget = BUDGET_PATTERN.search(text)
    days = DAYS_PATTERN.search(text)
    subject = SUBJECT_PATTERN.search(text)
    priority = PRIORITY_PATTERN.search(text)
    calculation = CALCULATION_PATTERN.search(text)
    if city:
        slots["destination"] = city.group(1).strip()
    if budget:
        slots["budget_inr"] = int(budget.group(1).replace(",", ""))
    if days:
        slots["duration_days"] = int(days.group(1))
    if subject:
        slots["subject"] = subject.group(1).strip()
    if priority:
        slots["priority"] = priority.group(1).strip()
    if calculation:
        slots["expression"] = calculation.group(1).strip().rstrip("?.")
    return slots


def _cancel_is_followed_by_replacement(text: str) -> bool:
    """Distinguish a complete stop from `cancel X; do Y instead`."""

    cancellation = CANCEL_PATTERN.search(text)
    if cancellation is None:
        return False
    tail = text[cancellation.end() :]
    return REPLACEMENT_COMMAND_PATTERN.search(tail) is not None


def _extract_research_topic(text: str) -> str | None:
    """Use the newest explicit research command as the authoritative topic."""

    triggers = list(RESEARCH_TRIGGER_PATTERN.finditer(text))
    if not triggers:
        return None
    topic = text[triggers[-1].end() :].strip(" \t\r\n.,;:!?-")
    return topic or None


def understand(text: str, current_intent: str, current_slots: dict[str, Any]) -> IntentUpdate:
    lower = text.lower().strip()
    slots = _extract_slots(text)
    if CANCEL_PATTERN.search(text) and not _cancel_is_followed_by_replacement(text):
        return IntentUpdate(current_intent, is_cancel=True, confidence=0.98)

    if re.search(r"\b(pause|hold (?:this|that)|come back to)\b", lower):
        return IntentUpdate(current_intent, is_pause=True, confidence=0.95)

    if any(word in lower for word in ("weather", "temperature", "forecast")):
        intent = "weather_information"
        if "destination" in slots:
            slots["location"] = slots.pop("destination")
    elif re.search(r"\b(calculate|compute|evaluate)\b", lower):
        intent = "calculation"
    elif any(word in lower for word in ("study", "exam", "revise", "revision")):
        intent = "study_planning"
    elif any(word in lower for word in ("trip", "travel", "itinerary", "flight", "hotel")):
        intent = "travel_planning"
    elif any(
        phrase in lower
        for phrase in ("research", "find information", "investigate", "compare", "best laptop")
    ):
        intent = "research"
    elif current_intent == "research" and re.search(
        r"\b(actually|instead|i meant|change|make it|also|under|prioriti[sz]e)\b",
        lower,
    ):
        intent = "research"
    elif any(key in slots for key in ("destination", "budget_inr", "duration_days")):
        # A destination/budget correction can arrive without repeating "trip".
        intent = "travel_planning"
    elif current_intent != "unknown" and re.search(
        r"\b(actually|instead|i meant|change|make it|also)\b", lower
    ):
        intent = current_intent
    else:
        intent = "general_assistance"

    if intent == "research":
        topic = _extract_research_topic(text)
        if topic:
            slots["topic"] = topic
        elif "topic" not in current_slots:
            slots["topic"] = text.strip()

    corrected = [
        key for key, value in slots.items() if key in current_slots and current_slots[key] != value
    ]
    confidence = 0.9 if intent != "general_assistance" else 0.65
    return IntentUpdate(intent, slots, corrected, confidence=confidence)
