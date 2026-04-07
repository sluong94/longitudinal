"""
Trend Eligibility Engine — applies strict rules to determine
which variables can be safely trended across waves.

This is separate from the manifest builder so it can be used
independently for runtime filtering and validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .manifest import ManifestEntry, ExactMatchStatus


@dataclass
class TrendEligibilityRule:
    """A single rule that must pass for a variable to be trend-eligible."""

    name: str
    description: str

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        raise NotImplementedError


class PresentInBothRule(TrendEligibilityRule):
    """Variable must exist in both historical and latest wave."""

    def __init__(self):
        super().__init__(
            name="present_in_both",
            description="Variable must be present in both historical and latest wave datasets",
        )

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        if entry.historical_present and entry.latest_wave_present:
            return True, ""
        if not entry.historical_present:
            return False, "Not present in historical dataset"
        return False, "Not present in latest wave"


class ExactMatchRule(TrendEligibilityRule):
    """Response options must match exactly between waves."""

    def __init__(self):
        super().__init__(
            name="exact_match",
            description="Response options must be identical across waves",
        )

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        if entry.exact_match_status == ExactMatchStatus.EXACT_MATCH:
            return True, ""
        return False, f"Match status: {entry.exact_match_status.value}"


class NotExcludedRule(TrendEligibilityRule):
    """Variable must not be in an excluded category."""

    def __init__(self):
        super().__init__(
            name="not_excluded",
            description="Variable must not be admin/QC/timing/excluded",
        )

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        if entry.exact_match_status == ExactMatchStatus.EXCLUDED:
            return False, "Variable is in excluded category"
        return True, ""


class DisplayEligibleRule(TrendEligibilityRule):
    """Variable must be approved for display."""

    def __init__(self):
        super().__init__(
            name="display_eligible",
            description="Variable must be eligible for dashboard display",
        )

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        if entry.display_eligible:
            return True, ""
        return False, "Variable is not display-eligible"


class NotOpenEndedRule(TrendEligibilityRule):
    """Open-ended text responses are not suitable for trending."""

    def __init__(self):
        super().__init__(
            name="not_open_ended",
            description="Open-ended text variables cannot be trended",
        )

    def check(self, entry: ManifestEntry) -> tuple[bool, str]:
        if entry.question_type == "text_open":
            return False, "Open-ended text variable"
        return True, ""


class TrendEligibility:
    """
    Applies an ordered set of rules to determine trend eligibility.

    All rules must pass for a variable to be trend-eligible.
    The first failing rule provides the reason code.
    """

    DEFAULT_RULES = [
        NotExcludedRule(),
        DisplayEligibleRule(),
        PresentInBothRule(),
        ExactMatchRule(),
        NotOpenEndedRule(),
    ]

    def __init__(self, rules: Optional[list[TrendEligibilityRule]] = None):
        self.rules = rules or self.DEFAULT_RULES

    def assess(self, entry: ManifestEntry) -> tuple[bool, str]:
        """
        Assess a single manifest entry for trend eligibility.

        Returns (eligible: bool, reason: str).
        If eligible, reason is "All rules passed".
        If not eligible, reason is the first failing rule's message.
        """
        for rule in self.rules:
            passed, reason = rule.check(entry)
            if not passed:
                return False, f"[{rule.name}] {reason}"
        return True, "All rules passed"

    def assess_all(
        self, entries: list[ManifestEntry]
    ) -> list[tuple[ManifestEntry, bool, str]]:
        """Assess all entries and return results with reasons."""
        return [(e, *self.assess(e)) for e in entries]

    def filter_trendable(
        self, entries: list[ManifestEntry]
    ) -> list[ManifestEntry]:
        """Return only the entries that pass all trend eligibility rules."""
        return [e for e in entries if self.assess(e)[0]]

    def audit_report(self, entries: list[ManifestEntry]) -> dict:
        """
        Generate an audit report showing how many variables pass/fail each rule.
        """
        report = {
            "total": len(entries),
            "trend_eligible": 0,
            "rule_failures": {rule.name: 0 for rule in self.rules},
            "first_failure_distribution": {},
        }

        for entry in entries:
            eligible, reason = self.assess(entry)
            if eligible:
                report["trend_eligible"] += 1
            else:
                # Extract rule name from reason
                rule_name = reason.split("]")[0].strip("[") if "]" in reason else "unknown"
                report["first_failure_distribution"][rule_name] = (
                    report["first_failure_distribution"].get(rule_name, 0) + 1
                )

        # Count individual rule failures (not just first failure)
        for entry in entries:
            for rule in self.rules:
                passed, _ = rule.check(entry)
                if not passed:
                    report["rule_failures"][rule.name] += 1

        return report
