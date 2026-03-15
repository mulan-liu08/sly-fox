"""
consistency_checker.py — Non-LLM component that validates proposed plot points
against the crime world state.

This is the "Consistency Checker" box in the architecture diagram. It enforces:
  1. No secret revealed before its designated step (logic masking).
  2. No contradiction of established facts.
  3. No repetition of the same obstacle type (anti-repetition buffer).
  4. Rationality filter — detective actions must be plausible given their knowledge.

All checks are purely symbolic / rule-based (no LLM calls).
"""

from __future__ import annotations
import re
from typing import Any


# ─── Secret tracking ─────────────────────────────────────────────────────────

class SecretTracker:
    """
    Tracks which secrets are allowed to be revealed at each plot point step.

    Secrets:
      - culprit_identity    (not until ≥ step 13 of 15)
      - murder_method       (not until ≥ step 11)
      - each clue_id        (not until its discovery step)
      - each alibi break    (not until ≥ step 8)
    """

    def __init__(self, state: dict[str, Any], target_plot_points: int = 18):
        self.state = state
        self.total = target_plot_points
        self._revealed: set[str] = set()

        # Assign discovery step for each clue (spread evenly, chained clues later)
        clues = state.get("clues", [])
        non_rh   = [c for c in clues if not c.get("is_red_herring")]
        red_h    = [c for c in clues if c.get("is_red_herring")]

        # Non-red-herring clues spread across steps 2–10
        step = 2
        self._clue_earliest: dict[str, int] = {}
        for clue in non_rh:
            prereq = clue.get("prerequisite_clue_id")
            earliest = self._clue_earliest.get(prereq, 0) + 2 if prereq else step
            self._clue_earliest[clue["id"]] = earliest
            step = min(earliest + 2, 10)

        # Red herrings can appear early (they mislead)
        for i, clue in enumerate(red_h):
            self._clue_earliest[clue["id"]] = 3 + i

        # Fixed secrets
        self._secret_earliest = {
            "murder_method":    max(6, self.total // 2),
            "culprit_identity": max(self.total - 3, 10),
            "alibi_break":      max(8, self.total // 2 + 1),
        }

    def can_reveal(self, secret: str, current_step: int) -> bool:
        """Return True if secret may be revealed at current_step."""
        if secret in self._revealed:
            return True  # already revealed, fine
        if secret in self._secret_earliest:
            return current_step >= self._secret_earliest[secret]
        if secret in self._clue_earliest:
            return current_step >= self._clue_earliest[secret]
        return True  # unknown secret — allow by default

    def mark_revealed(self, secret: str) -> None:
        self._revealed.add(secret)

    def is_revealed(self, secret: str) -> bool:
        return secret in self._revealed


# ─── Event type memory buffer (anti-repetition) ───────────────────────────────

class EventMemoryBuffer:
    """
    Tracks the *type* of obstacle/event at each step to prevent repetition.

    Event types (coarse categories):
      - WITNESS_REFUSES      (a witness won't talk)
      - CLUE_DESTROYED       (evidence gone)
      - FALSE_LEAD           (detective chases wrong suspect)
      - PHYSICAL_OBSTACLE    (locked door, missing key, etc.)
      - ALIBI_CHECK          (verifying an alibi)
      - CONFRONTATION        (direct confrontation with suspect)
      - DISCOVERY            (finding a new clue)
      - REVELATION           (major truth revealed)
      - OTHER
    """

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
        self._history: list[str] = []   # ordered list of event types seen

    def classify(self, plot_point_text: str) -> str:
        lower = plot_point_text.lower()
        for event_type, keywords in self._TYPE_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return event_type
        return "OTHER"

    def is_repetitive(self, plot_point_text: str, window: int = 3) -> bool:
        """Return True if the same event type appeared within the last `window` steps."""
        event_type = self.classify(plot_point_text)
        if event_type == "OTHER":
            return False
        recent = self._history[-window:]
        return recent.count(event_type) >= 2

    def record(self, plot_point_text: str) -> str:
        event_type = self.classify(plot_point_text)
        self._history.append(event_type)
        return event_type


# ─── Consistency Checker ─────────────────────────────────────────────────────

class ConsistencyChecker:
    """
    The main non-LLM consistency gate.

    Usage:
        checker = ConsistencyChecker(crime_world_state)
        result  = checker.check(proposed_plot_point_text, current_step)
        if result.is_valid:
            accumulator.add(proposed_plot_point_text)
        else:
            # regenerate
    """

    def __init__(self, state: dict[str, Any], target_plot_points: int = 18):
        self.state   = state
        self.secrets = SecretTracker(state, target_plot_points)
        self.events  = EventMemoryBuffer()
        self._established_facts: list[str] = self._extract_initial_facts(state)

    # ── Public ────────────────────────────────────────────────────────────────

    def check(self, text: str, step: int) -> "CheckResult":
        """
        Validate a proposed plot point.

        Returns a CheckResult with .is_valid and .reason.
        """
        # 1. Secret masking — does the text reveal something too early?
        secret_violation = self._check_secret_masking(text, step)
        if secret_violation:
            return CheckResult(False, f"Secret revealed too early: {secret_violation}")

        # 2. Contradiction check — does the text contradict known facts?
        contradiction = self._check_contradictions(text)
        if contradiction:
            return CheckResult(False, f"Contradicts established fact: {contradiction}")

        # 3. Anti-repetition
        if self.events.is_repetitive(text):
            return CheckResult(False, "Repetitive obstacle type — regenerate for variety")

        # 4. Rationality filter — detective actions must make sense
        rationality_issue = self._check_rationality(text, step)
        if rationality_issue:
            return CheckResult(False, f"Irrational detective action: {rationality_issue}")

        # All good — record the event and update secrets
        self.events.record(text)
        self._update_revealed_secrets(text)
        self._established_facts.append(self._summarise_fact(text))
        return CheckResult(True, "OK")

    def mark_clue_discovered(self, clue_id: str) -> None:
        self.secrets.mark_revealed(clue_id)

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_secret_masking(self, text: str, step: int) -> str | None:
        lower = text.lower()
        culprit_name = self.state.get("culprit", {}).get("name", "").lower()

        # Check culprit identity
        if culprit_name and culprit_name in lower:
            if not self.secrets.can_reveal("culprit_identity", step):
                return f"culprit identity ({culprit_name!r})"

        # Check murder method keywords
        method_keywords = ["killed by", "murdered using", "weapon was", "cause of death"]
        if any(k in lower for k in method_keywords):
            if not self.secrets.can_reveal("murder_method", step):
                return "murder method"

        return None

    def _check_contradictions(self, text: str) -> str | None:
        lower = text.lower()
        # Check alibi contradictions for innocent suspects
        for suspect in self.state.get("suspects", []):
            name = suspect.get("name", "").lower()
            if name and name in lower:
                alibi = suspect.get("alibi", "").lower()
                # Very naive: if text says the suspect "has no alibi" but they do, flag it
                if "no alibi" in lower and name in lower and alibi:
                    return (
                        f"{suspect['name']!r} actually has alibi: {suspect['alibi']!r}"
                    )
        return None

    def _check_rationality(self, text: str, step: int) -> str | None:
        lower = text.lower()
        # Detective shouldn't solve the case before step 12
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
        # Keep just the first sentence as a "fact" summary
        sentences = re.split(r"[.!?]", text.strip())
        return sentences[0].strip()[:120] if sentences else text[:120]


# ─── Result dataclass ─────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, is_valid: bool, reason: str):
        self.is_valid = is_valid
        self.reason   = reason

    def __repr__(self) -> str:
        status = "✓" if self.is_valid else "✗"
        return f"CheckResult({status} {self.reason!r})"
