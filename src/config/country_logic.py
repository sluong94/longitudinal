"""
Country Comparability Engine — handles balanced-country intersection
logic for longitudinal trend analysis.

The core problem: country coverage varies by wave and by question family.
A global trend can be misleading if it silently changes country composition.

Default rule: for longitudinal trends, use balanced-country intersection
(only countries present in ALL selected waves for a given question).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# Canonical country code mapping (from labeling workbook / W33 datamap)
COUNTRY_MAP = {
    1: "UK", 2: "USA", 3: "France", 4: "Italy", 5: "Germany",
    6: "Spain", 7: "Sweden", 8: "Denmark", 9: "Norway", 10: "Greece",
    11: "Hungary", 12: "Czech Republic", 13: "Poland", 14: "Russia",
    15: "South Korea", 16: "Thailand", 17: "UK (Welsh)", 18: "Ireland",
    19: "Australia", 20: "China", 21: "Japan", 22: "Austria",
    23: "India", 24: "Turkey", 25: "UAE", 26: "Argentina",
    27: "Brazil", 28: "Venezuela", 29: "Columbia", 30: "Switzerland",
    31: "Portugal", 32: "Canada", 33: "Mexico", 34: "Malaysia",
    35: "South Africa", 36: "Tunisia", 37: "Belgium", 38: "Netherlands",
    39: "Israel", 40: "Saudi Arabia", 41: "Finland", 42: "New Zealand",
    43: "Singapore", 44: "Chile", 45: "Taiwan", 46: "Hong Kong",
    47: "Indonesia", 48: "Kuwait", 49: "Qatar",
}


@dataclass
class CountryIntersectionResult:
    """Result of computing balanced-country intersection."""

    intersection_codes: set[int]
    intersection_names: list[str]
    per_wave_countries: dict[int, set[int]]  # wave_code -> country_codes
    waves_analyzed: list[int]
    dropped_countries: dict[int, str]  # code -> name, for countries excluded

    @property
    def count(self) -> int:
        return len(self.intersection_codes)

    def describe(self) -> str:
        names = sorted(self.intersection_names)
        return (
            f"Balanced intersection: {self.count} countries "
            f"({', '.join(names[:5])}{'...' if len(names) > 5 else ''})"
        )


class CountryComparabilityEngine:
    """
    Computes and manages country comparability for longitudinal analysis.

    Usage:
        engine = CountryComparabilityEngine()
        result = engine.compute_intersection(df, waves=[18, 19, 20])
        filtered = engine.apply_balanced_filter(df, result)
    """

    def __init__(self, country_map: Optional[dict[int, str]] = None):
        self.country_map = country_map or COUNTRY_MAP

    def compute_intersection(
        self,
        df: pd.DataFrame,
        waves: Optional[list[int]] = None,
        variable_name: Optional[str] = None,
    ) -> CountryIntersectionResult:
        """
        Compute the balanced-country intersection across selected waves.

        Parameters
        ----------
        df : DataFrame with 'hCountry' and 'Wave' columns
        waves : list of wave codes to analyze. If None, uses all waves.
        variable_name : optional. If provided, only considers rows where
            this variable has non-null data (for per-question intersection).
        """
        work = df.copy()

        if waves is not None:
            work = work[work["Wave"].isin(waves)]

        if variable_name and variable_name in work.columns:
            work = work[work[variable_name].notna()]

        wave_values = sorted(work["Wave"].dropna().unique().tolist())

        # Per-wave country sets
        per_wave: dict[int, set[int]] = {}
        for w in wave_values:
            wave_data = work[work["Wave"] == w]
            countries = set(wave_data["hCountry"].dropna().astype(int).unique())
            per_wave[int(w)] = countries

        # Intersection
        if per_wave:
            intersection = set.intersection(*per_wave.values())
        else:
            intersection = set()

        # Dropped countries
        all_countries = set()
        for s in per_wave.values():
            all_countries |= s
        dropped = all_countries - intersection
        dropped_map = {
            c: self.country_map.get(c, f"Unknown ({c})") for c in sorted(dropped)
        }

        return CountryIntersectionResult(
            intersection_codes=intersection,
            intersection_names=[
                self.country_map.get(c, f"Unknown ({c})") for c in sorted(intersection)
            ],
            per_wave_countries=per_wave,
            waves_analyzed=wave_values,
            dropped_countries=dropped_map,
        )

    def apply_balanced_filter(
        self,
        df: pd.DataFrame,
        result: CountryIntersectionResult,
    ) -> pd.DataFrame:
        """Filter a DataFrame to only include balanced-intersection countries."""
        return df[df["hCountry"].isin(result.intersection_codes)].copy()

    def compute_country_specific(
        self,
        df: pd.DataFrame,
        country_code: int,
        waves: Optional[list[int]] = None,
    ) -> pd.DataFrame:
        """
        Filter to a single country across available waves.

        For use when the user explicitly selects a country
        (e.g., "US-only across available US waves").
        """
        filtered = df[df["hCountry"] == country_code].copy()
        if waves is not None:
            filtered = filtered[filtered["Wave"].isin(waves)]
        return filtered

    def get_country_name(self, code: int) -> str:
        return self.country_map.get(code, f"Unknown ({code})")

    def get_country_code(self, name: str) -> Optional[int]:
        for code, n in self.country_map.items():
            if n.lower() == name.lower():
                return code
        return None

    def wave_country_matrix(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Build a wave × country presence matrix.

        Returns a DataFrame where rows are waves, columns are country names,
        and values are respondent counts.
        """
        if "Wave" not in df.columns or "hCountry" not in df.columns:
            raise ValueError("DataFrame must have 'Wave' and 'hCountry' columns")

        matrix = df.groupby(["Wave", "hCountry"]).size().unstack(fill_value=0)
        matrix.columns = [
            self.country_map.get(int(c), f"Country {c}") for c in matrix.columns
        ]
        return matrix
