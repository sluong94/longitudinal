"""
Analysis Population Registry — defines the controlled set of
reporting populations for longitudinal analysis.

Design principle: keep this minimal. One primary population for
W33-linked trend analysis, with at most one legacy fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class AnalysisPopulation:
    """Definition of a controlled analysis population."""

    population_id: str
    description: str
    age_min: Optional[int]
    age_max: Optional[int]
    employment_rule: str  # 'employed_only', 'all', 'custom'
    employment_codes: list[int]  # A10 values to include
    country_rule: str  # 'balanced_intersection', 'all', 'specific'
    country_codes: Optional[list[int]]  # None = determined at runtime
    wave_rule: str  # 'all_available', 'w33_compatible', 'custom'
    wave_codes: Optional[list[int]]  # None = all
    is_default: bool = False
    notes: str = ""

    def apply_filters(
        self,
        df: pd.DataFrame,
        country_intersection: Optional[set[int]] = None,
    ) -> pd.DataFrame:
        """
        Apply this population's filters to a DataFrame.

        Parameters
        ----------
        df : DataFrame with columns like Age_Numeric, A10, hCountry, Wave
        country_intersection : set of country codes for balanced comparison
            If provided and country_rule is 'balanced_intersection',
            this overrides country_codes.
        """
        filtered = df.copy()

        # Age filter
        if self.age_min is not None and "Age_Numeric" in filtered.columns:
            filtered = filtered[filtered["Age_Numeric"] >= self.age_min]
        if self.age_max is not None and "Age_Numeric" in filtered.columns:
            filtered = filtered[filtered["Age_Numeric"] <= self.age_max]

        # Employment filter
        if self.employment_rule == "employed_only" and "A10" in filtered.columns:
            filtered = filtered[filtered["A10"].isin(self.employment_codes)]

        # Country filter
        if self.country_rule == "balanced_intersection" and "hCountry" in filtered.columns:
            if country_intersection is not None:
                filtered = filtered[filtered["hCountry"].isin(country_intersection)]
        elif self.country_rule == "specific" and self.country_codes and "hCountry" in filtered.columns:
            filtered = filtered[filtered["hCountry"].isin(self.country_codes)]

        # Wave filter
        if self.wave_codes is not None and "Wave" in filtered.columns:
            filtered = filtered[filtered["Wave"].isin(self.wave_codes)]

        return filtered


class AnalysisPopulationRegistry:
    """
    Registry of all defined analysis populations.

    For v1, this should contain exactly:
    1. trend_default_employed_18_65 (primary, default)
    2. optionally one legacy fallback if needed
    """

    def __init__(self):
        self._populations: dict[str, AnalysisPopulation] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register the v1 default populations."""

        # Primary: employed 18-65, balanced country intersection
        self.register(AnalysisPopulation(
            population_id="trend_default_employed_18_65",
            description=(
                "Primary longitudinal trend population: employed respondents "
                "aged 18-65, balanced-country intersection across selected waves. "
                "This is the default for all W33-linked trend analysis."
            ),
            age_min=18,
            age_max=65,
            employment_rule="employed_only",
            employment_codes=[1, 2, 3],  # FT, PT, self-employed
            country_rule="balanced_intersection",
            country_codes=None,  # determined at runtime
            wave_rule="all_available",
            wave_codes=None,
            is_default=True,
            notes="Designed to preserve comparability with W33 employed-only sample",
        ))

        # Latest wave exploratory: no restrictions beyond what's in the data
        self.register(AnalysisPopulation(
            population_id="latest_wave_all_respondents",
            description=(
                "All respondents in the latest wave. No demographic or "
                "employment filters applied. Used for latest-wave exploratory mode."
            ),
            age_min=None,
            age_max=None,
            employment_rule="all",
            employment_codes=[],
            country_rule="all",
            country_codes=None,
            wave_rule="custom",
            wave_codes=None,  # set to latest wave at runtime
            is_default=False,
            notes="Broadest possible base for latest-wave exploration",
        ))

    def register(self, population: AnalysisPopulation):
        self._populations[population.population_id] = population

    def get(self, population_id: str) -> Optional[AnalysisPopulation]:
        return self._populations.get(population_id)

    def get_default(self) -> AnalysisPopulation:
        for pop in self._populations.values():
            if pop.is_default:
                return pop
        raise ValueError("No default population defined")

    def list_all(self) -> list[AnalysisPopulation]:
        return list(self._populations.values())

    def list_ids(self) -> list[str]:
        return list(self._populations.keys())
