
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from core.state import init_state, require_data, get_analysis
from core.schema import (
    COL_ID,
    COL_NAME,
    COL_COST,
    COL_FUNC,
    COL_DESC,
    COL_ROI,
    COL_NPV,
    COL_PAYBACK,
    CRITERIA,
    CRITERIA_NAMES,
)
from core import ui


# ============================================================
# INITIALIZATION
# ============================================================

init_state()
require_data()

ss = st.session_state

ui.page_header(
    "Initiative Evaluation",
    "Raw inputs, normalised 0-100 scores (higher is always better) "
    "and weighted contributions."
)

a = get_analysis()

if a.note:
    st.warning(a.note)

s = a.scoring.summary
norm = a.scoring.normalized


# ============================================================
# EXPLANATION - COLLAPSIBLE
# ============================================================

with st.expander("How scores are calculated"):
    st.markdown(
        """
        The system converts evaluation inputs into normalised scores
        on a 0-100 scale, where higher scores always represent better
        performance.

        **Evaluation process:**

        1. Raw initiative inputs are collected.
        2. Subcriteria are normalised according to their evaluation
           direction (benefit or cost).
        3. Normalised subcriteria are combined using their assigned
           weights to calculate each main criterion score.
        4. Main criterion scores are multiplied by their active
           criterion weights.
        5. Weighted contributions are combined to produce the
           final initiative score.

        **Important:** Lower-risk and lower-cost performance indicators
        are treated in the appropriate direction so that higher
        normalised scores consistently indicate better performance.
        """
    )


# ============================================================
# NAVIGATION TABS
# ============================================================

tab1, tab2, tab3 = st.tabs([
    "Single initiative",
    "All initiatives",
    "Contributions"
])


# ============================================================
# TAB 1 - SINGLE INITIATIVE
# ============================================================

with tab1:

    labels = dict(zip(s[COL_ID], s[COL_NAME]))

    pick = st.selectbox(
        "Select initiative",
        list(labels),
        format_func=lambda i: f"{i} - {labels[i]}"
    )

    raw = ss.df[ss.df[COL_ID] == pick].iloc[0]
    row = s[s[COL_ID] == pick].iloc[0]
    nrow = norm[norm[COL_ID] == pick].iloc[0]

    st.markdown(
        f"**{raw[COL_NAME]}** "
        f"({raw[COL_FUNC] or 'No function given'})"
    )

    if raw[COL_DESC]:
        st.caption(raw[COL_DESC])

    # KPI CARDS

    ui.kpi_cards([
        (
            "Final Score",
            f"{row['Final Score']:.1f}",
            f"Rank {int(row['Rank'])} of {len(s)}"
        ),
        (
            "Estimated Cost",
            f"{raw[COL_COST]:,.1f}",
            f"{raw[COL_COST] / a.budget * 100:,.0f}% of budget"
            if a.budget > 0 else "-"
        ),
        (
            "Expected ROI",
            f"{raw[COL_ROI]:g}%",
            "Expected return"
        ),
        (
            "NPV / Payback",
            f"{raw[COL_NPV]:g} / {raw[COL_PAYBACK]:g}y",
            "Shorter payback is better"
        )
    ])

    st.divider()

    # CONTRIBUTION CHART

    contrib = [
        row[f"{c} (contribution)"]
        for c in CRITERIA_NAMES
    ]

    fig = go.Figure(
        go.Bar(
            x=CRITERIA_NAMES,
            y=contrib,
            marker_color=ui.CRIT_COLORS,
            text=[f"{v:.1f}" for v in contrib],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Weighted Contribution: %{y:.2f} points"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title=(
            f"Contribution to Final Score "
            f"({row['Final Score']:.1f} / 100)"
        ),
        yaxis_title="Weighted Contribution (points)",
        xaxis_title="Evaluation Criteria",
        showlegend=False,
        margin=dict(t=70, b=50)
    )

    ui.chart(fig, 380)

    # DETAILED INPUT AND NORMALISATION TABLE

    st.subheader("Input Values & Normalised Scores")

    det = []

    for c, subs in CRITERIA.items():

        for s_ in subs:

            det.append({
                "Criterion": c,
                "Subcriterion": s_.label,
                "Input Value": raw[s_.label],
                "Direction": (
                    "Benefit"
                    if s_.direction == "benefit"
                    else "Cost (Inverted)"
                ),
                "Normalised Score (0-100)": nrow[s_.label]
            })

    ui.table(pd.DataFrame(det))

    st.caption(
        "Higher normalised scores indicate better performance. "
        "Cost-oriented criteria are inverted where applicable."
    )


# ============================================================
# TAB 2 - ALL INITIATIVES
# ============================================================

with tab2:

    st.subheader("Criterion Scores and Final Ranking")

    ui.table(
        s[
            [COL_ID, COL_NAME, COL_COST]
            + CRITERIA_NAMES
            + ["Final Score", "Rank"]
        ].sort_values("Rank")
    )

    # OPTIONAL HEATMAP

    with st.expander("Detailed Subcriteria Heatmap"):

        st.caption(
            "Compare the normalised performance of all initiatives "
            "across individual evaluation subcriteria."
        )

        z = norm.drop(columns=[COL_ID, COL_NAME])

        fig = go.Figure(
            go.Heatmap(
                z=z.values,
                x=list(z.columns),
                y=norm[COL_NAME],
                colorscale="Blues",
                zmin=0,
                zmax=100,
                colorbar=dict(title="Score (0-100)"),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "%{x}<br>"
                    "Normalised Score: %{z:.1f}"
                    "<extra></extra>"
                )
            )
        )

        fig.update_layout(
            title="Normalised Subcriteria Performance",
            yaxis=dict(autorange="reversed"),
            xaxis=dict(tickangle=-45),
            margin=dict(b=140, t=70)
        )

        ui.chart(fig, 560)

        st.caption(
            "Darker cells indicate better performance after "
            "normalisation. Lower risk appears as a higher score."
        )


# ============================================================
# TAB 3 - CONTRIBUTIONS
# ============================================================

with tab3:

    st.subheader("Weighted Criterion Contributions")

    st.caption(
        "This chart shows how each evaluation criterion contributes "
        "to the final score of every strategic initiative."
    )

    d = s.sort_values("Final Score")

    fig = go.Figure()

    for c, col in zip(CRITERIA_NAMES, ui.CRIT_COLORS):

        fig.add_bar(
            name=c,
            y=d[COL_NAME],
            x=d[f"{c} (contribution)"],
            orientation="h",
            marker_color=col,
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"{c}: "
                "%{x:.2f} points"
                "<extra></extra>"
            )
        )

    fig.update_layout(
        barmode="stack",
        title=(
            "Weighted Criterion Contributions "
            "to Each Initiative's Final Score"
        ),
        xaxis_title="Final Score (points)",
        yaxis_title="Strategic Initiatives",
        legend_title="Evaluation Criteria",
        margin=dict(l=180, t=70)
    )

    ui.chart(fig, 560)

    st.subheader("Contribution Breakdown")

    ui.table(
        s[
            [COL_NAME]
            + [
                f"{c} (contribution)"
                for c in CRITERIA_NAMES
            ]
            + ["Final Score"]
        ].sort_values("Final Score", ascending=False)
    )
