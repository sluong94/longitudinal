"""
Harmonization Manifest — the core artifact that determines
what can be combined, what is latest-wave-only, and what is trendable.

This is the single most important piece of the longitudinal system.
It is built deterministically from parsed source metadata and
produces a transparent, auditable record of every harmonization decision.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from .variable_registry import VariableRegistry, VariableCategory


class ExactMatchStatus(str, Enum):
    """Result of comparing a variable across historical and latest wave."""
    EXACT_MATCH = "exact_match"
    NAME_MATCH_VALUES_DIFFER = "name_match_values_differ"
    LATEST_WAVE_ONLY = "latest_wave_only"
    HISTORICAL_ONLY = "historical_only"
    EXCLUDED = "excluded"
    NOT_ASSESSED = "not_assessed"


class TrendEligibilityStatus(str, Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    PENDING_REVIEW = "pending_review"


# Canonical reason codes for why a variable is not trendable
REASON_CODES = {
    "exact_match": "Variable is exact-match trendable",
    "latest_only": "Variable exists only in latest wave",
    "historical_only": "Variable exists only in historical dataset",
    "values_differ": "Response options differ between waves",
    "question_text_differs": "Question wording differs between waves",
    "population_mismatch": "Eligible population not comparable",
    "admin_excluded": "Administrative/operational variable excluded",
    "hidden_not_whitelisted": "Hidden/derived variable not whitelisted",
    "open_ended": "Open-ended variable not suitable for trending",
    "insufficient_waves": "Present in fewer than 2 waves",
    "pending_manual_review": "Requires manual review before trending",
}


@dataclass
class ManifestEntry:
    """A single row in the harmonization manifest."""

    canonical_variable_id: str
    question_family: str
    canonical_question_text: str
    source_dataset: str  # 'historical', 'latest_wave', 'both'
    source_wave: str  # e.g. 'W13-W32', 'W33', 'W13-W33'
    source_variable_name: str
    response_options_hash: str
    question_type: str
    value_labels: dict[str, str]
    latest_wave_present: bool
    historical_present: bool
    exact_match_status: ExactMatchStatus
    trend_eligible: bool
    reason_not_trendable: str
    analysis_population_id: str
    country_mode_default: str
    display_eligible: bool
    segment_eligible: bool
    notes: str = ""


class HarmonizationManifest:
    """
    Generates and holds the harmonization manifest.

    The manifest is built by comparing the variable registry
    (which combines labeling workbook + W33 datamap) and applying
    strict trendability rules.

    Supports a whitelist for manually approved trendable variables
    that would otherwise fail strict matching (e.g., variables present
    in both datasets but only documented on one side).
    """

    def __init__(
        self,
        variable_registry: VariableRegistry,
        trend_whitelist: Optional[set[str]] = None,
    ):
        self.registry = variable_registry
        self._entries: list[ManifestEntry] = []
        self.trend_whitelist = trend_whitelist or set()

    def build(
        self,
        labeling_vars: dict,
        w33_datamap: dict,
        default_population_id: str = "trend_default_employed_18_65",
    ) -> list[ManifestEntry]:
        """
        Build the full harmonization manifest.

        Compares each variable across historical labeling workbook and
        W33 datamap, determines exact-match status, and applies
        trendability rules.
        """
        self._entries = []

        for var in self.registry.list_all():
            entry = self._assess_variable(
                var, labeling_vars, w33_datamap, default_population_id
            )
            self._entries.append(entry)

        return self._entries

    def _assess_variable(
        self,
        var,
        labeling_vars: dict,
        w33_datamap: dict,
        default_population_id: str,
    ) -> ManifestEntry:
        """Assess a single variable for harmonization and trendability."""

        code = var.canonical_id
        in_hist = var.in_historical
        in_latest = var.in_latest_wave
        hist_defn = labeling_vars.get(code)
        w33_defn = w33_datamap.get(code)

        # Determine source dataset
        if in_hist and in_latest:
            source_dataset = "both"
            source_wave = "W13-W33"
        elif in_latest:
            source_dataset = "latest_wave"
            source_wave = "W33"
        elif in_hist:
            source_dataset = "historical"
            source_wave = "W13-W32"
        else:
            source_dataset = "metadata_only"
            source_wave = ""

        # Determine question family (prefix before digits/underscores)
        question_family = self._infer_question_family(code)

        # Determine exact match status
        exact_match_status, match_reason = self._check_exact_match(
            var, hist_defn, w33_defn
        )

        # Apply trendability rules
        trend_eligible, reason = self._apply_trend_rules(
            var, exact_match_status, match_reason
        )

        # Population and country defaults
        analysis_pop = default_population_id if trend_eligible else ""
        country_mode = "balanced_intersection" if trend_eligible else "all_available"

        return ManifestEntry(
            canonical_variable_id=code,
            question_family=question_family,
            canonical_question_text=var.question_text,
            source_dataset=source_dataset,
            source_wave=source_wave,
            source_variable_name=code,
            response_options_hash=var.response_options_hash,
            question_type=var.question_type.value,
            value_labels=var.value_labels,
            latest_wave_present=in_latest,
            historical_present=in_hist,
            exact_match_status=exact_match_status,
            trend_eligible=trend_eligible,
            reason_not_trendable=reason,
            analysis_population_id=analysis_pop,
            country_mode_default=country_mode,
            display_eligible=var.display_eligible,
            segment_eligible=var.segment_eligible,
            notes="",
        )

    def _infer_question_family(self, code: str) -> str:
        """
        Extract the question family prefix.

        Examples: 'AI_consumer1r3' -> 'AI_consumer1'
                  'Work_sentiment1r5' -> 'Work_sentiment1'
                  'A2' -> 'A2'
                  'B1' -> 'B1'
        """
        # Strip trailing 'r\d+' or 'r\d+oe' suffix for multi-response items
        import re
        match = re.match(r"^(.+?)(?:r\d+(?:oe)?)?$", code)
        if match:
            base = match.group(1)
            # Further group: 'AI_workforcenew1' stays as-is
            return base
        return code

    def _check_exact_match(
        self,
        var,
        hist_defn,
        w33_defn,
    ) -> tuple[ExactMatchStatus, str]:
        """
        Determine exact-match status between historical and latest wave.

        Uses strict comparison: variable name must match AND
        response options hash must match.
        """
        # Exclusion categories
        if var.category in (
            VariableCategory.ADMIN,
            VariableCategory.QC,
            VariableCategory.TIMING,
            VariableCategory.GEO,
            VariableCategory.EXCLUDE,
        ):
            return ExactMatchStatus.EXCLUDED, "admin_excluded"

        if not var.in_historical and not var.in_latest_wave:
            return ExactMatchStatus.NOT_ASSESSED, "metadata_only"

        if var.in_latest_wave and not var.in_historical:
            return ExactMatchStatus.LATEST_WAVE_ONLY, "latest_only"

        if var.in_historical and not var.in_latest_wave:
            return ExactMatchStatus.HISTORICAL_ONLY, "historical_only"

        # Both present — compare response options
        if hist_defn and w33_defn:
            hist_hash = hist_defn.response_options_hash
            w33_hash = w33_defn.response_options_hash

            # Both have value labels — compare hashes
            if hist_hash and w33_hash:
                if hist_hash == w33_hash:
                    return ExactMatchStatus.EXACT_MATCH, "exact_match"
                else:
                    return (
                        ExactMatchStatus.NAME_MATCH_VALUES_DIFFER,
                        "values_differ",
                    )

            # One or both lack value labels — could be open-ended or
            # the labeling workbook may not document values for this var
            if not hist_hash and not w33_hash:
                # Both open-ended or undocumented
                return ExactMatchStatus.EXACT_MATCH, "exact_match"

            # Mismatch in documentation level
            return ExactMatchStatus.NAME_MATCH_VALUES_DIFFER, "values_differ"

        # One side lacks metadata — conservative: name match only
        if hist_defn or w33_defn:
            return ExactMatchStatus.NAME_MATCH_VALUES_DIFFER, "pending_manual_review"

        # Neither side has metadata but both present in data
        return ExactMatchStatus.NOT_ASSESSED, "pending_manual_review"

    def _apply_trend_rules(
        self,
        var,
        exact_match_status: ExactMatchStatus,
        match_reason: str,
    ) -> tuple[bool, str]:
        """
        Apply strict trendability rules.

        A variable is trendable ONLY if:
        1. Present in both historical and latest wave
        2. Exact match on response options (or whitelisted)
        3. Not an excluded category
        4. Not hidden/derived (unless whitelisted)
        5. Not open-ended

        Variables in the trend_whitelist bypass rules 2 and 4
        (value-match strictness) but still must be present in both
        datasets and not in excluded categories.
        """
        is_whitelisted = var.canonical_id in self.trend_whitelist

        # Rule 1: Must be present in both (no whitelist bypass)
        if exact_match_status in (
            ExactMatchStatus.LATEST_WAVE_ONLY,
            ExactMatchStatus.HISTORICAL_ONLY,
        ):
            return False, REASON_CODES.get(match_reason, match_reason)

        # Rule 2: Excluded categories cannot be whitelisted
        if exact_match_status == ExactMatchStatus.EXCLUDED:
            return False, REASON_CODES["admin_excluded"]

        # Rule 3: Hidden/derived must be whitelisted
        if var.category == VariableCategory.HIDDEN and not var.whitelist_override and not is_whitelisted:
            return False, REASON_CODES["hidden_not_whitelisted"]

        # Rule 4: Values must match exactly — OR be whitelisted
        if exact_match_status == ExactMatchStatus.NAME_MATCH_VALUES_DIFFER:
            if is_whitelisted:
                return True, "Whitelisted: manual approval overrides value-match check"
            return False, REASON_CODES["values_differ"]

        # Rule 5: Open-ended not trendable (no whitelist bypass)
        if var.question_type.value in ("text_open",):
            return False, REASON_CODES["open_ended"]

        # Rule 6: Must be exact match
        if exact_match_status == ExactMatchStatus.EXACT_MATCH:
            return True, REASON_CODES["exact_match"]

        # Whitelist catch-all for NOT_ASSESSED variables present in both
        if is_whitelisted and var.in_historical and var.in_latest_wave:
            return True, "Whitelisted: manual approval"

        # Default: not eligible
        return False, REASON_CODES.get(match_reason, "Unknown reason")

    @property
    def entries(self) -> list[ManifestEntry]:
        return self._entries

    def get_trendable(self) -> list[ManifestEntry]:
        return [e for e in self._entries if e.trend_eligible]

    def get_latest_wave_only(self) -> list[ManifestEntry]:
        return [
            e for e in self._entries
            if e.latest_wave_present and not e.historical_present
            and e.display_eligible
        ]

    def get_historical_only(self) -> list[ManifestEntry]:
        return [
            e for e in self._entries
            if e.historical_present and not e.latest_wave_present
            and e.display_eligible
        ]

    def get_excluded(self) -> list[ManifestEntry]:
        return [
            e for e in self._entries
            if e.exact_match_status == ExactMatchStatus.EXCLUDED
        ]

    def summary(self) -> dict:
        """Summary statistics of the harmonization manifest."""
        total = len(self._entries)
        return {
            "total_variables": total,
            "trend_eligible": len(self.get_trendable()),
            "latest_wave_only": len(self.get_latest_wave_only()),
            "historical_only": len(self.get_historical_only()),
            "excluded": len(self.get_excluded()),
            "display_eligible": len(
                [e for e in self._entries if e.display_eligible]
            ),
            "segment_eligible": len(
                [e for e in self._entries if e.segment_eligible]
            ),
        }

    def export_csv(self, output_path: str | Path):
        """Export the manifest to CSV for inspection and audit."""
        output_path = Path(output_path)
        if not self._entries:
            raise ValueError("Manifest is empty. Call build() first.")

        fieldnames = [
            "canonical_variable_id",
            "question_family",
            "canonical_question_text",
            "source_dataset",
            "source_wave",
            "source_variable_name",
            "response_options_hash",
            "question_type",
            "value_labels",
            "latest_wave_present",
            "historical_present",
            "exact_match_status",
            "trend_eligible",
            "reason_not_trendable",
            "analysis_population_id",
            "country_mode_default",
            "display_eligible",
            "segment_eligible",
            "notes",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self._entries:
                row = {}
                for fn in fieldnames:
                    val = getattr(entry, fn)
                    if isinstance(val, dict):
                        val = json.dumps(val, ensure_ascii=False)
                    elif isinstance(val, Enum):
                        val = val.value
                    row[fn] = val
                writer.writerow(row)

    def export_json(self, output_path: str | Path):
        """Export the manifest to JSON."""
        output_path = Path(output_path)
        data = []
        for entry in self._entries:
            d = asdict(entry)
            # Convert enums to strings
            d["exact_match_status"] = entry.exact_match_status.value
            data.append(d)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_pending_review(self) -> list[ManifestEntry]:
        """Variables present in both datasets but not yet trendable.
        These are the candidates for whitelist review."""
        return [
            e for e in self._entries
            if e.historical_present and e.latest_wave_present
            and not e.trend_eligible
            and e.exact_match_status != ExactMatchStatus.EXCLUDED
        ]

    def export_review_csv(
        self,
        output_path: str | Path,
        labeling_vars: dict,
        w33_datamap: dict,
    ):
        """
        Export a human-readable review file for variables that need
        manual trendability decisions.

        Shows side-by-side: historical value labels vs W33 value labels,
        question text, and the reason the variable was not auto-approved.
        """
        output_path = Path(output_path)
        pending = self.get_pending_review()

        fieldnames = [
            "variable",
            "question_family",
            "review_category",
            "reason_blocked",
            "is_whitelisted",
            "historical_question_text",
            "w33_question_text",
            "historical_value_count",
            "w33_value_count",
            "historical_values",
            "w33_values",
            "recommendation",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for entry in sorted(pending, key=lambda e: e.question_family):
                hist_defn = labeling_vars.get(entry.canonical_variable_id)
                w33_defn = w33_datamap.get(entry.canonical_variable_id)

                h_vals = hist_defn.value_labels if hist_defn else {}
                w_vals = w33_defn.value_labels if w33_defn else {}
                h_text = hist_defn.question_text if hist_defn else ""
                w_text = w33_defn.description if w33_defn else ""

                # Classify the review category
                is_oe = (
                    entry.canonical_variable_id.endswith("oe")
                    or entry.canonical_variable_id.endswith("_OE")
                    or len(h_vals) > 50
                    or len(w_vals) > 50
                )
                is_flag = "Flag" in entry.canonical_variable_id or "flag" in entry.canonical_variable_id
                is_one_side_undoc = (
                    (len(h_vals) == 0 and len(w_vals) > 0)
                    or (len(h_vals) > 0 and len(w_vals) == 0)
                    or (len(h_vals) == 0 and len(w_vals) == 0)
                )

                if is_oe:
                    review_cat = "OPEN_ENDED"
                    rec = "Not trendable (open-ended responses)"
                elif is_flag:
                    review_cat = "FLAG_DERIVED"
                    rec = "Likely not needed for dashboard display"
                elif is_one_side_undoc:
                    review_cat = "ONE_SIDE_UNDOCUMENTED"
                    rec = "Column exists in both datasets but value labels only on one side. Likely trendable if question unchanged."
                else:
                    review_cat = "CODED_RESPONSE_CHANGE"
                    rec = "Response options changed between waves. Review if collapsible."

                # Truncate open-ended values for readability
                h_display = json.dumps(h_vals, ensure_ascii=False) if len(h_vals) <= 30 else f"({len(h_vals)} values, open-ended)"
                w_display = json.dumps(w_vals, ensure_ascii=False) if len(w_vals) <= 30 else f"({len(w_vals)} values, open-ended)"

                writer.writerow({
                    "variable": entry.canonical_variable_id,
                    "question_family": entry.question_family,
                    "review_category": review_cat,
                    "reason_blocked": entry.reason_not_trendable,
                    "is_whitelisted": entry.canonical_variable_id in self.trend_whitelist,
                    "historical_question_text": h_text[:200],
                    "w33_question_text": w_text[:200],
                    "historical_value_count": len(h_vals),
                    "w33_value_count": len(w_vals),
                    "historical_values": h_display,
                    "w33_values": w_display,
                    "recommendation": rec,
                })
