from __future__ import annotations
import re
from typing import Any


class SecretTracker:

    def __init__(self, state: dict[str, Any], target_plot_points: int = 18):
        self.state = state
        self.total = target_plot_points
        self._revealed: set[str] = set()

        clues = state.get("clues", [])
        non_rh   = [c for c in clues if not c.get("is_red_herring")]
        red_h    = [c for c in clues if c.get("is_red_herring")]

        step = 2
        self._clue_earliest: dict[str, int] = {}
        for clue in non_rh:
            prereq = clue.get("prerequisite_clue_id")
            earliest = self._clue_earliest.get(prereq, 0) + 2 if prereq else step
            self._clue_earliest[clue["id"]] = earliest
            step = min(earliest + 2, 10)

        for i, clue in enumerate(red_h):
            self._clue_earliest[clue["id"]] = 3 + i

        self._secret_earliest = {
            "murder_method":    max(6, self.total // 2),
            "culprit_identity": max(self.total - 3, 10),
            "alibi_break":      max(8, self.total // 2 + 1),
        }

    def can_reveal(self, secret: str, current_step: int) -> bool:
        if secret in self._revealed:
            return True
        if secret in self._secret_earliest:
            return current_step >= self._secret_earliest[secret]
        if secret in self._clue_earliest:
            return current_step >= self._clue_earliest[secret]
        return True

    def mark_revealed(self, secret: str) -> None:
        self._revealed.add(secret)

    def is_revealed(self, secret: str) -> bool:
        return secret in self._revealed

class EventMemoryBuffer:

    _TYPE_KEYWORDS: dict[str, list[str]] = {
        "WITNESS_REFUSES":   ["refuse", "won't talk", "silent", "no comment", "won't speak"],
        "CLUE_DESTROYED":    ["destroy", "burned", "missing", "stolen", "gone", "removed"],
        "FALSE_LEAD":        ["wrong", "false lead", "dead end", "mislead", "red herring"],
        "PHYSICAL_OBSTACLE": ["locked", "blocked", "obstacle", "barrier", "can't access"],
        "ALIBI_CHECK":       ["alibi", "whereabouts", "verify", "confirm location"],
        "CONFRONTATION":     ["confront", "accuse", "challenge", "interrogat"],
        "DISCOVERY":         ["find", "discover", "uncover", "reveal", "notice", "spot"],
        "REVELATION":        ["truth", "realize", "understand", "conclude", "killer is"],
    }

    def __init__(self):
        self._history: list[str] = []

    def classify(self, plot_point_text: str) -> str:
        lower = plot_point_text.lower()
        for event_type, keywords in self._TYPE_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return event_type
        return "OTHER"

    def is_repetitive(self, plot_point_text: str, window: int = 3) -> bool:
        event_type = self.classify(plot_point_text)
        if event_type == "OTHER":
            return False
        recent = self._history[-window:]
        return recent.count(event_type) >= 2

    def record(self, plot_point_text: str) -> str:
        event_type = self.classify(plot_point_text)
        self._history.append(event_type)
        return event_type


class ConsistencyChecker:

    def __init__(self, state: dict[str, Any], target_plot_points: int = 18):
        self.state   = state
        self.secrets = SecretTracker(state, target_plot_points)
        self.events  = EventMemoryBuffer()
        self._established_facts: list[str] = self._extract_initial_facts(state)

    def check(self, text: str, step: int) -> "CheckResult":
        secret_violation = self._check_secret_masking(text, step)
        if secret_violation:
            return CheckResult(False, f"Secret revealed too early: {secret_violation}")
        contradiction = self._check_contradictions(text)
        if contradiction:
            return CheckResult(False, f"Contradicts established fact: {contradiction}")

        if self.events.is_repetitive(text):
            return CheckResult(False, "Repetitive obstacle type — regenerate for variety")

        rationality_issue = self._check_rationality(text, step)
        if rationality_issue:
            return CheckResult(False, f"Irrational detective action: {rationality_issue}")

        self.events.record(text)
        self._update_revealed_secrets(text)
        self._established_facts.append(self._summarise_fact(text))
        return CheckResult(True, "OK")

    def mark_clue_discovered(self, clue_id: str) -> None:
        self.secrets.mark_revealed(clue_id)

    def _check_secret_masking(self, text: str, step: int) -> str | None:
        lower = text.lower()
        culprit_name = self.state.get("culprit", {}).get("name", "").lower()

        if culprit_name and culprit_name in lower:
            if not self.secrets.can_reveal("culprit_identity", step):
                return f"culprit identity ({culprit_name!r})"

        method_keywords = ["killed by", "murdered using", "weapon was", "cause of death"]
        if any(k in lower for k in method_keywords):
            if not self.secrets.can_reveal("murder_method", step):
                return "murder method"

        return None

    def _check_contradictions(self, text: str) -> str | None:
        lower = text.lower()
        for suspect in self.state.get("suspects", []):
            name = suspect.get("name", "").lower()
            if name and name in lower:
                alibi = suspect.get("alibi", "").lower()
                if "no alibi" in lower and name in lower and alibi:
                    return (
                        f"{suspect['name']!r} actually has alibi: {suspect['alibi']!r}"
                    )
        return None

    def _check_rationality(self, text: str, step: int) -> str | None:
        lower = text.lower()
        if step < 12 and any(k in lower for k in ["case is solved", "killer confirmed", "mystery solved"]):
            return "case resolved too early"
        return None

    def _update_revealed_secrets(self, text: str) -> None:
        lower = text.lower()
        for clue in self.state.get("clues", []):
            if clue["description"].lower()[:20] in lower:
                self.secrets.mark_revealed(clue["id"])

    def _extract_initial_facts(self, state: dict) -> list[str]:
        facts = []
        victim = state.get("victim", {})
        if victim.get("name"):
            facts.append(f"victim is {victim['name']}")
        setting = state.get("setting", {})
        if setting.get("location"):
            facts.append(f"crime took place at {setting['location']}")
        return facts

    def _summarise_fact(self, text: str) -> str:
        sentences = re.split(r"[.!?]", text.strip())
        return sentences[0].strip()[:120] if sentences else text[:120]

class CheckResult:
    def __init__(self, is_valid: bool, reason: str):
        self.is_valid = is_valid
        self.reason   = reason

    def __repr__(self) -> str:
        status = "Good" if self.is_valid else "Bad"
        return f"CheckResult({status} {self.reason!r})"
