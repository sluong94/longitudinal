#!/usr/bin/env python3
"""
Generate the harmonization manifest from source files.

This is the primary entry point for building the harmonization layer.
It reads all three source files, builds the variable registry,
and produces the harmonization manifest as both CSV and JSON.

Usage:
    python scripts/generate_harmonization_manifest.py
    python scripts/generate_harmonization_manifest.py --wave W33
    python scripts/generate_harmonization_manifest.py --wave W31 --trend-only

Inputs (expected in repo root):
    - Labeling Databook W32.xlsx
    - Sample data file W33.xlsx
    - Longitudinal_Dataset_Sample.xlsx
    - config/trend_whitelist.json  (optional)

Outputs (written to output/):
    - harmonization_manifest.csv / .json
    - manifest_summary.json
    - trend_eligibility_audit.json
    - pending_review.csv  (variables needing manual trendability decisions)
    - wave_summary.csv    (per-wave variable counts)
    - wave_<label>_variables.csv  (when --wave is specified)
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.parsers import W33Parser, LongitudinalParser, LabelingWorkbookParser
from src.harmonization import (
    HarmonizationManifest,
    VariableRegistry,
    TrendEligibility,
    WaveOutputEngine,
)
from src.config import AnalysisPopulationRegistry, SegmentRegistry, CountryComparabilityEngine


def load_whitelist(config_dir: Path) -> set[str]:
    """Load the trend whitelist from config/trend_whitelist.json."""
    whitelist_path = config_dir / "trend_whitelist.json"
    if not whitelist_path.exists():
        return set()
    with open(whitelist_path) as f:
        data = json.load(f)
    approved = data.get("approved", {})
    # approved is a dict of {variable_code: reason}
    return set(approved.keys())


def main():
    parser = argparse.ArgumentParser(
        description="Generate harmonization manifest and wave-specific outputs"
    )
    parser.add_argument(
        "--wave",
        type=str,
        default=None,
        help="Generate output for a specific wave (e.g., W33, W31). "
             "Produces a variable list CSV for that wave.",
    )
    parser.add_argument(
        "--trend-only",
        action="store_true",
        help="When used with --wave, only show trend-eligible variables.",
    )
    args = parser.parse_args()

    data_dir = project_root
    output_dir = project_root / "output"
    config_dir = project_root / "config"
    output_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("HARMONIZATION MANIFEST GENERATOR")
    print("=" * 60)

    # ── Step 1: Parse source files ──────────────────────────────
    print("\n[1/7] Parsing labeling workbook...")
    labeling_parser = LabelingWorkbookParser(
        data_dir / "Labeling Databook W32.xlsx"
    )
    labeling_vars = labeling_parser.parse()
    print(f"  -> {len(labeling_vars)} variables parsed")
    print(f"  -> Waves: {labeling_parser.wave_map}")
    print(f"  -> Derived (UDV) variables: {len(labeling_parser.list_derived_variables())}")

    print("\n[2/7] Parsing W33 datamap...")
    w33_parser = W33Parser(data_dir / "Sample data file W33.xlsx")
    w33_datamap = w33_parser.parse_datamap()
    w33_columns = w33_parser.get_column_names()
    print(f"  -> {len(w33_datamap)} variables in datamap")
    print(f"  -> {len(w33_columns)} columns in raw data")
    print(f"  -> Survey variables: {len(w33_parser.get_survey_variables())}")
    print(f"  -> Hidden/derived: {len(w33_parser.get_hidden_derived_variables())}")
    print(f"  -> Excluded (admin/timing/QC/geo): {len(w33_parser.get_excluded_variables())}")

    print("\n[3/7] Parsing longitudinal dataset...")
    long_parser = LongitudinalParser(
        data_dir / "Longitudinal_Dataset_Sample.xlsx"
    )
    long_columns = long_parser.get_column_names()
    print(f"  -> {len(long_columns)} columns")

    # Overlap analysis
    overlap = set(w33_columns) & set(long_columns)
    w33_only = set(w33_columns) - set(long_columns)
    hist_only = set(long_columns) - set(w33_columns)
    print(f"\n  Column overlap analysis:")
    print(f"    Overlap (candidate trendable): {len(overlap)}")
    print(f"    W33-only: {len(w33_only)}")
    print(f"    Historical-only: {len(hist_only)}")

    # ── Step 2: Load whitelist ──────────────────────────────────
    print("\n[4/7] Loading trend whitelist...")
    whitelist = load_whitelist(config_dir)
    if whitelist:
        print(f"  -> {len(whitelist)} whitelisted variables: {sorted(whitelist)}")
    else:
        print("  -> No whitelisted variables (config/trend_whitelist.json)")

    # ── Step 3: Build variable registry ─────────────────────────
    print("\n[5/7] Building variable registry...")
    registry = VariableRegistry()
    registry.build_from_parsers(
        labeling_vars=labeling_vars,
        w33_datamap=w33_datamap,
        w33_columns=w33_columns,
        longitudinal_columns=long_columns,
    )
    print(f"  -> {registry.size} canonical variables registered")
    print(f"  -> Display-eligible: {len(registry.list_display_eligible())}")
    print(f"  -> Segment-eligible: {len(registry.list_segment_eligible())}")
    print(f"  -> Latest-wave-only: {len(registry.list_latest_wave_only())}")
    print(f"  -> Historical-only: {len(registry.list_historical_only())}")

    # ── Step 4: Build harmonization manifest ────────────────────
    print("\n[6/7] Building harmonization manifest...")
    manifest = HarmonizationManifest(registry, trend_whitelist=whitelist)
    entries = manifest.build(
        labeling_vars=labeling_vars,
        w33_datamap=w33_datamap,
        default_population_id="trend_default_employed_18_65",
    )

    summary = manifest.summary()
    print(f"  -> Total entries: {summary['total_variables']}")
    print(f"  -> Trend-eligible: {summary['trend_eligible']}")
    print(f"  -> Latest-wave-only (display): {summary['latest_wave_only']}")
    print(f"  -> Historical-only (display): {summary['historical_only']}")
    print(f"  -> Excluded: {summary['excluded']}")

    # ── Step 5: Run trend eligibility audit ─────────────────────
    print("\n[7/7] Running trend eligibility audit...")
    te = TrendEligibility()
    audit = te.audit_report(entries)
    print(f"  -> Trend-eligible (strict rules): {audit['trend_eligible']}")
    print(f"  -> Rule failure distribution:")
    for rule, count in sorted(audit["first_failure_distribution"].items()):
        print(f"      {rule}: {count}")

    # ── Step 6: Export core files ───────────────────────────────
    print(f"\n{'=' * 60}")
    print("EXPORTING")
    print("=" * 60)

    manifest.export_csv(output_dir / "harmonization_manifest.csv")
    print(f"  -> {output_dir / 'harmonization_manifest.csv'}")

    manifest.export_json(output_dir / "harmonization_manifest.json")
    print(f"  -> {output_dir / 'harmonization_manifest.json'}")

    with open(output_dir / "manifest_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  -> {output_dir / 'manifest_summary.json'}")

    with open(output_dir / "trend_eligibility_audit.json", "w") as f:
        json.dump(audit, f, indent=2)
    print(f"  -> {output_dir / 'trend_eligibility_audit.json'}")

    # ── Step 7: Export review file ──────────────────────────────
    manifest.export_review_csv(
        output_dir / "pending_review.csv",
        labeling_vars=labeling_vars,
        w33_datamap=w33_datamap,
    )
    pending_count = len(manifest.get_pending_review())
    print(f"  -> {output_dir / 'pending_review.csv'} ({pending_count} variables pending review)")

    # ── Step 8: Wave-specific outputs ───────────────────────────
    wave_engine = WaveOutputEngine(entries, wave_labels=labeling_parser.wave_map)
    # Extend wave labels to include W33
    wave_engine.wave_labels[20] = "W33"

    wave_engine.export_wave_summary_csv(output_dir / "wave_summary.csv")
    print(f"  -> {output_dir / 'wave_summary.csv'}")

    if args.wave:
        wave_label = args.wave.upper()
        out_name = f"wave_{wave_label}_variables.csv"
        wave_engine.export_wave_variable_list(
            wave_label=wave_label,
            output_path=output_dir / out_name,
            trend_only=args.trend_only,
        )
        mode_str = "trend-only" if args.trend_only else "all display-eligible"
        var_count = len(
            wave_engine.get_trendable_for_wave(wave_label)
            if args.trend_only
            else wave_engine.get_variables_for_wave(wave_label)
        )
        print(f"  -> {output_dir / out_name} ({var_count} {mode_str} variables)")

    # ── Step 9: Show trendable variables ────────────────────────
    trendable = manifest.get_trendable()
    print(f"\n{'=' * 60}")
    print(f"TREND-ELIGIBLE VARIABLES ({len(trendable)})")
    print("=" * 60)
    whitelisted_trend = [e for e in trendable if "Whitelisted" in e.reason_not_trendable]
    auto_trend = [e for e in trendable if "Whitelisted" not in e.reason_not_trendable]

    if auto_trend:
        print(f"\n  Auto-approved ({len(auto_trend)}):")
        for entry in auto_trend:
            print(f"    {entry.canonical_variable_id}: {entry.canonical_question_text[:65]}")

    if whitelisted_trend:
        print(f"\n  Whitelisted ({len(whitelisted_trend)}):")
        for entry in whitelisted_trend:
            print(f"    {entry.canonical_variable_id}: {entry.canonical_question_text[:65]}")

    # ── Step 10: Show latest-wave-only highlights ───────────────
    latest_only = manifest.get_latest_wave_only()
    print(f"\n{'=' * 60}")
    print(f"LATEST-WAVE-ONLY VARIABLES ({len(latest_only)})")
    print("=" * 60)
    for entry in latest_only[:20]:
        print(f"  {entry.canonical_variable_id}: {entry.canonical_question_text[:70]}")
    if len(latest_only) > 20:
        print(f"  ... and {len(latest_only) - 20} more")

    # ── Step 11: Per-wave summary table ─────────────────────────
    print(f"\n{'=' * 60}")
    print("PER-WAVE SUMMARY")
    print("=" * 60)
    for ws in wave_engine.per_wave_summary():
        latest_tag = " *" if ws["is_latest"] else ""
        lo_count = ws["latest_wave_only_count"]
        lo_str = f", {lo_count} latest-only" if lo_count else ""
        print(
            f"  {ws['wave_label']}{latest_tag}: "
            f"{ws['total_display_variables']} display vars, "
            f"{ws['trend_eligible_variables']} trendable"
            f"{lo_str}"
        )

    # ── Step 12: Show config summaries ──────────────────────────
    print(f"\n{'=' * 60}")
    print("CONFIGURATION")
    print("=" * 60)

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
    print("=" * 60)


if __name__ == "__main__":
    main()
