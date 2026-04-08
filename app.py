"""
Longitudinal Survey Dashboard

A dual-mode interactive dashboard for exploring survey data:
- Mode 1: Latest Wave Explorer (W33) — broad exploration, all variables
- Mode 2: Longitudinal Trend Viewer — strict trendable variables only

Run with: streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# ─── Config ────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT

WAVE_LABELS = {
    1: "W13", 2: "W14", 3: "W15", 4: "W16", 5: "W17",
    6: "W18", 7: "W19", 8: "W20", 9: "W21", 10: "W22",
    11: "W23", 12: "W24", 13: "W25", 14: "W26", 15: "W28",
    16: "W29", 17: "W30", 18: "W31", 19: "W32", 20: "W33",
}
WAVE_LABELS_INV = {v: k for k, v in WAVE_LABELS.items()}
LATEST_WAVE = "W33"


# ─── Data Loading (cached) ────────────────────────────────────
@st.cache_data
def load_manifest():
    return pd.read_csv(OUTPUT_DIR / "harmonization_manifest.csv")


@st.cache_data
def load_pending_review():
    return pd.read_csv(OUTPUT_DIR / "pending_review.csv")


@st.cache_data
def load_wave_summary():
    return pd.read_csv(OUTPUT_DIR / "wave_summary.csv")


@st.cache_data
def load_manifest_summary():
    with open(OUTPUT_DIR / "manifest_summary.json") as f:
        return json.load(f)


@st.cache_data
def load_w33_raw():
    """Load W33 data — prefers Parquet (fast), falls back to Excel (sample)."""
    parquet_path = DATA_DIR / "data" / "w33_full.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    return pd.read_excel(DATA_DIR / "Sample data file W33.xlsx", sheet_name="A1")


@st.cache_data
def load_longitudinal_sample():
    """Load longitudinal data — prefers Parquet (fast), falls back to Excel (sample)."""
    parquet_path = DATA_DIR / "data" / "longitudinal_full.parquet"
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    return pd.read_excel(DATA_DIR / "Longitudinal_Dataset_Sample.xlsx")


@st.cache_data
def load_w33_wave_variables():
    path = OUTPUT_DIR / "wave_W33_variables.csv"
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


# ─── Helper: decode value labels ──────────────────────────────
def parse_value_labels(val_str):
    """Parse value labels from JSON string in CSV."""
    if pd.isna(val_str) or val_str == "" or val_str == "{}":
        return {}
    try:
        return json.loads(val_str)
    except (json.JSONDecodeError, TypeError):
        return {}


def format_value_labels(val_dict):
    """Format value labels dict as readable text."""
    if not val_dict:
        return "_(no coded values)_"
    lines = [f"**{k}** = {v}" for k, v in sorted(val_dict.items(), key=lambda x: safe_float(x[0]))]
    return "  \n".join(lines)


def safe_float(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0


# ─── Sidebar ──────────────────────────────────────────────────
st.set_page_config(page_title="Survey Dashboard", layout="wide")

st.sidebar.title("Survey Dashboard")
mode = st.sidebar.radio(
    "Dashboard Mode",
    ["Latest Wave Explorer", "Longitudinal Trends", "Harmonization Review"],
    help=(
        "**Latest Wave Explorer**: Explore all W33 variables broadly.\n\n"
        "**Longitudinal Trends**: Only exact-match trendable variables across waves.\n\n"
        "**Harmonization Review**: Inspect and manage variable harmonization."
    ),
)


# ═══════════════════════════════════════════════════════════════
# MODE 1: LATEST WAVE EXPLORER
# ═══════════════════════════════════════════════════════════════
if mode == "Latest Wave Explorer":
    st.title("Latest Wave Explorer (W33)")
    st.caption(
        "Broad exploration of the newest wave. Includes all display-eligible "
        "variables — not limited to historically comparable ones."
    )

    manifest = load_manifest()
    w33_vars = manifest[manifest["latest_wave_present"] == True]
    w33_display = w33_vars[w33_vars["display_eligible"] == True].copy()

    # ── Summary metrics ────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total W33 Variables", len(w33_vars))
    col2.metric("Display-Eligible", len(w33_display))
    col3.metric("Trend-Eligible", len(w33_display[w33_display["trend_eligible"] == True]))
    col4.metric("W33-Only (New)", len(w33_display[w33_display["historical_present"] == False]))

    st.divider()

    # ── Filters ────────────────────────────────────────────────
    col_left, col_right = st.columns(2)
    with col_left:
        source_filter = st.multiselect(
            "Source",
            options=["both", "latest_wave"],
            default=["both", "latest_wave"],
            help="'both' = also in historical dataset, 'latest_wave' = W33-only",
        )
    with col_right:
        qtype_options = sorted(w33_display["question_type"].dropna().unique())
        qtype_filter = st.multiselect(
            "Question Type",
            options=qtype_options,
            default=qtype_options,
        )

    search = st.text_input("Search variables (name or question text)", "")

    # ── Apply filters ──────────────────────────────────────────
    filtered = w33_display[
        w33_display["source_dataset"].isin(source_filter)
        & w33_display["question_type"].isin(qtype_filter)
    ]
    if search:
        mask = (
            filtered["canonical_variable_id"].str.contains(search, case=False, na=False)
            | filtered["canonical_question_text"].str.contains(search, case=False, na=False)
            | filtered["question_family"].str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    st.write(f"**{len(filtered)} variables** matching filters")

    # ── Variable list ──────────────────────────────────────────
    display_cols = [
        "canonical_variable_id", "question_family", "canonical_question_text",
        "question_type", "source_dataset", "trend_eligible",
    ]
    st.dataframe(
        filtered[display_cols].rename(columns={
            "canonical_variable_id": "Variable",
            "question_family": "Family",
            "canonical_question_text": "Question",
            "question_type": "Type",
            "source_dataset": "Source",
            "trend_eligible": "Trendable",
        }),
        use_container_width=True,
        height=400,
    )

    # ── Variable detail ────────────────────────────────────────
    st.divider()
    st.subheader("Variable Detail")
    var_options = filtered["canonical_variable_id"].tolist()
    if var_options:
        selected_var = st.selectbox("Select a variable", var_options)
        row = filtered[filtered["canonical_variable_id"] == selected_var].iloc[0]

        col_a, col_b = st.columns(2)
        with col_a:
            st.write(f"**Variable:** `{row['canonical_variable_id']}`")
            st.write(f"**Family:** {row['question_family']}")
            st.write(f"**Type:** {row['question_type']}")
            st.write(f"**Source:** {row['source_dataset']}")
            st.write(f"**Trend-eligible:** {'Yes' if row['trend_eligible'] else 'No'}")
            if not row["trend_eligible"]:
                st.write(f"**Reason:** {row['reason_not_trendable']}")

        with col_b:
            st.write("**Question Text:**")
            st.info(row["canonical_question_text"] if pd.notna(row["canonical_question_text"]) else "_(none)_")
            vals = parse_value_labels(row.get("value_labels", "{}"))
            if vals:
                st.write("**Response Options:**")
                st.markdown(format_value_labels(vals))

        # Show raw data if available
        st.write("**Sample Data (W33 raw):**")
        try:
            raw = load_w33_raw()
            if selected_var in raw.columns:
                sample_data = raw[selected_var].dropna()
                if not sample_data.empty:
                    if vals:
                        mapped = sample_data.map(lambda x: vals.get(str(int(x)) if pd.notna(x) else "", str(x)))
                        st.write(mapped.value_counts().to_frame("Count"))
                    else:
                        st.write(sample_data.value_counts().head(20).to_frame("Count"))
                else:
                    st.write("_(no data in sample)_")
            else:
                st.write(f"_(column `{selected_var}` not in raw data)_")
        except Exception as e:
            st.write(f"_(could not load raw data: {e})_")


# ═══════════════════════════════════════════════════════════════
# MODE 2: LONGITUDINAL TRENDS
# ═══════════════════════════════════════════════════════════════
elif mode == "Longitudinal Trends":
    st.title("Longitudinal Trend Viewer")
    st.caption(
        "Strict wave-over-wave analysis. Only exact-match trendable variables. "
        "Default population: employed 18-65, balanced-country intersection."
    )

    manifest = load_manifest()
    trendable = manifest[manifest["trend_eligible"] == True].copy()

    # ── Summary ────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Trend-Eligible Variables", len(trendable))
    col2.metric("Historical Waves", "W13-W32 (19 waves)")
    col3.metric("Latest Wave", "W33")

    st.divider()

    # ── Wave summary table ─────────────────────────────────────
    st.subheader("Per-Wave Summary")
    wave_summary = load_wave_summary()
    st.dataframe(
        wave_summary.rename(columns={
            "wave_code": "Code",
            "wave_label": "Wave",
            "is_latest": "Latest?",
            "total_display_variables": "Display Variables",
            "trend_eligible_variables": "Trendable",
            "latest_wave_only_count": "Latest-Only",
        }),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # ── Wave selector ──────────────────────────────────────────
    st.subheader("Explore by Wave")
    wave_options = [WAVE_LABELS[k] for k in sorted(WAVE_LABELS.keys())]
    selected_wave = st.selectbox("Select a wave", wave_options, index=len(wave_options) - 1)

    is_latest = selected_wave == LATEST_WAVE
    if is_latest:
        st.info(f"**{selected_wave}** is the latest wave. Showing both trendable and W33-only variables.")
        wave_vars = manifest[
            (manifest["latest_wave_present"] == True)
            & (manifest["display_eligible"] == True)
        ]
    else:
        st.info(f"**{selected_wave}** is a historical wave. Showing trendable variables available in this wave.")
        wave_vars = trendable  # all trendable vars span the historical range

    # ── Show/hide trend-only toggle ────────────────────────────
    if is_latest:
        trend_only = st.checkbox("Show only trend-eligible variables", value=False)
        if trend_only:
            wave_vars = wave_vars[wave_vars["trend_eligible"] == True]

    st.write(f"**{len(wave_vars)} variables** for {selected_wave}")

    display_cols = [
        "canonical_variable_id", "question_family", "canonical_question_text",
        "question_type", "trend_eligible", "source_dataset",
    ]
    st.dataframe(
        wave_vars[display_cols].rename(columns={
            "canonical_variable_id": "Variable",
            "question_family": "Family",
            "canonical_question_text": "Question",
            "question_type": "Type",
            "trend_eligible": "Trendable",
            "source_dataset": "Source",
        }),
        use_container_width=True,
        height=400,
    )

    # ── Trendable variable detail ──────────────────────────────
    st.divider()
    st.subheader("Trend Variable Detail")
    trend_options = trendable["canonical_variable_id"].tolist()
    if trend_options:
        selected_trend = st.selectbox("Select a trendable variable", trend_options)
        row = trendable[trendable["canonical_variable_id"] == selected_trend].iloc[0]

        col_a, col_b = st.columns(2)
        with col_a:
            st.write(f"**Variable:** `{row['canonical_variable_id']}`")
            st.write(f"**Family:** {row['question_family']}")
            st.write(f"**Type:** {row['question_type']}")
            st.write(f"**Analysis Population:** {row['analysis_population_id']}")
            st.write(f"**Country Mode:** {row['country_mode_default']}")
        with col_b:
            st.write("**Question Text:**")
            st.info(row["canonical_question_text"] if pd.notna(row["canonical_question_text"]) else "_(none)_")
            vals = parse_value_labels(row.get("value_labels", "{}"))
            if vals:
                st.write("**Response Options:**")
                st.markdown(format_value_labels(vals))

        # Cross-wave data preview
        st.write("**Cross-Wave Data Preview:**")
        try:
            long_df = load_longitudinal_sample()
            if selected_trend in long_df.columns:
                wave_col = "Wave"
                if wave_col in long_df.columns:
                    pivot = long_df.groupby(wave_col)[selected_trend].value_counts().unstack(fill_value=0)
                    if vals:
                        pivot.columns = [vals.get(str(int(c)), str(c)) for c in pivot.columns]
                    pivot.index = [WAVE_LABELS.get(int(w), f"W{w}") for w in pivot.index]
                    st.dataframe(pivot, use_container_width=True)
                else:
                    st.write("_(no Wave column in data)_")
            else:
                st.write(f"_(column `{selected_trend}` not in longitudinal sample)_")
        except Exception as e:
            st.write(f"_(could not load data: {e})_")


# ═══════════════════════════════════════════════════════════════
# MODE 3: HARMONIZATION REVIEW
# ═══════════════════════════════════════════════════════════════
elif mode == "Harmonization Review":
    st.title("Harmonization Review")
    st.caption(
        "Inspect the harmonization manifest, review pending variables, "
        "and understand how trendability decisions were made."
    )

    manifest = load_manifest()
    summary = load_manifest_summary()

    # ── Overview metrics ───────────────────────────────────────
    cols = st.columns(5)
    cols[0].metric("Total Variables", summary["total_variables"])
    cols[1].metric("Trend-Eligible", summary["trend_eligible"])
    cols[2].metric("Latest-Wave Only", summary["latest_wave_only"])
    cols[3].metric("Historical Only", summary["historical_only"])
    cols[4].metric("Excluded", summary["excluded"])

    st.divider()

    # ── Tab layout ─────────────────────────────────────────────
    tab1, tab2, tab3 = st.tabs([
        "Pending Review", "Full Manifest", "Audit Report"
    ])

    # ── Tab 1: Pending Review ──────────────────────────────────
    with tab1:
        st.subheader("Variables Pending Manual Review")
        st.write(
            "These variables are present in **both** datasets but were not "
            "auto-approved for trending. Review and decide which to whitelist."
        )

        pending = load_pending_review()

        # Category filter
        cat_options = sorted(pending["review_category"].unique())
        cat_filter = st.multiselect(
            "Filter by category",
            options=cat_options,
            default=cat_options,
        )
        filtered_pending = pending[pending["review_category"].isin(cat_filter)]

        # Summary by category
        cat_counts = filtered_pending["review_category"].value_counts()
        for cat, count in cat_counts.items():
            if cat == "ONE_SIDE_UNDOCUMENTED":
                st.write(f"- **{cat}** ({count}): Column in both datasets, labels on one side only. _Most likely trendable._")
            elif cat == "OPEN_ENDED":
                st.write(f"- **{cat}** ({count}): Free-text responses. _Not trendable._")
            elif cat == "CODED_RESPONSE_CHANGE":
                st.write(f"- **{cat}** ({count}): Response options changed between waves. _Review if collapsible._")
            elif cat == "FLAG_DERIVED":
                st.write(f"- **{cat}** ({count}): QC/system flags. _Likely not needed._")

        st.dataframe(
            filtered_pending[[
                "variable", "question_family", "review_category",
                "reason_blocked", "historical_question_text", "w33_question_text",
                "historical_value_count", "w33_value_count", "recommendation",
            ]].rename(columns={
                "variable": "Variable",
                "question_family": "Family",
                "review_category": "Category",
                "reason_blocked": "Reason Blocked",
                "historical_question_text": "Historical Question",
                "w33_question_text": "W33 Question",
                "historical_value_count": "Hist Values",
                "w33_value_count": "W33 Values",
                "recommendation": "Recommendation",
            }),
            use_container_width=True,
            height=500,
        )

        # Detail view
        st.divider()
        st.subheader("Variable Detail")
        var_options = filtered_pending["variable"].tolist()
        if var_options:
            selected = st.selectbox("Select a variable to inspect", var_options, key="review_var")
            row = filtered_pending[filtered_pending["variable"] == selected].iloc[0]

            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Historical (Labeling Workbook)**")
                st.write(f"Question: {row['historical_question_text'] or '_(none)_'}")
                st.write(f"Value count: {row['historical_value_count']}")
                h_vals = parse_value_labels(row.get("historical_values", "{}"))
                if h_vals and isinstance(h_vals, dict):
                    st.markdown(format_value_labels(h_vals))
                elif isinstance(h_vals, str):
                    st.write(h_vals)
                else:
                    st.write("_(no labels)_")

            with col_b:
                st.write("**W33 (Datamap)**")
                st.write(f"Question: {row['w33_question_text'] or '_(none)_'}")
                st.write(f"Value count: {row['w33_value_count']}")
                w_vals = parse_value_labels(row.get("w33_values", "{}"))
                if w_vals and isinstance(w_vals, dict):
                    st.markdown(format_value_labels(w_vals))
                elif isinstance(w_vals, str):
                    st.write(w_vals)
                else:
                    st.write("_(no labels)_")

            st.info(f"**Recommendation:** {row['recommendation']}")

    # ── Tab 2: Full Manifest ───────────────────────────────────
    with tab2:
        st.subheader("Full Harmonization Manifest")

        # Filters
        col_l, col_m, col_r = st.columns(3)
        with col_l:
            src_filter = st.multiselect(
                "Source Dataset",
                options=sorted(manifest["source_dataset"].dropna().unique()),
                default=sorted(manifest["source_dataset"].dropna().unique()),
                key="manifest_src",
            )
        with col_m:
            match_filter = st.multiselect(
                "Match Status",
                options=sorted(manifest["exact_match_status"].dropna().unique()),
                default=sorted(manifest["exact_match_status"].dropna().unique()),
                key="manifest_match",
            )
        with col_r:
            trend_filter = st.multiselect(
                "Trend Eligible",
                options=[True, False],
                default=[True, False],
                key="manifest_trend",
            )

        search_manifest = st.text_input("Search", "", key="manifest_search")

        filt = manifest[
            manifest["source_dataset"].isin(src_filter)
            & manifest["exact_match_status"].isin(match_filter)
            & manifest["trend_eligible"].isin(trend_filter)
        ]
        if search_manifest:
            mask = (
                filt["canonical_variable_id"].str.contains(search_manifest, case=False, na=False)
                | filt["canonical_question_text"].str.contains(search_manifest, case=False, na=False)
            )
            filt = filt[mask]

        st.write(f"**{len(filt)}** / {len(manifest)} variables")
        st.dataframe(
            filt[[
                "canonical_variable_id", "question_family", "canonical_question_text",
                "source_dataset", "exact_match_status", "trend_eligible",
                "reason_not_trendable", "question_type",
            ]].rename(columns={
                "canonical_variable_id": "Variable",
                "question_family": "Family",
                "canonical_question_text": "Question",
                "source_dataset": "Source",
                "exact_match_status": "Match Status",
                "trend_eligible": "Trendable",
                "reason_not_trendable": "Reason",
                "question_type": "Type",
            }),
            use_container_width=True,
            height=500,
        )

    # ── Tab 3: Audit Report ────────────────────────────────────
    with tab3:
        st.subheader("Trend Eligibility Audit")
        try:
            with open(OUTPUT_DIR / "trend_eligibility_audit.json") as f:
                audit = json.load(f)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Variables Assessed", audit["total"])
                st.metric("Trend-Eligible", audit["trend_eligible"])

            with col2:
                st.write("**First Failure Distribution**")
                st.write(
                    "When a variable fails trend eligibility, which rule "
                    "blocks it first?"
                )
                fail_df = pd.DataFrame([
                    {"Rule": k, "Count": v}
                    for k, v in sorted(
                        audit["first_failure_distribution"].items(),
                        key=lambda x: -x[1],
                    )
                ])
                st.dataframe(fail_df, hide_index=True, use_container_width=True)

            st.write("**Per-Rule Failure Counts** (a variable can fail multiple rules)")
            rule_df = pd.DataFrame([
                {"Rule": k, "Failures": v}
                for k, v in sorted(
                    audit["rule_failures"].items(),
                    key=lambda x: -x[1],
                )
            ])
            st.dataframe(rule_df, hide_index=True, use_container_width=True)

        except Exception as e:
            st.error(f"Could not load audit report: {e}")


# ─── Footer ───────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    "**Population:** employed 18-65, balanced countries  \n"
    "**Latest wave:** W33  \n"
    "**Historical:** W13-W32 (19 waves)"
)
