"""
Parser for the historical longitudinal dataset sample.

This file is a flat respondent-level table with a Wave column,
covering W13–W32. The full production file is much larger;
this parser is designed to work with both the sample and full versions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


class LongitudinalParser:
    """
    Parses the historical longitudinal dataset.

    Usage:
        parser = LongitudinalParser("Longitudinal_Dataset_Sample.xlsx")
        columns = parser.get_column_names()
        df = parser.load_data()  # or load_data(waves=[18, 19]) for subset
    """

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._columns: list[str] = []
        self._data: Optional[pd.DataFrame] = None

    def get_column_names(self) -> list[str]:
        """Get column names without loading full data."""
        if self._columns:
            return self._columns
        df = pd.read_excel(self.file_path, nrows=0)
        self._columns = list(df.columns)
        return self._columns

    def load_data(
        self,
        waves: Optional[list[int]] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        """
        Load longitudinal data, optionally filtering by wave and/or columns.

        Parameters
        ----------
        waves : list of int, optional
            Numeric wave codes to include (e.g. [18, 19] for W31, W32).
        columns : list of str, optional
            Subset of columns to load. 'Wave' is always included.
        """
        usecols = None
        if columns:
            required = set(columns) | {"Wave"}
            available = set(self.get_column_names())
            usecols = sorted(required & available)

        df = pd.read_excel(self.file_path, usecols=usecols)

        if waves is not None and "Wave" in df.columns:
            df = df[df["Wave"].isin(waves)].copy()

        self._data = df
        self._columns = list(df.columns)
        return df

    def get_wave_values(self) -> list:
        """Return unique wave values present in the dataset."""
        df = pd.read_excel(self.file_path, usecols=["Wave"])
        return sorted(df["Wave"].dropna().unique().tolist())

    def get_country_values(self) -> list:
        """Return unique country codes present in the dataset."""
        df = pd.read_excel(self.file_path, usecols=["hCountry"])
        return sorted(df["hCountry"].dropna().unique().tolist())

    def get_column_coverage_by_wave(
        self, target_columns: Optional[list[str]] = None
    ) -> dict[int, list[str]]:
        """
        For each wave, identify which target columns have non-null data.

        This is useful for understanding which variables were actually
        fielded in which waves — column presence alone does not guarantee
        that data exists for every wave.
        """
        df = self.load_data() if self._data is None else self._data

        if target_columns is None:
            target_columns = [c for c in df.columns if c != "Wave"]

        coverage: dict[int, list[str]] = {}
        for wave_val, group in df.groupby("Wave"):
            present = []
            for col in target_columns:
                if col in group.columns and group[col].notna().any():
                    present.append(col)
            coverage[wave_val] = present

        return coverage

    def validate_employment_only(self) -> dict:
        """Check whether all respondents appear to be employed."""
        df = self.load_data() if self._data is None else self._data

        result = {
            "has_a10": "A10" in df.columns,
            "a10_values": [],
            "appears_employed_only": False,
            "evidence": [],
        }

        if result["has_a10"]:
            vals = sorted(df["A10"].dropna().unique().tolist())
            result["a10_values"] = vals
            employed_codes = {1, 2, 3}
            actual = set(int(v) for v in vals)
            if actual.issubset(employed_codes):
                result["appears_employed_only"] = True
                result["evidence"].append(
                    f"All A10 values ({actual}) are employed statuses"
                )

        return result
