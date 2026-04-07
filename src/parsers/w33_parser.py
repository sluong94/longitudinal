"""
Parser for the W33 (latest wave) raw data file.

Handles two sheets:
- A1: respondent-level raw data
- Datamap: variable definitions and value code mappings

The Datamap uses a convention:
  [variable_name]: Description text
  Values: range
    code  label
    code  label
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import openpyxl
import pandas as pd


# Fields that are administrative / operational and should never appear in analysis
ADMIN_FIELDS = frozenset({"record", "uuid", "status", "vdecLang", "QSamp"})

# Prefix patterns for timing and QC fields
TIMING_PATTERN = re.compile(r"^TimeSection")
QC_PATTERN = re.compile(r"^QCFlag")

# US-specific geographic fields (kept for reference but excluded from core survey)
US_GEO_FIELDS = frozenset({
    "Region_US", "Division_US", "Urbanicity_US", "State_US", "MSA", "County_Name",
})

# DMA / zip-code derived fields
DMA_PATTERN = re.compile(r"^dmaData")


@dataclass
class W33VariableDefinition:
    """A variable as parsed from the W33 Datamap sheet."""

    name: str
    description: str
    value_labels: dict[str, str]  # {code: label}
    response_type: str  # 'coded', 'open_numeric', 'open_text', 'unknown'
    response_options_hash: str = ""

    def __post_init__(self):
        self.response_options_hash = self._compute_response_hash()

    def _compute_response_hash(self) -> str:
        if not self.value_labels:
            return ""
        canonical = json.dumps(
            sorted(self.value_labels.items()), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def field_category(self) -> str:
        """Classify this variable into a structural category."""
        if self.name in ADMIN_FIELDS:
            return "admin"
        if TIMING_PATTERN.match(self.name):
            return "timing"
        if QC_PATTERN.match(self.name):
            return "qc"
        if self.name in US_GEO_FIELDS or DMA_PATTERN.match(self.name):
            return "geo_derived"
        if self.name.startswith("h") and len(self.name) > 1 and self.name[1].isupper():
            return "hidden_derived"
        return "survey"


class W33Parser:
    """
    Parses W33 raw data file.

    Usage:
        parser = W33Parser("Sample data file W33.xlsx")
        parser.parse_datamap()
        parser.parse_raw_data()  # optional for sample inspection
    """

    WAVE_ID = "W33"
    WAVE_CODE_NUMERIC = 20  # next after W32=19

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._datamap: dict[str, W33VariableDefinition] = {}
        self._raw_data: Optional[pd.DataFrame] = None
        self._columns: list[str] = []

    def parse_datamap(self) -> dict[str, W33VariableDefinition]:
        """Parse the Datamap sheet into structured variable definitions."""
        wb = openpyxl.load_workbook(self.file_path, read_only=True)
        ws = wb["Datamap"]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        current_var: Optional[dict] = None
        var_pattern = re.compile(r"^\[(.+?)\](?::?\s*(.*))?$")

        for row in rows:
            cell_a = str(row[0]).strip() if row[0] else ""
            cell_b = row[1]
            cell_c = row[2]

            match = var_pattern.match(cell_a)
            if match:
                # Save previous variable
                if current_var:
                    self._save_datamap_variable(current_var)

                var_name = match.group(1).strip()
                var_desc = (match.group(2) or "").strip()
                current_var = {
                    "name": var_name,
                    "description": var_desc,
                    "values": {},
                    "response_type": "unknown",
                }
            elif current_var is not None:
                if cell_b is not None and cell_c is not None:
                    current_var["values"][str(cell_b).strip()] = str(cell_c).strip()
                elif cell_a:
                    lower = cell_a.lower()
                    if "open numeric" in lower:
                        current_var["response_type"] = "open_numeric"
                    elif "open text" in lower:
                        current_var["response_type"] = "open_text"
                    elif lower.startswith("values:"):
                        current_var["response_type"] = "coded"

        if current_var:
            self._save_datamap_variable(current_var)

        return self._datamap

    def _save_datamap_variable(self, var_dict: dict):
        defn = W33VariableDefinition(
            name=var_dict["name"],
            description=var_dict["description"],
            value_labels=var_dict["values"],
            response_type=var_dict["response_type"],
        )
        self._datamap[defn.name] = defn

    def parse_raw_data(self) -> pd.DataFrame:
        """Load the A1 sheet (raw respondent data). Use sparingly on large files."""
        self._raw_data = pd.read_excel(self.file_path, sheet_name="A1")
        self._columns = list(self._raw_data.columns)
        return self._raw_data

    def get_column_names(self) -> list[str]:
        """Get column names without loading all data (reads header only)."""
        if self._columns:
            return self._columns
        df = pd.read_excel(self.file_path, sheet_name="A1", nrows=0)
        self._columns = list(df.columns)
        return self._columns

    @property
    def datamap(self) -> dict[str, W33VariableDefinition]:
        if not self._datamap:
            self.parse_datamap()
        return self._datamap

    def get_survey_variables(self) -> list[str]:
        """Return variable names classified as survey (not admin/timing/QC/geo)."""
        return [
            name for name, defn in self.datamap.items()
            if defn.field_category == "survey"
        ]

    def get_hidden_derived_variables(self) -> list[str]:
        return [
            name for name, defn in self.datamap.items()
            if defn.field_category == "hidden_derived"
        ]

    def get_excluded_variables(self) -> list[str]:
        """Return variables that should be excluded from dashboard display."""
        return [
            name for name, defn in self.datamap.items()
            if defn.field_category in ("admin", "timing", "qc", "geo_derived")
        ]

    def validate_employment_only(self, df: Optional[pd.DataFrame] = None) -> dict:
        """
        Check whether the dataset appears to be employed-only.

        Returns a diagnostic dict rather than a boolean, so the caller
        can inspect evidence rather than trusting a blind assumption.
        """
        if df is None:
            if self._raw_data is None:
                df = self.parse_raw_data()
            else:
                df = self._raw_data

        result = {
            "has_a10": "A10" in df.columns,
            "has_employment_quota": "hA10EmploymentQuota" in df.columns,
            "a10_values": sorted(df["A10"].dropna().unique().tolist()) if "A10" in df.columns else [],
            "employment_quota_values": (
                sorted(df["hA10EmploymentQuota"].dropna().unique().tolist())
                if "hA10EmploymentQuota" in df.columns else []
            ),
            "appears_employed_only": False,
            "evidence": [],
        }

        # Check if all respondents are employed (A10 in {1, 2, 3})
        employed_codes = {1, 2, 3}
        if result["has_a10"]:
            a10_vals = set(df["A10"].dropna().astype(int))
            if a10_vals.issubset(employed_codes):
                result["appears_employed_only"] = True
                result["evidence"].append(
                    f"All A10 values ({a10_vals}) are employed statuses"
                )
            else:
                non_employed = a10_vals - employed_codes
                result["evidence"].append(
                    f"A10 contains non-employed values: {non_employed}"
                )

        if result["has_employment_quota"]:
            result["evidence"].append(
                f"hA10EmploymentQuota present with values: {result['employment_quota_values']}"
            )

        return result
