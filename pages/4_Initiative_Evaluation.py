import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, COL_FUNC, COL_DESC, COL_ROI, COL_NPV, COL_PAYBACK, CRITERIA, CRITERIA_NAMES
from core import ui

init_state()
require_data()
ss = st.session_state
ui.page_header("Initiative Evaluation", "Raw inputs, normalised 0-100 scores (higher is always better) and weighted contributions.")
a = get_analysis()
if a.note:
    st.warning(a.note)
s, norm = a.scoring.summary, a.scoring.normalized

st.info("**Normalisation.** Ratings (1-N): benefit = (x-1)/(N-1)x100; risk/complexity = (N-x)/(N-1)x100. "
        "ROI and NPV: min-max, higher better. Payback: min-max inverted, shorter better. "
        "Criterion score = mean of its subcriteria; contribution = weight x criterion score; "
        "**final score = sum of contributions (0-100)**.")

tab1, tab2, tab3 = st.tabs(["Single initiative", "All initiatives", "Contributions"])

with tab1:
    labels = dict(zip(s[COL_ID], s[COL_NAME]))
    pick = st.selectbox("Initiative", list(labels), format_func=lambda i: f"{i} - {labels[i]}")
    raw = ss.df[ss.df[COL_ID] == pick].iloc[0]
    row = s[s[COL_ID] == pick].iloc[0]
    nrow = norm[norm[COL_ID] == pick].iloc[0]
    st.markdown(f"**{raw[COL_NAME]}**  ({raw[COL_FUNC] or 'no function given'})")
    if raw[COL_DESC]:
        st.caption(raw[COL_DESC])
    ui.kpi_cards([("Final score", f"{row['Final Score']:.1f}", f"rank {int(row['Rank'])} of {len(s)}"),
                  ("Estimated cost", f"{raw[COL_COST]:,.1f}", f"{raw[COL_COST] / a.budget * 100:,.0f}% of budget" if a.budget > 0 else "-"),
                  ("Expected ROI", f"{raw[COL_ROI]:g}%", "benefit"),
                  ("NPV / Payback", f"{raw[COL_NPV]:g} / {raw[COL_PAYBACK]:g}y", "payback: shorter is better")])
    c1, c2 = st.columns(2)
    with c1:
        vals = [row[c] for c in CRITERIA_NAMES]
        fig = go.Figure(go.Scatterpolar(r=vals + vals[:1], theta=CRITERIA_NAMES + CRITERIA_NAMES[:1], fill="toself",
                                        line_color=ui.NAVY, name=raw[COL_NAME]))
        fig.update_layout(title="Criterion scores (0-100)", polar=dict(radialaxis=dict(range=[0, 100])), showlegend=False)
        ui.chart(fig, 380)
    with c2:
        contrib = [row[f"{c} (contribution)"] for c in CRITERIA_NAMES]
        fig = go.Figure(go.Bar(x=CRITERIA_NAMES, y=contrib, marker_color=ui.CRIT_COLORS, text=[f"{v:.1f}" for v in contrib], textposition="outside"))
        fig.update_layout(title=f"Contribution to the final score ({row['Final Score']:.1f})", yaxis_title="points")
        ui.chart(fig, 380)
    import pandas as pd
    det = []
    for c, subs in CRITERIA.items():
        for s_ in subs:
            det.append({"Criterion": c, "Subcriterion": s_.label, "Input value": raw[s_.label],
                        "Direction": "benefit" if s_.direction == "benefit" else "cost (inverted)",
                        "Normalised (0-100)": nrow[s_.label]})
    ui.table(pd.DataFrame(det))

with tab2:
    st.subheader("Criterion scores and final score")
    ui.table(s[[COL_ID, COL_NAME, COL_COST] + CRITERIA_NAMES + ["Final Score", "Rank"]])
    st.subheader("Normalised subcriteria heat map")
    z = norm.drop(columns=[COL_ID, COL_NAME])
    fig = go.Figure(go.Heatmap(z=z.values, x=list(z.columns), y=norm[COL_NAME], colorscale="Blues", zmin=0, zmax=100,
                               colorbar=dict(title="0-100")))
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(tickangle=-45))
    ui.chart(fig, 560)
    st.caption("Darker = better performance after normalisation (low risk appears dark).")

with tab3:
    d = s.sort_values("Final Score")
    fig = go.Figure()
    for c, col in zip(CRITERIA_NAMES, ui.CRIT_COLORS):
        fig.add_bar(name=c, y=d[COL_NAME], x=d[f"{c} (contribution)"], orientation="h", marker_color=col)
    fig.update_layout(barmode="stack", title="Weighted criterion contributions to each initiative's final score", xaxis_title="Final score (points)")
    ui.chart(fig, 560)
    ui.table(s[[COL_NAME] + [f"{c} (contribution)" for c in CRITERIA_NAMES] + ["Final Score"]])
