import streamlit as st
import plotly.graph_objects as go

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core import ui

init_state()
require_data()
ui.page_header("Executive Dashboard", "Summary of the current analysis - all figures are calculated live from your inputs.")

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
top = s.iloc[0]
ui.kpi_cards([
    ("Total initiatives", len(s), f"{s['Rank'].nunique()} distinct ranks"),
    ("Available budget", f"{a.budget:,.1f}", "decision constraint"),
    ("Total proposed investment", f"{total_cost:,.1f}", f"{total_cost / a.budget * 100:,.0f}% of budget" if a.budget > 0 else "-"),
    ("Recommended investment", f"{opt.total_cost:,.1f}", f"remaining {opt.remaining:,.1f}"),
    ("Budget utilisation", f"{opt.utilization:.1f}%", opt.method),
    ("Highest-ranked initiative", top[COL_NAME], f"score {top['Final Score']:.1f} / 100"),
    ("Selected initiatives", f"{opt.n_selected} of {len(s)}", "in the optimal portfolio"),
    ("Portfolio score", f"{opt.total_value:,.1f}", f"average {opt.average_score:.1f} per initiative"),
])

if opt.status == "empty":
    st.warning(opt.message)

t = opt.table.copy()
t["Decision"] = t["Selected"].map({True: "Selected", False: "Not selected"})
t = t.sort_values("Final Score")
c1, c2 = st.columns([3, 2])
with c1:
    fig = go.Figure(go.Bar(x=t["Final Score"], y=t[COL_NAME], orientation="h",
                           marker_color=[ui.NAVY if x else ui.GREY for x in t["Selected"]],
                           text=t["Final Score"].round(1), textposition="outside"))
    fig.update_layout(title="Initiative scores (navy = selected in optimal portfolio)", xaxis=dict(range=[0, 100], title="Final score (0-100)"))
    ui.chart(fig, 520)
with c2:
    fig = go.Figure()
    fig.add_bar(name="Invested", x=["Budget"], y=[opt.total_cost], marker_color=ui.NAVY)
    fig.add_bar(name="Remaining", x=["Budget"], y=[max(opt.remaining, 0)], marker_color=ui.LIGHT)
    fig.add_bar(name="Total proposed", x=["Proposed"], y=[total_cost], marker_color=ui.GREY)
    fig.update_layout(barmode="stack", title="Budget vs proposed investment")
    fig.add_hline(y=a.budget, line_dash="dash", line_color=ui.RED, annotation_text="Budget")
    ui.chart(fig, 300)
    sel = opt.table[opt.table["Selected"]]
    if len(sel):
        avg = [sel[f"{c} (contribution)"].mean() for c in CRITERIA_NAMES]
        fig = go.Figure(go.Bar(x=CRITERIA_NAMES, y=avg, marker_color=ui.CRIT_COLORS))
        fig.update_layout(title="Average criterion contribution - selected portfolio", yaxis_title="points")
        ui.chart(fig, 300)

fig = go.Figure(go.Scatter(
    x=t[COL_COST], y=t["Final Score"], mode="markers+text", text=t[COL_NAME].str.slice(0, 18),
    textposition="top center", marker=dict(size=14, color=[ui.NAVY if x else ui.GREY for x in t["Selected"]])))
if a.budget > 0:
    fig.add_vline(x=a.budget, line_dash="dash", line_color=ui.RED, annotation_text="Total budget")
fig.update_layout(title="Cost vs score (value for money)", xaxis_title="Estimated cost", yaxis_title="Final score")
ui.chart(fig, 430)

st.subheader("Summary insights")
gain = opt.total_value - a.greedy.total_value
ins = [f"**{top[COL_NAME]}** has the highest score ({top['Final Score']:.1f}).",
       f"The optimal portfolio funds **{opt.n_selected}** initiatives using **{opt.utilization:.1f}%** of the budget.",
       f"Selecting purely by rank would give a portfolio value of {a.greedy.total_value:,.1f}; optimisation gives {opt.total_value:,.1f} ({gain:+,.1f})."]
missed = s[(s["Rank"] <= 5) & (~s[COL_ID].isin(opt.selected_ids))]
if len(missed):
    ins.append("Top-5 initiatives **not** funded because of the budget: " + ", ".join(missed[COL_NAME]) + ".")
if total_cost <= a.budget:
    ins.append("The budget covers every proposed initiative - the constraint is not binding.")
for i in ins:
    st.markdown(f"- {i}")
