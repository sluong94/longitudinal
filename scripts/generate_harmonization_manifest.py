#!/usr/bin/env python3
"""
Generate the harmonization manifest from source files.

This is the primary entry point for building the harmonization layer.
It reads all three source files, builds the variable registry,
and produces the harmonization manifest as both CSV and JSON.

Usage:
    python scripts/generate_harmonization_manifest.py

Inputs (expected in repo root):
    - Labeling Databook W32.xlsx
    - Sample data file W33.xlsx
    - Longitudinal_Dataset_Sample.xlsx

Outputs (written to output/):
    - harmonization_manifest.csv
    - harmonization_manifest.json
    - manifest_summary.json
    - trend_eligibility_audit.json
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.parsers import W33Parser, LongitudinalParser, LabelingWorkbookParser
from src.harmonization import HarmonizationManifest, VariableRegistry, TrendEligibility
from src.config import AnalysisPopulationRegistry, SegmentRegistry, CountryComparabilityEngine


def main():
    data_dir = project_root
    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("HARMONIZATION MANIFEST GENERATOR")
    print("=" * 60)

    # ── Step 1: Parse source files ──────────────────────────────
    print("\n[1/6] Parsing labeling workbook...")
    labeling_parser = LabelingWorkbookParser(
        data_dir / "Labeling Databook W32.xlsx"
    )
    labeling_vars = labeling_parser.parse()
    print(f"  → {len(labeling_vars)} variables parsed")
    print(f"  → Waves: {labeling_parser.wave_map}")
    print(f"  → Derived (UDV) variables: {len(labeling_parser.list_derived_variables())}")

    print("\n[2/6] Parsing W33 datamap...")
    w33_parser = W33Parser(data_dir / "Sample data file W33.xlsx")
    w33_datamap = w33_parser.parse_datamap()
    w33_columns = w33_parser.get_column_names()
    print(f"  → {len(w33_datamap)} variables in datamap")
    print(f"  → {len(w33_columns)} columns in raw data")
    print(f"  → Survey variables: {len(w33_parser.get_survey_variables())}")
    print(f"  → Hidden/derived: {len(w33_parser.get_hidden_derived_variables())}")
    print(f"  → Excluded (admin/timing/QC/geo): {len(w33_parser.get_excluded_variables())}")

    print("\n[3/6] Parsing longitudinal dataset...")
    long_parser = LongitudinalParser(
        data_dir / "Longitudinal_Dataset_Sample.xlsx"
    )
    long_columns = long_parser.get_column_names()
    print(f"  → {len(long_columns)} columns")

    # Overlap analysis
    overlap = set(w33_columns) & set(long_columns)
    w33_only = set(w33_columns) - set(long_columns)
    hist_only = set(long_columns) - set(w33_columns)
    print(f"\n  Column overlap analysis:")
    print(f"    Overlap (candidate trendable): {len(overlap)}")
    print(f"    W33-only: {len(w33_only)}")
    print(f"    Historical-only: {len(hist_only)}")

    # ── Step 2: Build variable registry ─────────────────────────
    print("\n[4/6] Building variable registry...")
    registry = VariableRegistry()
    registry.build_from_parsers(
        labeling_vars=labeling_vars,
        w33_datamap=w33_datamap,
        w33_columns=w33_columns,
        longitudinal_columns=long_columns,
    )
    print(f"  → {registry.size} canonical variables registered")
    print(f"  → Display-eligible: {len(registry.list_display_eligible())}")
    print(f"  → Segment-eligible: {len(registry.list_segment_eligible())}")
    print(f"  → Latest-wave-only: {len(registry.list_latest_wave_only())}")
    print(f"  → Historical-only: {len(registry.list_historical_only())}")

    # ── Step 3: Build harmonization manifest ────────────────────
    print("\n[5/6] Building harmonization manifest...")
    manifest = HarmonizationManifest(registry)
    entries = manifest.build(
        labeling_vars=labeling_vars,
        w33_datamap=w33_datamap,
        default_population_id="trend_default_employed_18_65",
    )

    summary = manifest.summary()
    print(f"  → Total entries: {summary['total_variables']}")
    print(f"  → Trend-eligible: {summary['trend_eligible']}")
    print(f"  → Latest-wave-only (display): {summary['latest_wave_only']}")
    print(f"  → Historical-only (display): {summary['historical_only']}")
    print(f"  → Excluded: {summary['excluded']}")

    # ── Step 4: Run trend eligibility audit ─────────────────────
    print("\n[6/6] Running trend eligibility audit...")
    te = TrendEligibility()
    audit = te.audit_report(entries)
    print(f"  → Trend-eligible (strict rules): {audit['trend_eligible']}")
    print(f"  → Rule failure distribution:")
    for rule, count in sorted(audit["first_failure_distribution"].items()):
        print(f"      {rule}: {count}")

    # ── Step 5: Export ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("EXPORTING")
    print("=" * 60)

    manifest.export_csv(output_dir / "harmonization_manifest.csv")
    print(f"  → {output_dir / 'harmonization_manifest.csv'}")

    manifest.export_json(output_dir / "harmonization_manifest.json")
    print(f"  → {output_dir / 'harmonization_manifest.json'}")

    with open(output_dir / "manifest_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  → {output_dir / 'manifest_summary.json'}")

    with open(output_dir / "trend_eligibility_audit.json", "w") as f:
        json.dump(audit, f, indent=2)
    print(f"  → {output_dir / 'trend_eligibility_audit.json'}")

    # ── Step 6: Show trendable variables ────────────────────────
    trendable = manifest.get_trendable()
    print(f"\n{'=' * 60}")
    print(f"TREND-ELIGIBLE VARIABLES ({len(trendable)})")
    print(f"{'=' * 60}")
    for entry in trendable:
        print(f"  {entry.canonical_variable_id}: {entry.canonical_question_text[:70]}")

    # ── Step 7: Show latest-wave-only highlights ────────────────
    latest_only = manifest.get_latest_wave_only()
    print(f"\n{'=' * 60}")
    print(f"LATEST-WAVE-ONLY VARIABLES ({len(latest_only)})")
    print(f"{'=' * 60}")
    for entry in latest_only[:20]:
        print(f"  {entry.canonical_variable_id}: {entry.canonical_question_text[:70]}")
    if len(latest_only) > 20:
        print(f"  ... and {len(latest_only) - 20} more")

    # ── Step 8: Show config summaries ───────────────────────────
    print(f"\n{'=' * 60}")
    print("CONFIGURATION")
    print(f"{'=' * 60}")

    pop_reg = AnalysisPopulationRegistry()
    print(f"\n  Analysis populations:")
    for pop in pop_reg.list_all():
        marker = " (DEFAULT)" if pop.is_default else ""
        print(f"    {pop.population_id}{marker}")
        print(f"      {pop.description[:80]}")

    seg_reg = SegmentRegistry()
    print(f"\n  Approved segments (trend mode):")
    for seg in seg_reg.list_for_trend_mode():
        print(f"    {seg.segment_id} ({seg.variable_code}): {seg.display_name}")

    print(f"\n{'=' * 60}")
    print("DONE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
