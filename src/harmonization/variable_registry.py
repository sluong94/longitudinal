"""
Variable Registry — the canonical index of all known survey variables.

Each variable gets exactly one canonical entry. The registry tracks:
- Where it appears (historical, latest wave, or both)
- Its structural category (survey, demographic, derived, admin, etc.)
- Whether it is approved for display and/or segmentation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VariableCategory(str, Enum):
    """Structural classification of a variable."""
    DEMOGRAPHIC = "demographic"
    SURVEY_ITEM = "survey_item"
    DERIVED = "derived"
    HIDDEN = "hidden"
    ADMIN = "admin"
    QC = "qc"
    TIMING = "timing"
    GEO = "geo"
    EXCLUDE = "exclude"


class QuestionType(str, Enum):
    """Response structure type."""
    SINGLE_SELECT = "single_select"
    MULTI_SELECT = "multi_select"
    NUMERIC_OPEN = "numeric_open"
    TEXT_OPEN = "text_open"
    SCALE = "scale"
    BINARY = "binary"
    UNKNOWN = "unknown"


# Demographic / segment variables that are structurally important
KNOWN_DEMOGRAPHICS = {
    "A1": "age_bucket",
    "A2": "gender",
    "A3": "household_income",
    "A4": "personal_income",
    "A5": "hispanic_latino",
    "A6": "race_ethnicity",
    "A7": "education",
    "A8": "marital_status",
    "A9": "children",
    "A10": "employment_status",
    "Age_Numeric": "age_numeric",
    "hCountry": "country",
    "LangPref": "language_preference",
    "B1": "industry",
}

# Variables that should never be exposed in the dashboard
ALWAYS_EXCLUDE_PATTERNS = [
    "record", "uuid", "status", "vdecLang", "QSamp",
]

ALWAYS_EXCLUDE_PREFIXES = [
    "TimeSection", "QCFlag", "dmaData",
]


@dataclass
class CanonicalVariable:
    """A single variable in the canonical registry."""

    canonical_id: str  # primary key, typically same as variable_code
    variable_code: str
    display_name: str
    question_text: str
    category: VariableCategory
    question_type: QuestionType
    value_labels: dict[str, str]
    response_options_hash: str

    # Presence flags
    in_historical: bool = False
    in_latest_wave: bool = False
    historical_waves: list[str] = field(default_factory=list)

    # Approval flags
    display_eligible: bool = True
    segment_eligible: bool = False
    trend_eligible: bool = False  # set by harmonization manifest
    whitelist_override: bool = False  # manual override for hidden/derived vars

    notes: str = ""


class VariableRegistry:
    """
    Central registry of all canonical variables.

    Built by combining the labeling workbook (historical source of truth)
    with the W33 datamap (latest wave additions).
    """

    def __init__(self):
        self._variables: dict[str, CanonicalVariable] = {}

    def register(self, var: CanonicalVariable):
        self._variables[var.canonical_id] = var

    def get(self, canonical_id: str) -> Optional[CanonicalVariable]:
        return self._variables.get(canonical_id)

    def list_all(self) -> list[CanonicalVariable]:
        return list(self._variables.values())

    def list_by_category(self, category: VariableCategory) -> list[CanonicalVariable]:
        return [v for v in self._variables.values() if v.category == category]

    def list_display_eligible(self) -> list[CanonicalVariable]:
        return [v for v in self._variables.values() if v.display_eligible]

    def list_segment_eligible(self) -> list[CanonicalVariable]:
        return [v for v in self._variables.values() if v.segment_eligible]

    def list_trend_eligible(self) -> list[CanonicalVariable]:
        return [v for v in self._variables.values() if v.trend_eligible]

    def list_latest_wave_only(self) -> list[CanonicalVariable]:
        return [
            v for v in self._variables.values()
            if v.in_latest_wave and not v.in_historical
        ]

    def list_historical_only(self) -> list[CanonicalVariable]:
        return [
            v for v in self._variables.values()
            if v.in_historical and not v.in_latest_wave
        ]

    @property
    def size(self) -> int:
        return len(self._variables)

    def classify_variable(self, var_name: str) -> VariableCategory:
        """Determine the structural category of a variable by name conventions."""
        if var_name in ALWAYS_EXCLUDE_PATTERNS:
            return VariableCategory.ADMIN
        for prefix in ALWAYS_EXCLUDE_PREFIXES:
            if var_name.startswith(prefix):
                if prefix == "TimeSection":
                    return VariableCategory.TIMING
                if prefix == "QCFlag":
                    return VariableCategory.QC
                if prefix == "dmaData":
                    return VariableCategory.GEO
        if var_name in KNOWN_DEMOGRAPHICS:
            return VariableCategory.DEMOGRAPHIC
        if var_name.startswith("h") and len(var_name) > 1 and var_name[1].isupper():
            return VariableCategory.HIDDEN
        return VariableCategory.SURVEY_ITEM

    def infer_question_type(
        self, value_labels: dict[str, str], response_type_hint: str = ""
    ) -> QuestionType:
        """Best-effort inference of question type from value labels."""
        if response_type_hint == "open_numeric":
            return QuestionType.NUMERIC_OPEN
        if response_type_hint == "open_text":
            return QuestionType.TEXT_OPEN

        if not value_labels:
            return QuestionType.UNKNOWN

        labels = list(value_labels.values())
        codes = list(value_labels.keys())

        # Binary: exactly 2 options (e.g., Yes/No)
        if len(labels) == 2:
            lower_labels = {l.lower() for l in labels}
            if lower_labels & {"yes", "no"}:
                return QuestionType.BINARY

        # Scale: labels suggest a Likert-type scale
        lower_labels = [l.lower() for l in labels]
        if any("agree" in l or "disagree" in l for l in lower_labels):
            return QuestionType.SCALE
        if any("satisfied" in l or "dissatisfied" in l for l in lower_labels):
            return QuestionType.SCALE
        if len(labels) >= 5 and all(
            c.replace(".", "").replace("-", "").isdigit() for c in codes
        ):
            # Numeric codes with 5+ options — likely a scale
            return QuestionType.SCALE

        return QuestionType.SINGLE_SELECT

    def build_from_parsers(
        self,
        labeling_vars: dict,  # from LabelingWorkbookParser
        w33_datamap: dict,    # from W33Parser
        w33_columns: list[str],
        longitudinal_columns: list[str],
    ):
        """
        Populate the registry from parsed source data.

        Priority: labeling workbook is source of truth for historical variables.
        W33 datamap adds latest-wave variables not in the workbook.
        """
        historical_col_set = set(longitudinal_columns)
        w33_col_set = set(w33_columns)

        # 1. Register all labeling workbook variables
        for code, defn in labeling_vars.items():
            category = self.classify_variable(code)
            q_type = self.infer_question_type(defn.value_labels)

            is_segment = code in KNOWN_DEMOGRAPHICS
            is_display = category in (
                VariableCategory.DEMOGRAPHIC,
                VariableCategory.SURVEY_ITEM,
            )
            # Hidden/derived variables are not display-eligible by default
            if category in (
                VariableCategory.HIDDEN,
                VariableCategory.ADMIN,
                VariableCategory.QC,
                VariableCategory.TIMING,
                VariableCategory.GEO,
                VariableCategory.EXCLUDE,
            ):
                is_display = False

            self.register(CanonicalVariable(
                canonical_id=code,
                variable_code=code,
                display_name=defn.variable_name or code,
                question_text=defn.question_text,
                category=category,
                question_type=q_type,
                value_labels=defn.value_labels,
                response_options_hash=defn.response_options_hash,
                in_historical=code in historical_col_set,
                in_latest_wave=code in w33_col_set,
                display_eligible=is_display,
                segment_eligible=is_segment,
            ))

        # 2. Register W33-only variables not in the labeling workbook
        for name, defn in w33_datamap.items():
            if name in self._variables:
                continue  # already registered from labeling workbook

            category = self.classify_variable(name)
            q_type = self.infer_question_type(
                defn.value_labels, defn.response_type
            )
            is_display = category in (
                VariableCategory.DEMOGRAPHIC,
                VariableCategory.SURVEY_ITEM,
            )
            is_segment = name in KNOWN_DEMOGRAPHICS

            self.register(CanonicalVariable(
                canonical_id=name,
                variable_code=name,
                display_name=defn.description or name,
                question_text=defn.description,
                category=category,
                question_type=q_type,
                value_labels=defn.value_labels,
                response_options_hash=defn.response_options_hash,
                in_historical=name in historical_col_set,
                in_latest_wave=True,
                display_eligible=is_display,
                segment_eligible=is_segment,
            ))
