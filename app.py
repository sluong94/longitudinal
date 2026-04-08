"""
Longitudinal Survey Dashboard
Two modes: Latest Wave Explorer (W33) + Longitudinal Trends + Harmonization Review
Run with: streamlit run app.py
"""
import json, re
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ─── Config ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT

NAVY = "#002C77"
BLUE = "#009FDA"
PALETTE = [
    "#002C77", "#E63946", "#2A9D8F", "#E9C46A", "#264653",
    "#F4A261", "#7209B7", "#3A86FF", "#06D6A0", "#EF476F",
    "#118AB2", "#073B4C",
]
CHART_BG = dict(
    plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
    font=dict(family="Inter, Helvetica, Arial, sans-serif", color="#333333", size=12),
    margin=dict(l=10, r=30, t=60, b=30),
    xaxis=dict(showgrid=False, zeroline=False),
    yaxis=dict(showgrid=False, zeroline=False),
)
WAVE_LABELS = {
    1: "W13", 2: "W14", 3: "W15", 4: "W16", 5: "W17",
    6: "W18", 7: "W19", 8: "W20", 9: "W21", 10: "W22",
    11: "W23", 12: "W24", 13: "W25", 14: "W26", 15: "W28",
    16: "W29", 17: "W30", 18: "W31", 19: "W32", 20: "W33",
}
WAVE_LABELS_INV = {v: k for k, v in WAVE_LABELS.items()}
LATEST_WAVE = "W33"
LATEST_WAVE_CODE = 20

# ─── Page config & CSS ───────────────────────────────────────
st.set_page_config(page_title="Survey Dashboard", layout="wide")
st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; max-width: 1100px;}
    [data-testid="stSidebar"] {background-color: #F0F2F6;}
    [data-testid="stSidebar"] label {
        color: #002C77 !important; font-weight: 600 !important; font-size: 0.82rem !important;
    }
    h1 {color: #002C77; font-size: 1.7rem !important; letter-spacing: -0.02em;}
    h2, h3 {color: #002C77;}
    .sidebar-title {
        color: #002C77; font-size: 1.1rem; font-weight: 700;
        margin-bottom: 0.8rem; padding-bottom: 0.5rem;
        border-bottom: 2px solid #002C77;
    }
    details {
        border: 1px solid #E0E4E8 !important; border-radius: 8px !important;
        margin-bottom: 0.6rem !important; background: #FFFFFF !important;
    }
    details > summary {
        font-size: 0.92rem !important; font-weight: 500 !important;
        color: #1a1a1a !important; padding: 0.75rem 1rem !important;
    }
    [data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #E0E4E8;
        border-radius: 8px; padding: 0.6rem;
    }
    [data-testid="stMetric"] label {color: #666 !important; font-size: 0.75rem !important;}
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #002C77 !important; font-size: 1.5rem !important; font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)

# ─── Data Loading ────────────────────────────────────────────
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
    p = DATA_DIR / "data" / "w33_full.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return pd.read_excel(DATA_DIR / "Sample data file W33.xlsx", sheet_name="A1")

@st.cache_data
def load_longitudinal():
    p = DATA_DIR / "data" / "longitudinal_full.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return pd.read_excel(DATA_DIR / "Longitudinal_Dataset_Sample.xlsx")

# ─── Helpers ─────────────────────────────────────────────────
def parse_value_labels(val_str):
    if pd.isna(val_str) or val_str in ("", "{}"):
        return {}
    try:
        return json.loads(val_str)
    except Exception:
        return {}

def safe_int(s):
    return s.dropna().astype(float).astype(int)

def _layout(fig, title, subtitle, height):
    fig.update_layout(
        **CHART_BG,
        title=dict(
            text=f"<b>{title}</b><br><span style='font-size:11px;color:#666'>{subtitle}</span>",
            font=dict(size=13, color=NAVY), x=0, xanchor="left",
        ),
        height=height,
    )

# ─── Chart: simple horizontal bar ───────────────────────────
def simple_bar(labels, pcts, title, n):
    fig = go.Figure(go.Bar(
        x=pcts, y=labels, orientation="h",
        marker=dict(color=BLUE, cornerradius=4, line=dict(width=0)),
        text=[f"{p:.0f}%" for p in pcts],
        textposition="outside", textfont=dict(size=12),
        cliponaxis=False,
    ))
    _layout(fig, title, f"n = {n:,}", max(260, len(labels) * 38 + 80))
    fig.update_layout(
        xaxis=dict(range=[0, max(pcts) * 1.3 if pcts else 100],
                   showgrid=False, showticklabels=False),
        yaxis=dict(autorange="reversed", showgrid=False,
                   tickfont=dict(color="#333333", size=12)),
    )
    return fig

# ─── Chart: grouped horizontal bar with Overall baseline ────
def grouped_compare(labels, overall_pcts, group_data, title, n):
    fig = go.Figure()
    labels_r = labels[::-1]
    overall_r = overall_pcts[::-1]
    fig.add_trace(go.Bar(
        y=labels_r, x=overall_r, orientation="h", name="Overall",
        marker_color="#D0D0D0",
        text=[f"{p:.0f}%" for p in overall_r],
        textposition="outside", textfont=dict(size=11, color="#666"),
        cliponaxis=False,
    ))
    for i, (gl, gp) in enumerate(group_data):
        gp_r = gp[::-1]
        fig.add_trace(go.Bar(
            y=labels_r, x=gp_r, orientation="h", name=gl,
            marker_color=PALETTE[i % len(PALETTE)],
            text=[f"{p:.0f}%" for p in gp_r],
            textposition="outside", textfont=dict(size=11),
            cliponaxis=False,
        ))
    _layout(fig, title, f"n = {n:,} | Gray = Overall",
            max(400, len(labels) * 55 + 120))
    fig.update_layout(
        barmode="group",
        margin=dict(l=10, r=200, t=65, b=40),
        yaxis=dict(tickfont=dict(color="#333333", size=11)),
        xaxis=dict(showticklabels=False, showgrid=False),
        legend=dict(orientation="v", yanchor="top", y=0.99,
                    xanchor="left", x=1.02, font=dict(size=11)),
    )
    return fig

# ─── Chart: trend line (wave-over-wave) ─────────────────────
def trend_line_chart(wave_names, series_dict, title, subtitle=""):
    """series_dict: {series_name: [values_per_wave]}"""
    fig = go.Figure()
    for i, (name, vals) in enumerate(series_dict.items()):
        fig.add_trace(go.Scatter(
            x=wave_names, y=vals, mode="lines+markers+text",
            name=name, line=dict(color=PALETTE[i % len(PALETTE)], width=2.5),
            marker=dict(size=8),
            text=[f"{v:.0f}%" if pd.notna(v) else "" for v in vals],
            textposition="top center", textfont=dict(size=10),
        ))
    _layout(fig, title, subtitle, 420)
    fig.update_layout(
        margin=dict(l=10, r=30, t=70, b=50),
        xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(showgrid=True, gridcolor="#F0F0F0", ticksuffix="%",
                   rangemode="tozero"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=11)),
        hovermode="x unified",
    )
    return fig

# ─── Sidebar ─────────────────────────────────────────────────
st.sidebar.markdown('<div class="sidebar-title">Survey Dashboard</div>',
                    unsafe_allow_html=True)
mode = st.sidebar.radio(
    "Mode",
    ["Latest Wave Explorer", "Longitudinal Trends", "Harmonization Review"],
)

# ═══════════════════════════════════════════════════════════════
# MODE 1: LATEST WAVE EXPLORER
# ═══════════════════════════════════════════════════════════════
if mode == "Latest Wave Explorer":
    st.title("Latest Wave Explorer (W33)")
    st.markdown('<div style="height:4px;background:linear-gradient(90deg,#002C77,#009FDA);border-radius:2px;margin-bottom:0.5rem"></div>', unsafe_allow_html=True)
    st.caption("Broad exploration of the newest wave. Not limited to historically comparable variables.")

    manifest = load_manifest()
    w33_display = manifest[
        (manifest["latest_wave_present"] == True) & (manifest["display_eligible"] == True)
    ].copy()

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Display Variables", len(w33_display))
    c2.metric("Trend-Eligible", len(w33_display[w33_display["trend_eligible"] == True]))
    c3.metric("W33-Only (New)", len(w33_display[w33_display["historical_present"] == False]))
    try:
        raw = load_w33_raw()
        c4.metric("Respondents", f"{len(raw):,}")
    except Exception:
        c4.metric("Respondents", "N/A")

    st.sidebar.markdown("---")
    st.sidebar.metric("Respondents", f"{len(raw) if 'raw' in dir() else 'N/A':,}" if 'raw' in dir() else "N/A")

    # Search + filter
    search = st.text_input("Search questions...",
                           placeholder="Type to find a question or variable...",
                           key="w33_search")

    col_l, col_r = st.columns(2)
    with col_l:
        source_filter = st.multiselect("Source", ["both", "latest_wave"],
                                        default=["both", "latest_wave"])
    with col_r:
        qtype_opts = sorted(w33_display["question_type"].dropna().unique())
        qtype_filter = st.multiselect("Question Type", qtype_opts, default=qtype_opts)

    filtered = w33_display[
        w33_display["source_dataset"].isin(source_filter)
        & w33_display["question_type"].isin(qtype_filter)
    ]
    if search:
        sl = search.lower()
        mask = (
            filtered["canonical_variable_id"].str.contains(sl, case=False, na=False)
            | filtered["canonical_question_text"].str.contains(sl, case=False, na=False)
            | filtered["question_family"].str.contains(sl, case=False, na=False)
        )
        filtered = filtered[mask]

    # Group by question family
    families = filtered.groupby("question_family")
    st.write(f"**{len(filtered)} variables** in **{len(families)} question groups**")

    try:
        raw = load_w33_raw()
        has_raw = True
    except Exception:
        has_raw = False

    for family_name, family_df in sorted(families, key=lambda x: x[0]):
        family_rows = family_df.sort_values("canonical_variable_id")
        first_row = family_rows.iloc[0]
        q_text = first_row["canonical_question_text"] if pd.notna(first_row["canonical_question_text"]) else family_name
        label = f"{family_name}: {q_text[:80]}" if q_text != family_name else family_name
        trend_tag = " | trendable" if family_rows["trend_eligible"].any() else ""

        with st.expander(f"{label}{trend_tag}", expanded=bool(search)):
            for _, row in family_rows.iterrows():
                var_id = row["canonical_variable_id"]
                vals = parse_value_labels(row.get("value_labels", "{}"))
                q_display = row["canonical_question_text"] if pd.notna(row["canonical_question_text"]) else var_id

                if len(family_rows) > 1:
                    st.markdown(f"**{var_id}**: {q_display}")

                if has_raw and var_id in raw.columns:
                    col_data = raw[var_id].dropna()
                    n = len(col_data)
                    if n > 0 and vals:
                        counts = safe_int(col_data).value_counts().sort_index()
                        counts = counts[~counts.index.isin([98, 99, 999])]
                        if len(counts) > 0:
                            labels_list = [vals.get(str(v), str(v)) for v in counts.index]
                            pcts = (counts / counts.sum() * 100).values.tolist()
                            fig = simple_bar(labels_list, pcts, q_display, n)
                            st.plotly_chart(fig, key=f"w33_{var_id}", use_container_width=True)
                        else:
                            st.caption(f"n = {n}")
                    elif n > 0:
                        st.caption(f"n = {n} | No coded values")
                        st.write(col_data.value_counts().head(10).to_frame("Count"))
                    else:
                        st.caption("No data in sample")
                else:
                    st.caption(f"Variable: `{var_id}` | Type: {row['question_type']}")
                    if vals:
                        st.write(", ".join([f"{k}={v}" for k, v in list(vals.items())[:8]]))

# ═══════════════════════════════════════════════════════════════
# MODE 2: LONGITUDINAL TRENDS
# ═══════════════════════════════════════════════════════════════
elif mode == "Longitudinal Trends":
    st.title("Longitudinal Trends")
    st.markdown('<div style="height:4px;background:linear-gradient(90deg,#002C77,#009FDA);border-radius:2px;margin-bottom:0.5rem"></div>', unsafe_allow_html=True)
    st.caption("Wave-over-wave analysis. Only exact-match trendable variables. "
               "Default: employed 18-65, balanced-country intersection.")

    manifest = load_manifest()
    trendable = manifest[manifest["trend_eligible"] == True].copy()

    # Load data
    try:
        long_df = load_longitudinal()
        has_data = True
        n_total = len(long_df)
    except Exception:
        has_data = False
        n_total = 0

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Trendable Variables", len(trendable))
    c2.metric("Waves", f"W13-W33 ({len(WAVE_LABELS)})")
    c3.metric("Respondents (all waves)", f"{n_total:,}" if has_data else "N/A")

    if not has_data:
        st.warning("No longitudinal data loaded. Convert your full Excel file using:\n\n"
                   "`python scripts/convert_to_parquet.py --longitudinal \"path/to/file.xlsx\"`")
    else:
        st.sidebar.markdown("---")
        st.sidebar.metric("Total Respondents", f"{n_total:,}")

        # Wave selector
        available_waves = sorted(long_df["Wave"].dropna().unique().tolist())
        available_wave_labels = [WAVE_LABELS.get(int(w), f"W{int(w)}") for w in available_waves]
        st.sidebar.markdown("**Waves to include:**")
        selected_wave_labels = st.sidebar.multiselect(
            "Waves", available_wave_labels, default=available_wave_labels,
            label_visibility="collapsed"
        )
        selected_wave_codes = [WAVE_LABELS_INV[wl] for wl in selected_wave_labels if wl in WAVE_LABELS_INV]

        # Filter data to selected waves
        df_waves = long_df[long_df["Wave"].isin(selected_wave_codes)].copy()
        wave_order = [WAVE_LABELS[c] for c in sorted(selected_wave_codes)]

        # Variable selector
        st.subheader("Select a Variable")
        trend_options = trendable["canonical_variable_id"].tolist()
        trend_labels = {
            row["canonical_variable_id"]: f"{row['canonical_variable_id']}: {str(row['canonical_question_text'])[:60]}"
            for _, row in trendable.iterrows()
        }
        selected_var = st.selectbox(
            "Trendable variable",
            trend_options,
            format_func=lambda x: trend_labels.get(x, x),
        )

        if selected_var and selected_var in df_waves.columns:
            row_meta = trendable[trendable["canonical_variable_id"] == selected_var].iloc[0]
            vals = parse_value_labels(row_meta.get("value_labels", "{}"))
            q_text = row_meta["canonical_question_text"] if pd.notna(row_meta["canonical_question_text"]) else selected_var
            q_type = row_meta["question_type"]

            st.markdown(f"**{q_text}**")
            st.caption(f"Type: {q_type} | Population: {row_meta['analysis_population_id']} | Country: {row_meta['country_mode_default']}")

            # Compute wave-over-wave percentages
            col_data = df_waves[["Wave", selected_var]].dropna(subset=[selected_var]).copy()

            if vals and q_type in ("single_select", "scale", "binary"):
                col_data[selected_var] = safe_int(col_data[selected_var])
                col_data = col_data[~col_data[selected_var].isin([98, 99, 999])]

                # Compute % per wave per response
                series_dict = {}
                n_per_wave = {}
                for wc in sorted(selected_wave_codes):
                    wl = WAVE_LABELS[wc]
                    wdf = col_data[col_data["Wave"] == wc]
                    n_per_wave[wl] = len(wdf)

                resp_vals = sorted(col_data[selected_var].unique())
                for rv in resp_vals:
                    label = vals.get(str(rv), str(rv))
                    pcts = []
                    for wc in sorted(selected_wave_codes):
                        wdf = col_data[col_data["Wave"] == wc]
                        n = len(wdf)
                        pct = (wdf[selected_var] == rv).sum() / n * 100 if n > 0 else None
                        pcts.append(pct)
                    series_dict[label] = pcts

                # n= subtitle
                n_str = " | ".join([f"{wl}: n={n_per_wave.get(wl, 0):,}" for wl in wave_order[:3]])
                if len(wave_order) > 3:
                    n_str += f" | ... ({len(wave_order)} waves)"

                fig = trend_line_chart(wave_order, series_dict, q_text, n_str)
                st.plotly_chart(fig, use_container_width=True, key=f"trend_{selected_var}")

                # Data table
                with st.expander("Show data table"):
                    table_data = {"Wave": wave_order, "n": [n_per_wave.get(w, 0) for w in wave_order]}
                    for label, pcts in series_dict.items():
                        table_data[label] = [f"{p:.1f}%" if p is not None else "-" for p in pcts]
                    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

            else:
                # Numeric or open: show mean per wave
                try:
                    col_data[selected_var] = pd.to_numeric(col_data[selected_var], errors="coerce")
                    means = col_data.groupby("Wave")[selected_var].mean()
                    counts = col_data.groupby("Wave")[selected_var].count()
                    wave_names = [WAVE_LABELS.get(int(w), f"W{int(w)}") for w in means.index]
                    fig = trend_line_chart(wave_names, {"Mean": means.values.tolist()},
                                           f"Mean: {q_text}", f"Across {len(means)} waves")
                    st.plotly_chart(fig, use_container_width=True, key=f"trend_{selected_var}")
                except Exception as e:
                    st.info(f"Cannot chart this variable: {e}")

        elif selected_var:
            st.warning(f"Variable `{selected_var}` not found in longitudinal data. "
                       "This may be available once the full dataset is converted.")

        # Per-wave respondent counts
        st.divider()
        st.subheader("Per-Wave Summary")
        if has_data:
            wave_counts = df_waves.groupby("Wave").size().reset_index(name="Respondents")
            wave_counts["Wave Label"] = wave_counts["Wave"].map(lambda w: WAVE_LABELS.get(int(w), f"W{int(w)}"))
            # Country count per wave
            if "hCountry" in df_waves.columns:
                country_counts = df_waves.groupby("Wave")["hCountry"].nunique().reset_index(name="Countries")
                wave_counts = wave_counts.merge(country_counts, on="Wave", how="left")
            st.dataframe(
                wave_counts[["Wave Label", "Respondents"] + (["Countries"] if "Countries" in wave_counts.columns else [])],
                hide_index=True, use_container_width=True,
            )

# ═══════════════════════════════════════════════════════════════
# MODE 3: HARMONIZATION REVIEW
# ═══════════════════════════════════════════════════════════════
elif mode == "Harmonization Review":
    st.title("Harmonization Review")
    st.markdown('<div style="height:4px;background:linear-gradient(90deg,#002C77,#009FDA);border-radius:2px;margin-bottom:0.5rem"></div>', unsafe_allow_html=True)
    st.caption("Inspect the harmonization manifest and review pending trendability decisions.")

    manifest = load_manifest()
    summary = load_manifest_summary()

    cols = st.columns(5)
    cols[0].metric("Total Variables", summary["total_variables"])
    cols[1].metric("Trend-Eligible", summary["trend_eligible"])
    cols[2].metric("Latest-Wave Only", summary["latest_wave_only"])
    cols[3].metric("Historical Only", summary["historical_only"])
    cols[4].metric("Excluded", summary["excluded"])

    tab1, tab2, tab3 = st.tabs(["Pending Review", "Full Manifest", "Audit Report"])

    with tab1:
        st.subheader("Variables Pending Review")
        pending = load_pending_review()
        if len(pending) == 0:
            st.success("No variables pending review.")
        else:
            cat_opts = sorted(pending["review_category"].unique())
            cat_filter = st.multiselect("Category", cat_opts, default=cat_opts)
            fp = pending[pending["review_category"].isin(cat_filter)]
            st.write(f"**{len(fp)}** items")
            st.dataframe(
                fp[["variable", "question_family", "question_text", "review_category",
                    "option_diff_note", "recommendation"]].rename(columns={
                    "variable": "Variable", "question_family": "Family",
                    "question_text": "Question", "review_category": "Category",
                    "option_diff_note": "Diff Note", "recommendation": "Recommendation",
                }),
                use_container_width=True, height=400,
            )

    with tab2:
        st.subheader("Full Manifest")
        search_m = st.text_input("Search", "", key="msearch")
        col_l, col_r = st.columns(2)
        with col_l:
            src_f = st.multiselect("Source", sorted(manifest["source_dataset"].dropna().unique()),
                                    default=sorted(manifest["source_dataset"].dropna().unique()), key="msrc")
        with col_r:
            trend_f = st.multiselect("Trendable", [True, False], default=[True, False], key="mtrend")
        filt = manifest[manifest["source_dataset"].isin(src_f) & manifest["trend_eligible"].isin(trend_f)]
        if search_m:
            mask = (filt["canonical_variable_id"].str.contains(search_m, case=False, na=False)
                    | filt["canonical_question_text"].str.contains(search_m, case=False, na=False))
            filt = filt[mask]
        st.write(f"**{len(filt)}** / {len(manifest)} variables")
        st.dataframe(
            filt[["canonical_variable_id", "question_family", "canonical_question_text",
                  "source_dataset", "exact_match_status", "trend_eligible", "reason_not_trendable"]].rename(columns={
                "canonical_variable_id": "Variable", "question_family": "Family",
                "canonical_question_text": "Question", "source_dataset": "Source",
                "exact_match_status": "Match", "trend_eligible": "Trendable",
                "reason_not_trendable": "Reason",
            }),
            use_container_width=True, height=500,
        )

    with tab3:
        st.subheader("Trend Eligibility Audit")
        try:
            with open(OUTPUT_DIR / "trend_eligibility_audit.json") as f:
                audit = json.load(f)
            c1, c2 = st.columns(2)
            c1.metric("Total Assessed", audit["total"])
            c1.metric("Trend-Eligible", audit["trend_eligible"])
            with c2:
                st.write("**First Failure Distribution**")
                fail_df = pd.DataFrame([
                    {"Rule": k, "Count": v}
                    for k, v in sorted(audit["first_failure_distribution"].items(), key=lambda x: -x[1])
                ])
                st.dataframe(fail_df, hide_index=True, use_container_width=True)
        except Exception as e:
            st.error(f"Could not load audit: {e}")

# ─── Footer ──────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.caption(
    "**Population:** employed 18-65, balanced countries\n\n"
    "**Latest wave:** W33\n\n"
    "**Historical:** W13-W32 (19 waves)"
)
