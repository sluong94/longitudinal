# Longitudinal Survey Dashboard — Architecture & Harmonization Design

## Overview

This system supports a dual-mode survey dashboard:

1. **Latest Wave Exploratory Mode** — broad analysis of the newest wave (W33), rich cuts, no requirement for historical comparability
2. **Longitudinal Trend Mode** — strict apples-to-apples wave-over-wave analysis using only exact-match trendable variables

The architecture follows the principle: **harmonization before visualization**.

## System Flow

```
Raw Excel Files (immutable)
    │
    ├── Labeling Databook W32.xlsx   (historical source of truth)
    ├── Sample data file W33.xlsx    (latest wave + datamap)
    └── Longitudinal_Dataset_Sample.xlsx  (historical respondent data)
    │
    ▼
Parsers (src/parsers/)
    │
    ├── LabelingWorkbookParser  → variable definitions, value labels, wave map
    ├── W33Parser               → W33 datamap + raw column detection
    └── LongitudinalParser      → historical columns + wave structure
    │
    ▼
Variable Registry (src/harmonization/variable_registry.py)
    │
    ├── Merges labeling workbook + W33 datamap
    ├── Classifies variables (survey, demographic, hidden, admin, QC, timing, geo)
    ├── Flags display-eligible and segment-eligible variables
    └── Detects presence in historical vs. latest wave
    │
    ▼
Harmonization Manifest (src/harmonization/manifest.py)
    │
    ├── Compares response options via deterministic hash
    ├── Determines exact-match status per variable
    ├── Applies strict trendability rules
    └── Produces auditable CSV/JSON manifest
    │
    ▼
Config Layer (src/config/)
    │
    ├── AnalysisPopulationRegistry  → controlled reporting bases
    ├── SegmentRegistry             → approved cross-tab cuts
    └── CountryComparabilityEngine  → balanced-country intersection
    │
    ▼
Dashboard (future)
    │
    ├── Latest Wave Mode  → all display-eligible W33 variables
    └── Trend Mode        → only trend-eligible variables, default population
```

## Directory Structure

```
longitudinal/
├── src/
│   ├── parsers/
│   │   ├── labeling_workbook_parser.py   # Historical labeling workbook (W32)
│   │   ├── w33_parser.py                 # Latest wave raw data + datamap
│   │   └── longitudinal_parser.py        # Historical longitudinal dataset
│   ├── harmonization/
│   │   ├── variable_registry.py          # Canonical variable index
│   │   ├── manifest.py                   # Harmonization manifest builder
│   │   └── trend_eligibility.py          # Strict trend eligibility rules
│   └── config/
│       ├── analysis_populations.py       # Controlled reporting populations
│       ├── segment_registry.py           # Approved dashboard segments/cuts
│       └── country_logic.py              # Balanced-country intersection
├── scripts/
│   └── generate_harmonization_manifest.py  # Main entry point
├── output/                                 # Generated manifest files
│   ├── harmonization_manifest.csv
│   ├── harmonization_manifest.json
│   ├── manifest_summary.json
│   └── trend_eligibility_audit.json
├── requirements.txt
└── ARCHITECTURE.md                         # This file
```

## Key Design Decisions

### 1. Trendability is strict by default

A variable is trend-eligible **only** if:
- Present in **both** historical and latest wave datasets
- Response options hash matches exactly
- Not in an excluded category (admin, QC, timing, geo)
- Not hidden/derived (unless explicitly whitelisted)
- Not open-ended text

This prevents false harmonization. Variables that look similar but differ in wording or response options are **not trendable** until manually approved.

### 2. One primary analysis population

The default longitudinal trend population is `trend_default_employed_18_65`:
- **Age**: 18–65
- **Employment**: employed only (A10 in {1, 2, 3})
- **Country**: balanced-country intersection across selected waves
- **Rationale**: W33 appears to be employed-only, so the historical base must match

A second population (`latest_wave_all_respondents`) exists for latest-wave exploratory mode with no filters.

### 3. Country comparability via balanced intersection

For longitudinal trends, the system defaults to balanced-country intersection — only countries present in **all** selected waves are included. This prevents country composition drift from distorting trend lines.

The engine also supports:
- Country-specific filtering (e.g., US-only)
- Per-question country intersection (since some questions are fielded in different country sets)

### 4. W33 is partially overlapping

Out of 564 W33 columns and 1604 historical columns:
- **89 columns** share exact names (candidate trendable set)
- **475 columns** are W33-only (new AI content, new instruments)
- **1515 columns** are historical-only

Of the 89 overlapping columns, **19 pass strict trendability** rules after response option hash comparison. The remaining 70 fail due to value label differences, hidden/derived status, or exclusion category.

### 5. Variable classification

Variables are classified into categories:
| Category | Rule | Display | Trend |
|---|---|---|---|
| `demographic` | Known demographic fields (A1-A10, hCountry, etc.) | Yes | If exact match |
| `survey_item` | Core survey questions | Yes | If exact match |
| `hidden` | h-prefix + uppercase (e.g., hWork1) | No (unless whitelisted) | No |
| `admin` | record, uuid, status, etc. | No | No |
| `qc` | QCFlag prefix | No | No |
| `timing` | TimeSection prefix | No | No |
| `geo` | dmaData prefix, US geo fields | No | No |

## Risk Mitigations

| Risk | Mitigation |
|---|---|
| **False harmonization** | Strict response-options hash comparison; no fuzzy matching |
| **Denominator drift** | Default population with explicit age/employment/country rules |
| **Country composition drift** | Balanced-country intersection computed per question |
| **Hidden field leakage** | Automatic classification by naming convention; hidden excluded by default |
| **Overpromising trends** | Only 19/89 overlapping variables pass strict rules; UI should separate modes |
| **W33 partial overlap** | Dual presence tracking; latest-wave-only variables clearly tagged |
| **Performance** | Column-name-only overlap detection; full data loaded only when needed |

## Running the Manifest Generator

```bash
pip install -r requirements.txt
python scripts/generate_harmonization_manifest.py
```

Outputs are written to `output/`.

## v2 Improvements (Deferred)

- Manual review workflow for `name_match_values_differ` variables
- Per-wave column coverage analysis (which variables are non-null per wave)
- Whitelist mechanism for approved hidden/derived variables
- Dashboard UI scaffolding (Streamlit or similar)
- Caching layer for large production datasets
- Weighted analysis support
- Wave-specific question text comparison (not just response options)
