
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core.optimization import explain_decisions
from core import ui


# ============================================================
# INITIALIZATION
# ============================================================

init_state()
require_data()

ui.page_header(
    "Decision Analysis",
    "Weighted Sum ranking and budget-constrained portfolio optimisation."
)

a = get_analysis()

s = a.scoring.summary
opt = a.optimal
gr = a.greedy

if a.note:
    st.warning(a.note)

if opt.status == "invalid":
    st.error(opt.message)
    st.stop()


# ============================================================
# NAVIGATION TABS
# ============================================================

tab_r, tab_p, tab_c = st.tabs([
    "Ranking (Weighted Sum Model)",
    "Portfolio Optimisation",
    "Optimised vs Rank-First"
])


# ============================================================
# TAB 1 - RANKING (WEIGHTED SUM MODEL)
# ============================================================

with tab_r:

    st.subheader("Strategic Initiative Ranking")

    st.latex(
        r"\text{Final Score}_i = "
        r"\sum_{c=1}^{5} w_c \times S_{ic}"
        r"\quad (S_{ic}\in[0,100])"
    )

    st.caption(
        "Weights in use: "
        + " | ".join(
            f"{c}: {a.weights[c] * 100:.1f}%"
            for c in CRITERIA_NAMES
        )
        + f"  (Source: {a.source})"
    )

    # WORKED EXAMPLE

    top = s.sort_values("Rank").iloc[0]

    with st.expander(
        f"Worked example: {top[COL_NAME]}",
        expanded=False
    ):

        lines = [
            f"- {c}: {a.weights[c]:.4f} × "
            f"{top[c]:.2f} = "
            f"**{top[f'{c} (contribution)']:.2f}**"
            for c in CRITERIA_NAMES
        ]

        st.markdown(
            "\n".join(lines)
            + f"\n\n**Final Score = {top['Final Score']:.2f}**"
        )

    # RANKING TABLE

    st.subheader("Ranking Results")

    ranking_columns = [
        "Rank",
        COL_ID,
        COL_NAME,
        "Final Score",
        COL_COST
    ] + CRITERIA_NAMES

    ui.table(
        s[ranking_columns].sort_values("Rank")
    )

    # RANKING CHART

    d = s.sort_values("Final Score", ascending=True)

    fig = go.Figure(
        go.Bar(
            y=d[COL_NAME],
            x=d["Final Score"],
            orientation="h",
            marker_color=ui.NAVY,
            text=d["Final Score"].round(1),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Final Score: %{x:.2f}/100"
                "<extra></extra>"
            )
        )
    )

    fig.update_layout(
        title="Strategic Initiative Ranking",
        xaxis=dict(
            range=[0, 110],
            title="Final Score (0-100)"
        ),
        yaxis_title="Strategic Initiatives",
        showlegend=False
    )

    ui.chart(fig, 520)


# ============================================================
# TAB 2 - PORTFOLIO OPTIMISATION
# ============================================================

with tab_p:

    st.subheader("Budget-Constrained Portfolio Selection")

    st.markdown("**Binary Portfolio Optimisation Model**")

    st.latex(
        r"\max \sum_i Score_i \times x_i"
    )

    st.latex(
        r"\text{Subject to: } "
        r"\sum_i Cost_i \times x_i \leq B"
    )

    st.latex(
        r"x_i \in \{0,1\}"
    )

    if opt.status == "empty":
        st.warning(opt.message)

    # PORTFOLIO KPIs

    ui.kpi_cards([
        (
            "Total Selected Investment",
            f"{opt.total_cost:,.2f}",
            f"Available budget: {a.budget:,.2f}"
        ),
        (
            "Remaining Budget",
            f"{opt.remaining:,.2f}",
            "Unallocated resources"
        ),
        (
            "Budget Utilisation",
            f"{opt.utilization:.1f}%",
            opt.method
        ),
        (
            "Portfolio Value",
            f"{opt.total_value:,.1f}",
            f"{opt.n_selected} initiatives selected"
        )
    ])

    # BUDGET VALIDATION

    assert opt.total_cost <= a.budget + 1e-9

    # SELECTED AND NOT SELECTED INITIATIVES

    t = opt.table.sort_values(
        "Final Score",
        ascending=False
    )

    cols = [
        COL_ID,
        COL_NAME,
        "Final Score",
        COL_COST
    ]

    c1, c2 = st.columns(2)

    with c1:

        st.subheader("Selected Initiatives")

        ui.table(
            t[t["Selected"]][cols]
        )

    with c2:

        st.subheader("Not Selected at This Budget")

        ui.table(
            t[~t["Selected"]][cols]
        )

    # DECISION EXPLANATIONS

    st.divider()

    st.subheader(
        "Why Was Each Initiative Selected or Not Selected?"
    )

    ex = explain_decisions(s, opt, gr)

    st.dataframe(
        ex,
        hide_index=True,
        **ui.stretch(),
        column_config={
            "Explanation": st.column_config.TextColumn(
                width="large"
            ),
            "Final Score": st.column_config.NumberColumn(
                format="%.1f"
            ),
            "Cost": st.column_config.NumberColumn(
                format="%.2f"
            )
        }
    )

    st.caption(
        "A high ranking does not guarantee selection. "
        "The optimisation model maximises the total value "
        "of the entire portfolio under the available budget, "
        "rather than selecting initiatives solely by individual rank."
    )


# ============================================================
# TAB 3 - OPTIMISED VS RANK-FIRST COMPARISON
# ============================================================

with tab_c:

    st.subheader("Portfolio Approach Comparison")

    # COMPARISON TABLE

    comp = [
        {
            "Approach": "Optimised Portfolio",
            "Initiatives": opt.n_selected,
            "Investment": opt.total_cost,
            "Remaining Budget": opt.remaining,
            "Utilisation (%)": opt.utilization,
            "Portfolio Value (Points)": opt.total_value
        },
        {
            "Approach": "Highest-Ranking-First",
            "Initiatives": gr.n_selected,
            "Investment": gr.total_cost,
            "Remaining Budget": gr.remaining,
            "Utilisation (%)": gr.utilization,
            "Portfolio Value (Points)": gr.total_value
        }
    ]

    ui.table(
        pd.DataFrame(comp)
    )

    # PERFORMANCE DIFFERENCE

    diff = opt.total_value - gr.total_value

    if diff > 1e-9:

        st.success(
            f"Optimisation adds **{diff:,.1f} points** "
            "of portfolio value compared with funding "
            "initiatives strictly in ranking order."
        )

    elif diff < -1e-9:

        st.warning(
            f"The rank-first approach achieves "
            f"{abs(diff):,.1f} more portfolio points "
            "for the current inputs."
        )

    else:

        st.info(
            "For this budget, the rank-first selection "
            "happens to be optimal as well."
        )

    # PORTFOLIO VALUE COMPARISON
    # Investment is intentionally excluded from this chart
    # because it uses a different measurement unit.

    st.subheader("Portfolio Value Comparison")

    fig = go.Figure()

    fig.add_bar(
        name="Optimised Portfolio",
        x=["Portfolio Score"],
        y=[opt.total_value],
        marker_color=ui.NAVY,
        text=[f"{opt.total_value:,.1f}"],
        textposition="outside",
        hovertemplate=(
            "Optimised Portfolio<br>"
            "Portfolio Value: %{y:,.1f} points"
            "<extra></extra>"
        )
    )

    fig.add_bar(
        name="Highest-Ranking-First",
        x=["Portfolio Score"],
        y=[gr.total_value],
        marker_color=ui.GREY,
        text=[f"{gr.total_value:,.1f}"],
        textposition="outside",
        hovertemplate=(
            "Highest-Ranking-First<br>"
            "Portfolio Value: %{y:,.1f} points"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        barmode="group",
        title="Total Strategic Value of Selected Portfolios",
        yaxis_title="Portfolio Score (Points)",
        xaxis_title="Comparison",
        showlegend=True
    )

    ui.chart(fig, 380)

    st.caption(
        "Portfolio value represents the sum of the weighted "
        "initiative scores. Investment costs are presented "
        "separately in the comparison table above."
    )

    # PORTFOLIO DIFFERENCES

    st.divider()

    st.subheader("Portfolio Composition Differences")

    only_opt = sorted(
        set(opt.selected_ids) - set(gr.selected_ids)
    )

    only_gr = sorted(
        set(gr.selected_ids) - set(opt.selected_ids)
    )

    names = dict(
        zip(s[COL_ID], s[COL_NAME])
    )

    st.markdown(
        "**Only in the Optimised Portfolio:** "
        + (
            ", ".join(names[i] for i in only_opt)
            if only_opt else "-"
        )
    )

    st.markdown(
        "**Only in the Highest-Ranking-First Portfolio:** "
        + (
            ", ".join(names[i] for i in only_gr)
            if only_gr else "-"
        )
    )
