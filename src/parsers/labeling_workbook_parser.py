"""
Parser for the historical Labeling Workbook (W32 and earlier).

This is the primary source of truth for:
- Variable codes and human-readable names
- Value code → label mappings
- Question text / descriptions
- UDV (user-defined variable) type flags
- Wave coverage metadata

The labeling workbook follows a MarketSight convention with a Labels sheet
structured as: Variable Code | Variable Name | Value Code | Value Name | ...
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass
class VariableDefinition:
    """A single variable as defined in the labeling workbook."""

    variable_code: str
    variable_name: str
    description: str  # from Description/Question Text column
    value_labels: dict[str, str]  # {value_code: value_label}
    category: str
    missing_values: str
    udv_type: Optional[str]  # MRV, RG, FV, MV, GV, or None
    udv_definition: Optional[str]
    value_to_count_in_mrv: Optional[str]
    response_options_hash: str = ""  # computed after init

    def __post_init__(self):
        self.response_options_hash = self._compute_response_hash()

    def _compute_response_hash(self) -> str:
        """Deterministic hash of value labels for exact-match comparison."""
        if not self.value_labels:
            return ""
        canonical = json.dumps(
            sorted(self.value_labels.items()), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def is_derived(self) -> bool:
        return self.udv_type is not None

    @property
    def question_text(self) -> str:
        """Best available human-readable question text."""
        if self.description:
            return self.description
        return self.variable_name


class LabelingWorkbookParser:
    """Parses the historical labeling workbook into structured variable definitions."""

    EXPECTED_COLUMNS = [
        "Variable Code",
        "Variable Name",
        "Value Code",
        "Value Name",
        "Category",
        "Description/Question Text",
        "Missing Values",
        "UDV Type",
        "UDV Definition",
        "Value to Count in MRV",
    ]

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._variables: dict[str, VariableDefinition] = {}
        self._wave_map: dict[int, str] = {}  # {numeric_code: wave_label}

    def parse(self) -> dict[str, VariableDefinition]:
        """Parse the Labels sheet and return variable definitions keyed by code."""
        df = pd.read_excel(
            self.file_path, sheet_name="Labels", header=0, dtype=str
        )
        df = df.fillna("")

        current_var_code = None
        current_var_name = ""
        current_description = ""
        current_category = ""
        current_missing = ""
        current_udv_type = ""
        current_udv_def = ""
        current_mrv_val = ""
        current_values: dict[str, str] = {}

        for _, row in df.iterrows():
            var_code = str(row.get("Variable Code", "")).strip()
            var_name = str(row.get("Variable Name", "")).strip()
            val_code = str(row.get("Value Code", "")).strip()
            val_name = str(row.get("Value Name", "")).strip()
            category = str(row.get("Category", "")).strip()
            desc = str(row.get("Description/Question Text", "")).strip()
            missing = str(row.get("Missing Values", "")).strip()
            udv_type = str(row.get("UDV Type", "")).strip()
            udv_def = str(row.get("UDV Definition", "")).strip()
            mrv_val = str(row.get("Value to Count in MRV", "")).strip()

            # New variable block starts when Variable Code is non-empty
            if var_code:
                # Save previous variable
                if current_var_code:
                    self._save_variable(
                        current_var_code,
                        current_var_name,
                        current_description,
                        current_values,
                        current_category,
                        current_missing,
                        current_udv_type,
                        current_udv_def,
                        current_mrv_val,
                    )

                current_var_code = var_code
                current_var_name = var_name
                current_description = desc
                current_category = category
                current_missing = missing
                current_udv_type = udv_type if udv_type else ""
                current_udv_def = udv_def
                current_mrv_val = mrv_val
                current_values = {}

                # Capture value on the same row if present
                if val_code and val_name:
                    current_values[val_code] = val_name

            elif val_code and val_name and current_var_code:
                # Continuation row: additional value label
                current_values[val_code] = val_name

        # Save last variable
        if current_var_code:
            self._save_variable(
                current_var_code,
                current_var_name,
                current_description,
                current_values,
                current_category,
                current_missing,
                current_udv_type,
                current_udv_def,
                current_mrv_val,
            )

        # Extract wave map from the Wave variable
        if "Wave" in self._variables:
            self._wave_map = {
                int(float(k)): v
                for k, v in self._variables["Wave"].value_labels.items()
                if k.replace(".", "").replace("-", "").isdigit()
            }

        return self._variables

    def _save_variable(
        self,
        code: str,
        name: str,
        description: str,
        values: dict[str, str],
        category: str,
        missing: str,
        udv_type: str,
        udv_def: str,
        mrv_val: str,
    ):
        self._variables[code] = VariableDefinition(
            variable_code=code,
            variable_name=name,
            description=description,
            value_labels=dict(values),
            category=category,
            missing_values=missing,
            udv_type=udv_type or None,
            udv_definition=udv_def or None,
            value_to_count_in_mrv=mrv_val or None,
        )

    @property
    def variables(self) -> dict[str, VariableDefinition]:
        if not self._variables:
            self.parse()
        return self._variables

    @property
    def wave_map(self) -> dict[int, str]:
        """Mapping from numeric wave code to wave label (e.g. {1: 'W13'})."""
        if not self._wave_map:
            self.parse()
        return self._wave_map

    def get_variable(self, code: str) -> Optional[VariableDefinition]:
        return self.variables.get(code)

    def list_variable_codes(self) -> list[str]:
        return list(self.variables.keys())

    def list_derived_variables(self) -> list[str]:
        """Return variable codes flagged as UDV (derived)."""
        return [k for k, v in self.variables.items() if v.is_derived]

    def list_variables_with_question_text(self) -> list[str]:
        """Return variable codes that have a Description/Question Text."""
        return [k for k, v in self.variables.items() if v.description]
