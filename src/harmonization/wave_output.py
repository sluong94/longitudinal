"""
Wave-specific output — allows users to view results filtered by wave.

Supports:
- Listing variables available per wave
- Showing which waves a trendable variable spans
- Generating per-wave summary tables
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from .manifest import ManifestEntry


# Wave code → label mapping (from labeling workbook, plus W33)
WAVE_LABELS = {
    1: "W13", 2: "W14", 3: "W15", 4: "W16", 5: "W17",
    6: "W18", 7: "W19", 8: "W20", 9: "W21", 10: "W22",
    11: "W23", 12: "W24", 13: "W25", 14: "W26", 15: "W28",
    16: "W29", 17: "W30", 18: "W31", 19: "W32", 20: "W33",
}

# Inverse: label → code
WAVE_CODES = {v: k for k, v in WAVE_LABELS.items()}

LATEST_WAVE_CODE = 20
LATEST_WAVE_LABEL = "W33"


@dataclass
class WaveVariableSummary:
    """Summary of a variable's availability across waves."""

    variable_id: str
    question_text: str
    trend_eligible: bool
    waves_present: list[str]  # e.g. ["W31", "W32", "W33"]
    wave_count: int
    source: str  # 'both', 'historical', 'latest_wave'


class WaveOutputEngine:
    """
    Generates wave-specific views of the harmonization manifest and data.
    """

    def __init__(
        self,
        manifest_entries: list[ManifestEntry],
        wave_labels: Optional[dict[int, str]] = None,
    ):
        self.entries = manifest_entries
        self.wave_labels = wave_labels or WAVE_LABELS

    def get_variables_for_wave(self, wave_label: str) -> list[ManifestEntry]:
        """
        Return manifest entries relevant to a specific wave.

        For the latest wave: returns all latest_wave_present entries.
        For historical waves: returns all historical_present entries.
        """
        if wave_label == LATEST_WAVE_LABEL:
            return [e for e in self.entries if e.latest_wave_present and e.display_eligible]
        else:
            return [e for e in self.entries if e.historical_present and e.display_eligible]

    def get_trendable_for_wave(self, wave_label: str) -> list[ManifestEntry]:
        """Return trend-eligible entries that include this wave."""
        if wave_label == LATEST_WAVE_LABEL:
            return [e for e in self.entries if e.trend_eligible and e.latest_wave_present]
        else:
            return [e for e in self.entries if e.trend_eligible and e.historical_present]

    def wave_variable_matrix(self) -> dict[str, dict[str, bool]]:
        """
        Build a variable × wave presence matrix.

        Returns: {variable_id: {wave_label: present_bool}}
        Only includes display-eligible, trend-eligible variables.
        """
        trendable = [e for e in self.entries if e.trend_eligible]
        matrix = {}
        for entry in trendable:
            row = {}
            for code, label in sorted(self.wave_labels.items()):
                if label == LATEST_WAVE_LABEL:
                    row[label] = entry.latest_wave_present
                else:
                    # For historical waves, we know the variable is in the
                    # historical dataset but can't determine per-wave presence
                    # without the full data. Mark as "historical_present".
                    row[label] = entry.historical_present
            matrix[entry.canonical_variable_id] = row
        return matrix

    def per_wave_summary(self) -> list[dict]:
        """
        Generate a summary for each wave showing variable counts.
        """
        summaries = []
        for code in sorted(self.wave_labels.keys()):
            label = self.wave_labels[code]
            is_latest = label == LATEST_WAVE_LABEL

            if is_latest:
                all_vars = [e for e in self.entries if e.latest_wave_present and e.display_eligible]
                trend_vars = [e for e in self.entries if e.trend_eligible and e.latest_wave_present]
            else:
                all_vars = [e for e in self.entries if e.historical_present and e.display_eligible]
                trend_vars = [e for e in self.entries if e.trend_eligible and e.historical_present]

            summaries.append({
                "wave_code": code,
                "wave_label": label,
                "is_latest": is_latest,
                "total_display_variables": len(all_vars),
                "trend_eligible_variables": len(trend_vars),
                "latest_wave_only_count": len([
                    e for e in all_vars if e.latest_wave_present and not e.historical_present
                ]) if is_latest else 0,
            })

        return summaries

    def export_wave_summary_csv(self, output_path: str | Path):
        """Export per-wave summary as CSV."""
        output_path = Path(output_path)
        summaries = self.per_wave_summary()

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=summaries[0].keys())
            writer.writeheader()
            writer.writerows(summaries)

    def export_wave_variable_list(
        self,
        wave_label: str,
        output_path: str | Path,
        trend_only: bool = False,
    ):
        """Export the variable list for a specific wave as CSV."""
        output_path = Path(output_path)

        if trend_only:
            entries = self.get_trendable_for_wave(wave_label)
        else:
            entries = self.get_variables_for_wave(wave_label)

        fieldnames = [
            "variable_id", "question_family", "question_text",
            "question_type", "trend_eligible", "source_dataset",
            "value_labels",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for e in sorted(entries, key=lambda x: x.question_family):
                writer.writerow({
                    "variable_id": e.canonical_variable_id,
                    "question_family": e.question_family,
                    "question_text": e.canonical_question_text[:200],
                    "question_type": e.question_type,
                    "trend_eligible": e.trend_eligible,
                    "source_dataset": e.source_dataset,
                    "value_labels": json.dumps(e.value_labels, ensure_ascii=False),
                })


def compute_wave_coverage(
    df: pd.DataFrame,
    target_variables: list[str],
    wave_labels: Optional[dict[int, str]] = None,
) -> pd.DataFrame:
    """
    Compute per-wave, per-variable non-null coverage from actual data.

    Returns a DataFrame: rows = variables, columns = wave labels,
    values = count of non-null responses.

    This gives ground truth on which variables are actually fielded
    per wave (not just present in the schema).
    """
    if wave_labels is None:
        wave_labels = WAVE_LABELS

    if "Wave" not in df.columns:
        raise ValueError("DataFrame must have a 'Wave' column")

    available = [v for v in target_variables if v in df.columns]
    results = {}

    for wave_code, group in df.groupby("Wave"):
        label = wave_labels.get(int(wave_code), f"W{wave_code}")
        counts = {}
        for var in available:
            counts[var] = int(group[var].notna().sum())
        results[label] = counts

    coverage = pd.DataFrame(results).fillna(0).astype(int)
    return coverage
