
import streamlit as st
import plotly.graph_objects as go

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core import ui

init_state()
require_data()

ui.page_header(
    "Executive Dashboard",
    "Summary of the current analysis - all figures are calculated live from your inputs."
)

a = get_analysis()
ss = st.session_state
s = a.scoring.summary
opt = a.optimal

if opt.status == "invalid":
    st.error(opt.message)
    st.stop()

if a.note:
    st.warning(a.note)

total_cost = float(s[COL_COST].sum())
top = s.sort_values("Rank").iloc[0]

# ============================================================
# 1. EXECUTIVE KPI CARDS
# ============================================================

ui.kpi_cards([
    ("Available Budget", f"{a.budget:,.1f}", "Total available resources"),
    ("Recommended Investment", f"{opt.total_cost:,.1f}",
     f"Remaining: {opt.remaining:,.1f}"),
    ("Selected Initiatives", f"{opt.n_selected} of {len(s)}",
     "Recommended portfolio"),
    ("Budget Utilisation", f"{opt.utilization:.1f}%",
     opt.method),

    ("Total Initiatives", len(s),
     f"{s['Rank'].nunique()} distinct ranks"),
    ("Total Proposed Investment", f"{total_cost:,.1f}",
     f"{total_cost / a.budget * 100:,.1f}% of budget"
     if a.budget > 0 else "-"),
    ("Highest-Ranked Initiative", top[COL_NAME],
     f"Score: {top['Final Score']:.1f} / 100"),
    ("Total Portfolio Score", f"{opt.total_value:,.1f}",
     f"Average: {opt.average_score:.1f} points per initiative"),
])

if opt.status == "empty":
    st.warning(opt.message)

# ============================================================
# 2. EXECUTIVE SUMMARY INSIGHTS
# ============================================================

st.subheader("Executive Decision Summary")

gain = opt.total_value - a.greedy.total_value

ins = [
    f"**{top[COL_NAME]}** is the highest-ranked initiative "
    f"with a score of **{top['Final Score']:.1f}/100**.",

    f"The recommended portfolio includes **{opt.n_selected} initiatives**, "
    f"requiring an investment of **{opt.total_cost:,.1f}**, "
    f"equivalent to **{opt.utilization:.1f}%** of the available budget.",

    f"The recommended portfolio achieves a total score of "
    f"**{opt.total_value:,.1f} points**, compared with "
    f"**{a.greedy.total_value:,.1f} points** under highest-ranking-first selection "
    f"({gain:+,.1f} points difference)."
]

missed = s[
    (s["Rank"] <= 5) &
    (~s[COL_ID].isin(opt.selected_ids))
]

if len(missed):
    missed_names = ", ".join(missed[COL_NAME].astype(str))
    ins.append(
        f"**Budget trade-off:** The following top-5 ranked initiatives "
        f"were not selected under the available budget: {missed_names}."
    )

if total_cost <= a.budget:
    ins.append(
        "**Budget observation:** The available budget is sufficient "
        "to fund all proposed initiatives."
    )

for insight in ins:
    st.markdown(f"- {insight}")

st.divider()

# ============================================================
# 3. INITIATIVE SCORES AND BUDGET ALLOCATION
# ============================================================

st.subheader("Portfolio Performance")

t = opt.table.copy()
t["Decision"] = t["Selected"].map({
    True: "Selected",
    False: "Not selected"
})
t = t.sort_values("Final Score")

c1, c2 = st.columns([3, 2])

with c1:
    fig = go.Figure(
        go.Bar(
            x=t["Final Score"],
            y=t[COL_NAME],
            orientation="h",
            marker_color=[
                ui.NAVY if x else ui.GREY
                for x in t["Selected"]
            ],
            text=t["Final Score"].round(1),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Final Score: %{x:.2f}/100"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title="Initiative Scores",
        xaxis=dict(
            range=[0, 110],
            title="Final Score (0-100)"
        ),
        yaxis_title="Strategic Initiatives",
        showlegend=False
    )

    ui.chart(fig, 520)

with c2:
    fig = go.Figure()

    fig.add_bar(
        name="Invested",
        x=["Budget"],
        y=[opt.total_cost],
        marker_color=ui.NAVY
    )

    fig.add_bar(
        name="Remaining",
        x=["Budget"],
        y=[max(opt.remaining, 0)],
        marker_color=ui.LIGHT
    )

    fig.add_bar(
        name="Total Proposed",
        x=["Proposed"],
        y=[total_cost],
        marker_color=ui.GREY
    )

    fig.update_layout(
        barmode="stack",
        title="Budget vs Proposed Investment",
        yaxis_title="Investment"
    )

    fig.add_hline(
        y=a.budget,
        line_dash="dash",
        line_color=ui.RED,
        annotation_text="Available Budget"
    )

    ui.chart(fig, 300)

    sel = opt.table[opt.table["Selected"]]

    if len(sel):
        avg = [
            sel[f"{c} (contribution)"].mean()
            for c in CRITERIA_NAMES
        ]

        fig = go.Figure(
            go.Bar(
                x=CRITERIA_NAMES,
                y=avg,
                marker_color=ui.CRIT_COLORS,
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Average Contribution: %{y:.2f} points"
                    "<extra></extra>"
                )
            )
        )

        fig.update_layout(
            title="Average Criterion Contribution",
            yaxis_title="Points",
            xaxis_title="Evaluation Criteria"
        )

        ui.chart(fig, 300)

# ============================================================
# 4. COST VS SCORE ANALYSIS
# ============================================================

st.divider()
st.subheader("Cost vs Score Analysis")

max_cost = float(t[COL_COST].max()) if len(t) else 0

fig = go.Figure(
    go.Scatter(
        x=t[COL_COST],
        y=t["Final Score"],
        mode="markers",
        customdata=t[COL_NAME],
        marker=dict(
            size=15,
            color=[
                ui.NAVY if x else ui.GREY
                for x in t["Selected"]
            ],
            line=dict(width=1, color="white"),
            opacity=0.85
        ),
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "Estimated Cost: %{x:,.2f}<br>"
            "Final Score: %{y:.2f}/100"
            "<extra></extra>"
        )
    )
)

fig.update_layout(
    title="Cost vs Score - Initiative Value for Money",
    xaxis=dict(
        title="Estimated Initiative Cost",
        range=[0, max_cost * 1.15 if max_cost > 0 else 1]
    ),
    yaxis=dict(
        title="Final Score (0-100)",
        range=[0, 105]
    ),
    showlegend=False,
    annotations=[
        dict(
            text="Navy = Selected | Grey = Not Selected",
            xref="paper",
            yref="paper",
            x=0,
            y=1.12,
            showarrow=False,
            font=dict(size=11)
        )
    ]
)

ui.chart(fig, 430)

st.caption(
    "Note: The chart compares individual initiative costs with their scores. "
    "The available budget is a portfolio-level constraint, not an individual "
    "initiative cost threshold."
)
