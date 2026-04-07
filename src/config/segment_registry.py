"""
Segment Registry — defines which variables are approved for use
as cross-tabulation cuts / filters in the dashboard.

Segments are a subset of the variable registry: only variables
that are methodologically appropriate for cutting data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SegmentDefinition:
    """A variable approved for use as a dashboard segment/cut."""

    segment_id: str
    variable_code: str
    display_name: str
    value_labels: dict[str, str]
    available_in_trend_mode: bool  # safe for longitudinal cuts
    available_in_latest_mode: bool  # safe for latest-wave cuts
    notes: str = ""


class SegmentRegistry:
    """
    Registry of approved segment/cut variables.

    Only variables explicitly registered here can be used
    as cross-tabulation dimensions in the dashboard.
    """

    def __init__(self):
        self._segments: dict[str, SegmentDefinition] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register the core demographic segments available in v1."""

        defaults = [
            SegmentDefinition(
                segment_id="country",
                variable_code="hCountry",
                display_name="Country",
                value_labels={},  # populated from data
                available_in_trend_mode=True,
                available_in_latest_mode=True,
                notes="In trend mode, uses balanced-country intersection by default",
            ),
            SegmentDefinition(
                segment_id="gender",
                variable_code="A2",
                display_name="Gender",
                value_labels={"1": "Male", "2": "Female", "3": "Non-binary", "4": "Prefer not to answer"},
                available_in_trend_mode=True,
                available_in_latest_mode=True,
            ),
            SegmentDefinition(
                segment_id="age_bucket",
                variable_code="A1",
                display_name="Age Group",
                value_labels={},  # populated from labeling workbook
                available_in_trend_mode=True,
                available_in_latest_mode=True,
            ),
            SegmentDefinition(
                segment_id="age_grouped",
                variable_code="A1_GroupedNew",
                display_name="Age Group (Grouped)",
                value_labels={},
                available_in_trend_mode=True,
                available_in_latest_mode=True,
            ),
            SegmentDefinition(
                segment_id="employment_status",
                variable_code="A10",
                display_name="Employment Status",
                value_labels={
                    "1": "Employed full-time",
                    "2": "Employed part-time",
                    "3": "Self-employed",
                    "4": "Not employed (excluding retired)",
                    "5": "Retired",
                },
                available_in_trend_mode=True,
                available_in_latest_mode=True,
                notes="In trend mode with default population, most respondents are employed",
            ),
            SegmentDefinition(
                segment_id="industry",
                variable_code="B1",
                display_name="Industry",
                value_labels={},  # populated from labeling workbook
                available_in_trend_mode=True,
                available_in_latest_mode=True,
            ),
        ]

        for seg in defaults:
            self.register(seg)

    def register(self, segment: SegmentDefinition):
        self._segments[segment.segment_id] = segment

    def get(self, segment_id: str) -> Optional[SegmentDefinition]:
        return self._segments.get(segment_id)

    def list_all(self) -> list[SegmentDefinition]:
        return list(self._segments.values())

    def list_for_trend_mode(self) -> list[SegmentDefinition]:
        return [s for s in self._segments.values() if s.available_in_trend_mode]

    def list_for_latest_mode(self) -> list[SegmentDefinition]:
        return [s for s in self._segments.values() if s.available_in_latest_mode]

    def list_ids(self) -> list[str]:
        return list(self._segments.keys())
