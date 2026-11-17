import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, WEIGHT_SOURCES, active_weights
from core.schema import CRITERIA, CRITERIA_NAMES, DEFAULT_WEIGHTS, SCORE_DEFINITIONS_BENEFIT, SCORE_DEFINITIONS_RISK
from core.ahp import (ahp, build_matrix, signed_to_value, value_to_signed, saaty_label, most_inconsistent_pair,
                      RANDOM_INDEX, CR_THRESHOLD)
from core import ui

init_state()
ss = st.session_state
ui.page_header("Criteria & Weighting", "Define how important each evaluation criterion is.")

n = len(CRITERIA_NAMES)
PAIRS = [(i, j) for i in range(n) for j in range(i + 1, n)]


def current_matrix():
    judg = {p: signed_to_value(ss.get(f"ahp_{p[0]}_{p[1]}", ss.ahp_judgments.get(p, 0))) for p in PAIRS}
    return build_matrix(n, judg)


def load_default_judgments():
    w = np.array([DEFAULT_WEIGHTS[c] for c in CRITERIA_NAMES])
    for (i, j) in PAIRS:
        k = value_to_signed(w[i] / w[j])
        ss.ahp_judgments[(i, j)] = k
        ss[f"ahp_{i}_{j}"] = k


def reset_judgments():
    for (i, j) in PAIRS:
        ss.ahp_judgments[(i, j)] = 0
        ss[f"ahp_{i}_{j}"] = 0


def apply_ahp():
    r = ahp(current_matrix())
    ss.ahp_weights = {c: float(w) for c, w in zip(CRITERIA_NAMES, r.weights)}
    ss.ahp_cr = r.cr
    ss.weight_source = "AHP"


# ---- weight source ----------------------------------------------------------
st.subheader("Weight source used in the evaluation")
ss.weight_source = st.radio("Active weights", WEIGHT_SOURCES, index=WEIGHT_SOURCES.index(ss.weight_source),
                            horizontal=True,
                            help="Default = illustrative proposed weights. Manual = your own percentages. AHP = derived from pairwise comparisons (apply them in the AHP tab).")
weights, source, note = active_weights()
if note:
    st.warning(note)

tab_h, tab_w, tab_a = st.tabs(["Criteria hierarchy", "Weights (default / manual)", "AHP pairwise comparison"])

with tab_h:
    rows = []
    for c, subs in CRITERIA.items():
        for s_ in subs:
            rows.append({"Criterion": c, "Subcriterion": s_.label,
                         "Type": "Qualitative rating" if s_.kind == "qual" else "Quantitative",
                         "Direction": "Benefit (higher = better)" if s_.direction == "benefit" else "Cost / risk (inverted: lower = better)"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, **ui.stretch())
    st.caption("Budget (Estimated Cost) is **not** a criterion: it is a decision constraint applied in portfolio optimisation.")
    st.markdown("**Score definitions** (all qualitative criteria use the same anchors; for risk and complexity a higher number is worse and is inverted automatically):")
    st.dataframe(pd.DataFrame({"Score": range(1, 6), "Benefit": list(SCORE_DEFINITIONS_BENEFIT.values()),
                               "Risk / complexity": list(SCORE_DEFINITIONS_RISK.values())}),
                 hide_index=True, **ui.stretch())

with tab_w:
    st.write("Enter weights as percentages. The values are used as entered when the source is **Manual**; "
             "they are always rescaled so that the weights used in the calculation sum to exactly 100%.")
    cols = st.columns(n)
    manual = {}
    for col, c in zip(cols, CRITERIA_NAMES):
        k = f"mw_{c}"
        if k not in ss:
            ss[k] = float(ss.manual_weights[c])
        manual[c] = col.number_input(c, min_value=0.0, max_value=100.0, step=1.0, key=k)
    ss.manual_weights = manual
    total = sum(manual.values())
    b1, b2, b3 = st.columns([2, 1, 1])
    if abs(total - 100) < 1e-6:
        b1.markdown(ui.pill(f"Total = {total:.1f}% - OK", "ok"), unsafe_allow_html=True)
    else:
        b1.markdown(ui.pill(f"Total = {total:.1f}% - must be 100%", "bad"), unsafe_allow_html=True)

    def normalise_manual():
        t = sum(ss.manual_weights.values())
        if t > 0:
            for c in CRITERIA_NAMES:
                ss[f"mw_{c}"] = ss.manual_weights[c] / t * 100

    def reset_manual():
        for c in CRITERIA_NAMES:
            ss[f"mw_{c}"] = DEFAULT_WEIGHTS[c] * 100

    b2.button("Normalise to 100%", on_click=normalise_manual, disabled=total <= 0)
    b3.button("Reset to proposed", on_click=reset_manual)
    if total <= 0:
        st.error("At least one weight must be greater than zero.")
    if ss.weight_source != "Manual":
        st.info("Select **Manual** in 'Active weights' above to use these values in the evaluation.")

    fig = go.Figure()
    fig.add_bar(name="Proposed (default)", x=CRITERIA_NAMES, y=[DEFAULT_WEIGHTS[c] * 100 for c in CRITERIA_NAMES], marker_color=ui.LIGHT)
    fig.add_bar(name=f"Active ({source})", x=CRITERIA_NAMES, y=[weights[c] * 100 for c in CRITERIA_NAMES], marker_color=ui.NAVY)
    fig.update_layout(barmode="group", yaxis_title="Weight (%)", title="Criteria weights")
    ui.chart(fig, 340)

    with st.expander("Subcriteria weights inside each criterion (advanced, default = equal)"):
        st.caption("Each criterion score is the weighted mean of its subcriteria; values are rescaled to sum to 100% per criterion.")
        for c, subs in CRITERIA.items():
            cs = st.columns(len(subs))
            vals = {}
            for col, s_ in zip(cs, subs):
                k = f"sw_{c}_{s_.label}"
                if k not in ss:
                    ss[k] = float(ss.sub_weights[c][s_.label] * 100)
                vals[s_.label] = col.number_input(f"{c}: {s_.label}", min_value=0.0, max_value=100.0, step=1.0, key=k)
            t = sum(vals.values())
            if t > 0:
                ss.sub_weights[c] = {k: v / t for k, v in vals.items()}
            else:
                st.error(f"{c}: at least one subcriterion weight must be > 0 (equal weights used instead).")
                ss.sub_weights[c] = {s_.label: 1 / len(subs) for s_ in subs}

with tab_a:
    with st.expander("How the AHP calculation works", expanded=False):
        st.markdown(r"""
1. For every pair of criteria, judge how much more important the first is than the second on **Saaty's 1-9 scale**
   (1 = equal, 3 = moderate, 5 = strong, 7 = very strong, 9 = extreme; 2, 4, 6, 8 are intermediate). The reverse comparison is the reciprocal ($a_{ji}=1/a_{ij}$).
2. The judgements form a positive reciprocal matrix **A**. The priority weights are the **principal right eigenvector** of **A** (normalised to sum 1): $A w = \lambda_{max} w$.
3. Consistency Index: $CI = (\lambda_{max}-n)/(n-1)$.
4. Consistency Ratio: $CR = CI / RI$, where RI is Saaty's Random Index for matrix size *n* (RI = 1.12 for n = 5).
5. If $CR > 0.10$ the judgements are considered too inconsistent and should be revised.
""")
    st.write("For each pair, choose which criterion is more important and by how much. "
             "The slider reads from left (**first** criterion more important) through *equal* to right (**second** more important).")
    options = list(range(8, -9, -1))
    for (i, j) in PAIRS:
        k = f"ahp_{i}_{j}"
        if k not in ss:
            ss[k] = ss.ahp_judgments.get((i, j), 0)

        def fmt(v, a=CRITERIA_NAMES[i], b=CRITERIA_NAMES[j]):
            if v == 0:
                return "1 - Equal importance"
            return f"{abs(v) + 1} - {a if v > 0 else b} ({saaty_label(v).lower()})"

        c1, c2 = st.columns([1, 2])
        c1.markdown(f"**{CRITERIA_NAMES[i]}**  \nvs **{CRITERIA_NAMES[j]}**")
        ss.ahp_judgments[(i, j)] = c2.select_slider("Judgement", options=options, key=k, format_func=fmt,
                                                    label_visibility="collapsed")
    b1, b2, b3 = st.columns(3)
    b1.button("Load judgements consistent with proposed weights", on_click=load_default_judgments)
    b2.button("Reset all to equal importance", on_click=reset_judgments)

    m = current_matrix()
    r = ahp(m)
    st.subheader("Pairwise comparison matrix")
    st.dataframe(pd.DataFrame(m, index=CRITERIA_NAMES, columns=CRITERIA_NAMES).round(3), **ui.stretch())

    st.subheader("Priority weights")
    c1, c2 = st.columns([2, 3])
    wdf = pd.DataFrame({"Criterion": CRITERIA_NAMES, "AHP weight (%)": r.weights * 100})
    with c1:
        ui.table(wdf)
    with c2:
        fig = go.Figure(go.Bar(x=wdf["Criterion"], y=wdf["AHP weight (%)"], marker_color=ui.NAVY,
                               text=wdf["AHP weight (%)"].round(1), textposition="outside"))
        fig.update_layout(yaxis_title="Weight (%)")
        ui.chart(fig, 300)

    st.subheader("Consistency check")
    ui.kpi_cards([("lambda max", f"{r.lambda_max:.4f}", f"n = {n}"),
                  ("Consistency Index (CI)", f"{r.ci:.4f}", f"(lambda max - {n}) / {n - 1}"),
                  ("Random Index (RI)", f"{r.ri:.2f}", "Saaty, n = 5"),
                  ("Consistency Ratio (CR)", f"{r.cr:.4f}", "threshold 0.10")])
    if r.consistent:
        st.success(f"CR = {r.cr:.3f} <= {CR_THRESHOLD:.2f}: the judgements are acceptably consistent.")
    else:
        st.warning(f"CR = {r.cr:.3f} exceeds {CR_THRESHOLD:.2f}: the judgements are inconsistent. Please revise them.")
        i, j, given, implied = most_inconsistent_pair(m)
        st.info(f"Suggestion: reconsider **{CRITERIA_NAMES[i]} vs {CRITERIA_NAMES[j]}** (currently {given:.2f}); "
                f"the other judgements imply about {implied:.2f}.")
    override = False
    if not r.consistent:
        override = st.checkbox("Apply these weights anyway (not recommended)")
    st.button("Apply AHP weights to the evaluation", type="primary", on_click=apply_ahp,
              disabled=(not r.consistent and not override))
    if ss.ahp_weights:
        st.caption(f"AHP weights currently stored (CR = {ss.ahp_cr:.3f}). Select **AHP** as the active source above to use them.")
