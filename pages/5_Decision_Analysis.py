import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core.optimization import explain_decisions
from core import ui

init_state()
require_data()
ui.page_header("Decision Analysis", "Weighted Sum ranking and budget-constrained portfolio optimisation.")
a = get_analysis()
s, opt, gr = a.scoring.summary, a.optimal, a.greedy
if a.note:
    st.warning(a.note)

tab_r, tab_p, tab_c = st.tabs(["Ranking (Weighted Sum Model)", "Portfolio optimisation", "Optimised vs rank-first"])

with tab_r:
    st.latex(r"\text{Final Score}_i=\sum_{c=1}^{5} w_c \times S_{ic}\qquad (S_{ic}\in[0,100])")
    st.caption("Weights in use: " + " | ".join(f"{c}: {a.weights[c] * 100:.1f}%" for c in CRITERIA_NAMES) + f"  (source: {a.source})")
    top = s.iloc[0]
    with st.expander(f"Worked example: {top[COL_NAME]}", expanded=False):
        lines = [f"- {c}: {a.weights[c]:.4f} x {top[c]:.2f} = **{top[f'{c} (contribution)']:.2f}**" for c in CRITERIA_NAMES]
        st.markdown("\n".join(lines) + f"\n\n**Final score = {top['Final Score']:.2f}**")
    ui.table(s[["Rank", COL_ID, COL_NAME, COL_COST] + CRITERIA_NAMES + ["Final Score"]])
    d = s.sort_values("Final Score")
    fig = go.Figure(go.Bar(y=d[COL_NAME], x=d["Final Score"], orientation="h", marker_color=ui.NAVY,
                           text=d["Final Score"].round(1), textposition="outside"))
    fig.update_layout(title="Initiative ranking", xaxis=dict(range=[0, 100], title="Final score"))
    ui.chart(fig, 520)

with tab_p:
    if opt.status == "invalid":
        st.error(opt.message)
        st.stop()
    st.markdown("**Binary optimisation model**")
    st.latex(r"\max \sum_i Score_i\,x_i \quad \text{s.t.}\quad \sum_i Cost_i\,x_i \le B,\quad x_i\in\{0,1\}")
    if opt.status == "empty":
        st.warning(opt.message)
    ui.kpi_cards([("Total selected investment", f"{opt.total_cost:,.2f}", f"budget {a.budget:,.2f}"),
                  ("Remaining budget", f"{opt.remaining:,.2f}", "unspent"),
                  ("Budget utilisation", f"{opt.utilization:.1f}%", opt.method),
                  ("Portfolio value", f"{opt.total_value:,.1f}", f"{opt.n_selected} initiatives selected")])
    assert opt.total_cost <= a.budget + 1e-9
    t = opt.table.sort_values("Final Score", ascending=False)
    cols = [COL_ID, COL_NAME, COL_COST, "Final Score"]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Selected initiatives")
        ui.table(t[t["Selected"]][cols])
    with c2:
        st.subheader("Rejected initiatives")
        ui.table(t[~t["Selected"]][cols])
    st.subheader("Why was each initiative selected or rejected?")
    ex = explain_decisions(s, opt, gr)
    st.dataframe(ex, hide_index=True, **ui.stretch(),
                 column_config={"Explanation": st.column_config.TextColumn(width="large"),
                                "Final Score": st.column_config.NumberColumn(format="%.1f"),
                                "Cost": st.column_config.NumberColumn(format="%.2f")})
    st.caption("A high rank does not guarantee selection: the optimiser maximises the total value of the whole portfolio, not the position of single initiatives.")

with tab_c:
    if opt.status == "invalid":
        st.stop()
    comp = [{"Approach": "Optimised portfolio", "Initiatives": opt.n_selected, "Investment": opt.total_cost,
             "Remaining": opt.remaining, "Utilisation (%)": opt.utilization, "Portfolio value": opt.total_value},
            {"Approach": "Highest-ranking-first", "Initiatives": gr.n_selected, "Investment": gr.total_cost,
             "Remaining": gr.remaining, "Utilisation (%)": gr.utilization, "Portfolio value": gr.total_value}]
    import pandas as pd
    ui.table(pd.DataFrame(comp))
    diff = opt.total_value - gr.total_value
    if diff > 1e-9:
        st.success(f"Optimisation adds **{diff:,.1f}** points of portfolio value compared with funding initiatives strictly in rank order.")
    else:
        st.info("For this budget the rank-first selection happens to be optimal as well.")
    fig = go.Figure()
    fig.add_bar(name="Optimised", x=["Portfolio value", "Investment"], y=[opt.total_value, opt.total_cost], marker_color=ui.NAVY)
    fig.add_bar(name="Highest-ranking-first", x=["Portfolio value", "Investment"], y=[gr.total_value, gr.total_cost], marker_color=ui.GREY)
    fig.update_layout(barmode="group")
    ui.chart(fig, 340)
    only_opt = sorted(set(opt.selected_ids) - set(gr.selected_ids))
    only_gr = sorted(set(gr.selected_ids) - set(opt.selected_ids))
    names = dict(zip(s[COL_ID], s[COL_NAME]))
    st.markdown("**Only in the optimised portfolio:** " + (", ".join(names[i] for i in only_opt) or "-"))
    st.markdown("**Only in the rank-first portfolio:** " + (", ".join(names[i] for i in only_gr) or "-"))
