import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, WEIGHT_SOURCES, active_weights
from core.schema import (
    CRITERIA,
    CRITERIA_NAMES,
    DEFAULT_WEIGHTS,
    SCORE_DEFINITIONS_BENEFIT,
    SCORE_DEFINITIONS_RISK,
)
from core.ahp import (
    ahp,
    build_matrix,
    signed_to_value,
    value_to_signed,
    saaty_label,
    most_inconsistent_pair,
    CR_THRESHOLD,
)
from core import ui


# ============================================================
# INITIALIZATION
# ============================================================

init_state()
ss = st.session_state

ui.page_header(
    "Criteria & Weighting",
    "Define how important each evaluation criterion is."
)

n = len(CRITERIA_NAMES)
PAIRS = [(i, j) for i in range(n) for j in range(i + 1, n)]


# ============================================================
# HELPERS
# ============================================================

def current_matrix():
    """Build the AHP matrix from the current pairwise judgements."""
    judgements = {
        pair: signed_to_value(
            ss.get(
                f"ahp_{pair[0]}_{pair[1]}",
                ss.ahp_judgments.get(pair, 0),
            )
        )
        for pair in PAIRS
    }
    return build_matrix(n, judgements)


def load_default_judgments():
    """Load pairwise judgements consistent with proposed default weights."""
    proposed = np.array(
        [DEFAULT_WEIGHTS[c] for c in CRITERIA_NAMES],
        dtype=float,
    )

    for i, j in PAIRS:
        judgement = value_to_signed(proposed[i] / proposed[j])
        ss.ahp_judgments[(i, j)] = judgement
        ss[f"ahp_{i}_{j}"] = judgement


def reset_judgments():
    """Reset all AHP pairwise comparisons to equal importance."""
    for i, j in PAIRS:
        ss.ahp_judgments[(i, j)] = 0
        ss[f"ahp_{i}_{j}"] = 0


def apply_ahp():
    """Save the current consistent AHP weights and activate AHP."""
    result = ahp(current_matrix())

    ss.ahp_weights = {
        criterion: float(weight)
        for criterion, weight in zip(CRITERIA_NAMES, result.weights)
    }
    ss.ahp_cr = float(result.cr)
    ss.weight_source = "AHP"
    ss.ahp_applied = True


def normalise_manual():
    """Rescale current manual inputs to sum to 100%."""
    values = {
        criterion: float(
            ss.get(
                f"mw_{criterion}",
                ss.manual_weights[criterion],
            )
        )
        for criterion in CRITERIA_NAMES
    }
    total = sum(values.values())

    if total > 0:
        for criterion in CRITERIA_NAMES:
            ss[f"mw_{criterion}"] = values[criterion] / total * 100


def reset_manual():
    """Restore proposed default weights in the manual input fields."""
    for criterion in CRITERIA_NAMES:
        ss[f"mw_{criterion}"] = DEFAULT_WEIGHTS[criterion] * 100


def format_weight_source(source_name):
    return source_name if source_name else "Not available"


# ============================================================
# SYNC MANUAL WIDGET VALUES BEFORE READING ACTIVE WEIGHTS
# ============================================================

# This keeps the active-weight summary at the top in sync with the
# latest Manual number_input values after a Streamlit rerun.
if not hasattr(ss, "manual_weights") or ss.manual_weights is None:
    ss.manual_weights = {
        criterion: float(DEFAULT_WEIGHTS[criterion])
        for criterion in CRITERIA_NAMES
    }

for criterion in CRITERIA_NAMES:
    manual_key = f"mw_{criterion}"
    if manual_key in ss:
        ss.manual_weights[criterion] = float(ss[manual_key])


# ============================================================
# ACTIVE WEIGHT SOURCE
# ============================================================

st.subheader("Weight source used in the evaluation")

selected_source = st.radio(
    "Active weights",
    WEIGHT_SOURCES,
    index=(
        WEIGHT_SOURCES.index(ss.weight_source)
        if ss.weight_source in WEIGHT_SOURCES
        else 0
    ),
    horizontal=True,
    help=(
        "Default = proposed weights. Manual = your own percentages. "
        "AHP = weights calculated from pairwise comparisons and activated "
        "using the Apply AHP button."
    ),
)

ss.weight_source = selected_source

weights, source, note = active_weights()

if note:
    st.warning(note)


# ============================================================
# CURRENTLY APPLIED WEIGHTS - EXECUTIVE SUMMARY
# ============================================================

st.subheader("Weights currently applied in the evaluation")
st.caption(
    f"Active source: **{format_weight_source(source)}**. "
    "These are the weights currently used to calculate initiative scores."
)

ui.kpi_cards([
    (
        criterion,
        f"{weights[criterion] * 100:.1f}%",
        "Applied criterion weight",
    )
    for criterion in CRITERIA_NAMES
])

if source == "AHP":
    st.success(
        "AHP weights are active. Changes to pairwise judgements will not "
        "change the evaluation until you apply the updated AHP weights."
    )
elif ss.weight_source == "AHP" and not ss.ahp_weights:
    st.warning(
        "AHP is selected, but no AHP weights have been applied yet. "
        "Complete the pairwise comparison and apply a consistent result."
    )

st.divider()


# ============================================================
# PAGE TABS
# ============================================================

tab_h, tab_w, tab_a = st.tabs([
    "Criteria hierarchy",
    "Weights (default / manual)",
    "AHP pairwise comparison",
])


# ============================================================
# TAB 1 - CRITERIA HIERARCHY
# ============================================================

with tab_h:

    rows = []

    for criterion, subcriteria in CRITERIA.items():
        for subcriterion in subcriteria:
            rows.append({
                "Criterion": criterion,
                "Subcriterion": subcriterion.label,
                "Type": (
                    "Qualitative rating"
                    if subcriterion.kind == "qual"
                    else "Quantitative"
                ),
                "Direction": (
                    "Benefit (higher = better)"
                    if subcriterion.direction == "benefit"
                    else "Cost / risk (inverted: lower = better)"
                ),
            })

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        **ui.stretch(),
    )

    st.caption(
        "Budget (Estimated Cost) is **not** a criterion. "
        "It is a decision constraint applied in portfolio optimisation."
    )

    st.markdown(
        "**Score definitions** "
        "(all qualitative criteria use the same anchors; for risk and "
        "complexity, a higher raw rating is worse and is inverted automatically):"
    )

    score_definitions = pd.DataFrame({
        "Score": range(1, 6),
        "Benefit": list(SCORE_DEFINITIONS_BENEFIT.values()),
        "Risk / complexity": list(SCORE_DEFINITIONS_RISK.values()),
    })

    st.dataframe(
        score_definitions,
        hide_index=True,
        **ui.stretch(),
    )


# ============================================================
# TAB 2 - DEFAULT / MANUAL WEIGHTS
# ============================================================

with tab_w:

    st.write(
        "Enter weights as percentages. When Manual is active, the system "
        "automatically rescales the entered values so the weights used in "
        "the evaluation sum to exactly 100%. Use **Normalise to 100%** "
        "if you also want to update the input fields themselves."
    )

    cols = st.columns(n)
    manual = {}

    for col, criterion in zip(cols, CRITERIA_NAMES):
        key = f"mw_{criterion}"

        if key not in ss:
            ss[key] = float(ss.manual_weights[criterion] * 100)

        manual[criterion] = col.number_input(
            criterion,
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            key=key,
        )

    ss.manual_weights = manual

    entered_total = sum(manual.values())

    # Show entered total and normalised result separately.
    if entered_total > 0:
        normalised_manual = {
            criterion: manual[criterion] / entered_total * 100
            for criterion in CRITERIA_NAMES
        }
    else:
        normalised_manual = {
            criterion: 0.0
            for criterion in CRITERIA_NAMES
        }

    st.markdown("**Manual weight validation**")

    b1, b2, b3 = st.columns([1, 1, 1])

    b1.metric(
        "Entered total",
        f"{entered_total:.1f}%",
        (
            "Already totals 100%"
            if abs(entered_total - 100) < 1e-6
            else f"{entered_total - 100:+.1f} pp vs 100%"
        ),
    )

    b2.metric(
        "Normalised total",
        "100.0%" if entered_total > 0 else "0.0%",
        "Used for calculation" if entered_total > 0 else "No valid weights",
    )

    b3.metric(
        "Active weight source",
        str(source),
        "Currently used in evaluation",
    )

    if abs(entered_total - 100) < 1e-6:
        st.success(
            f"Manual inputs total {entered_total:.1f}%. "
            "No rescaling is required."
        )
    elif entered_total > 0:
        st.info(
            f"Manual inputs total {entered_total:.1f}%. "
            "The system rescales these values proportionally to 100% "
            "when Manual is the active source."
        )
    else:
        st.error("At least one manual weight must be greater than zero.")

    with st.expander(
        "Preview: entered weights vs normalised weights",
        expanded=entered_total > 0 and abs(entered_total - 100) >= 1e-6,
    ):
        manual_preview = pd.DataFrame({
            "Criterion": CRITERIA_NAMES,
            "Entered Weight (%)": [
                manual[criterion]
                for criterion in CRITERIA_NAMES
            ],
            "Normalised Weight (%)": [
                normalised_manual[criterion]
                for criterion in CRITERIA_NAMES
            ],
        })

        ui.table(manual_preview)

    b1, b2 = st.columns([1, 1])

    b1.button(
        "Normalise inputs to 100%",
        on_click=normalise_manual,
        disabled=entered_total <= 0,
        use_container_width=True,
    )

    b2.button(
        "Reset to proposed weights",
        on_click=reset_manual,
        use_container_width=True,
    )

    if ss.weight_source != "Manual":
        st.info(
            "These are the Manual weight settings. Select **Manual** "
            "under 'Weight source used in the evaluation' above to "
            "use them in the decision model."
        )

    # --------------------------------------------------------
    # PROPOSED VS ACTIVE WEIGHT CHART
    # --------------------------------------------------------

    st.divider()
    st.subheader("Proposed vs Active Criteria Weights")

    weight_chart = go.Figure()

    weight_chart.add_bar(
        name="Proposed (default)",
        x=CRITERIA_NAMES,
        y=[
            DEFAULT_WEIGHTS[criterion] * 100
            for criterion in CRITERIA_NAMES
        ],
        marker_color=ui.LIGHT,
    )

    weight_chart.add_bar(
        name=f"Active ({source})",
        x=CRITERIA_NAMES,
        y=[
            weights[criterion] * 100
            for criterion in CRITERIA_NAMES
        ],
        marker_color=ui.NAVY,
    )

    weight_chart.update_layout(
        barmode="group",
        yaxis_title="Weight (%)",
        title="Proposed vs currently applied weights",
        legend_title="Weight source",
    )

    ui.chart(weight_chart, 340)

    # --------------------------------------------------------
    # SUBCRITERIA WEIGHTS
    # --------------------------------------------------------

    with st.expander(
        "Subcriteria weights inside each criterion (advanced, default = equal)"
    ):
        st.caption(
            "Each criterion score is the weighted mean of its subcriteria. "
            "Subcriteria weights are rescaled to sum to 100% within each "
            "criterion."
        )

        for criterion, subcriteria in CRITERIA.items():

            st.markdown(f"**{criterion}**")

            sub_columns = st.columns(len(subcriteria))
            values = {}

            for col, subcriterion in zip(sub_columns, subcriteria):
                key = f"sw_{criterion}_{subcriterion.label}"

                if key not in ss:
                    ss[key] = float(
                        ss.sub_weights[criterion][subcriterion.label] * 100
                    )

                values[subcriterion.label] = col.number_input(
                    subcriterion.label,
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    key=key,
                )

            sub_total = sum(values.values())

            if sub_total > 0:
                ss.sub_weights[criterion] = {
                    label: value / sub_total
                    for label, value in values.items()
                }
            else:
                st.error(
                    f"{criterion}: at least one subcriterion weight must "
                    "be greater than zero. Equal weights are used instead."
                )

                ss.sub_weights[criterion] = {
                    subcriterion.label: 1 / len(subcriteria)
                    for subcriterion in subcriteria
                }


# ============================================================
# TAB 3 - AHP PAIRWISE COMPARISON
# ============================================================

with tab_a:

    with st.expander(
        "How the AHP calculation works",
        expanded=False,
    ):
        st.markdown(
            r"""
1. For every pair of criteria, judge how much more important the first
   is than the second using **Saaty's 1-9 scale**.

   (1 = equal, 3 = moderate, 5 = strong, 7 = very strong, 9 = extreme;
   2, 4, 6, 8 are intermediate). The reverse comparison is the reciprocal
   (\(a_{ji}=1/a_{ij}\)).

2. The judgements form a positive reciprocal matrix **A**. The priority
   weights are the **principal right eigenvector** of **A**, normalised
   to sum to 1: \(Aw=\lambda_{\max}w\).

3. Consistency Index:
   \(CI=(\lambda_{\max}-n)/(n-1)\).

4. Consistency Ratio:
   \(CR=CI/RI\), where RI is Saaty's Random Index for matrix size \(n\).

5. If \(CR>0.10\), the judgements are considered too inconsistent
   and should be revised.
"""
        )

    st.write(
        "For each pair, choose which criterion is more important and by "
        "how much. The slider reads from left (**first** criterion more "
        "important), through **equal**, to right (**second** criterion "
        "more important)."
    )

    # --------------------------------------------------------
    # AHP ACTIONS - ABOVE THE COMPARISONS
    # --------------------------------------------------------

    action1, action2 = st.columns(2)

    action1.button(
        "Load example (proposed weights)",
        on_click=load_default_judgments,
        use_container_width=True,
        help=(
            "Loads pairwise judgements consistent with the proposed "
            "default criterion weights."
        ),
    )

    action2.button(
        "Reset to equal importance",
        on_click=reset_judgments,
        use_container_width=True,
        help="Sets every pairwise comparison to equal importance (1).",
    )

    st.divider()
    st.subheader("Pairwise Judgements")

    options = list(range(8, -9, -1))

    for i, j in PAIRS:

        key = f"ahp_{i}_{j}"

        if key not in ss:
            ss[key] = ss.ahp_judgments.get((i, j), 0)

        def format_judgement(value, first=CRITERIA_NAMES[i], second=CRITERIA_NAMES[j]):
            if value == 0:
                return "1 - Equal importance"

            more_important = first if value > 0 else second

            return (
                f"{abs(value) + 1} - {more_important} "
                f"({saaty_label(value).lower()})"
            )

        col1, col2 = st.columns([1, 2])

        col1.markdown(
            f"**{CRITERIA_NAMES[i]}**  \nvs **{CRITERIA_NAMES[j]}**"
        )

        judgement = col2.select_slider(
            "Judgement",
            options=options,
            key=key,
            format_func=format_judgement,
            label_visibility="collapsed",
        )

        ss.ahp_judgments[(i, j)] = judgement

    # Calculate the current AHP result after all sliders are read.
    matrix = current_matrix()
    result = ahp(matrix)

    # --------------------------------------------------------
    # PAIRWISE MATRIX - COLLAPSED
    # --------------------------------------------------------

    with st.expander(
        "View pairwise comparison matrix",
        expanded=False,
    ):
        st.caption(
            "The matrix shows the reciprocal comparison values generated "
            "from the judgements above."
        )

        matrix_df = pd.DataFrame(
            matrix,
            index=CRITERIA_NAMES,
            columns=CRITERIA_NAMES,
        ).round(3)

        st.dataframe(
            matrix_df,
            **ui.stretch(),
        )

    # --------------------------------------------------------
    # PRIORITY WEIGHTS - ALWAYS VISIBLE
    # --------------------------------------------------------

    st.divider()
    st.subheader("AHP Priority Weights")

    weight_df = pd.DataFrame({
        "Criterion": CRITERIA_NAMES,
        "AHP Weight (%)": result.weights * 100,
    })

    col1, col2 = st.columns([2, 3])

    with col1:
        ui.table(weight_df)

    with col2:
        fig = go.Figure(
            go.Bar(
                x=weight_df["Criterion"],
                y=weight_df["AHP Weight (%)"],
                marker_color=ui.NAVY,
                text=weight_df["AHP Weight (%)"].round(1),
                textposition="outside",
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "AHP Weight: %{y:.2f}%"
                    "<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title="AHP-Derived Criterion Weights",
            yaxis_title="Weight (%)",
        )

        ui.chart(fig, 300)

    # --------------------------------------------------------
    # CONSISTENCY CHECK - ALWAYS VISIBLE
    # --------------------------------------------------------

    st.divider()
    st.subheader("Consistency Check")

    ui.kpi_cards([
        (
            "Lambda Max",
            f"{result.lambda_max:.4f}",
            f"n = {n}",
        ),
        (
            "Consistency Index (CI)",
            f"{result.ci:.4f}",
            f"(lambda max - {n}) / {n - 1}",
        ),
        (
            "Random Index (RI)",
            f"{result.ri:.2f}",
            "Saaty random index",
        ),
        (
            "Consistency Ratio (CR)",
            f"{result.cr:.4f}",
            f"Threshold: {CR_THRESHOLD:.2f}",
        ),
    ])

    if result.consistent:
        st.success(
            f"CR = {result.cr:.3f} <= {CR_THRESHOLD:.2f}: "
            "the judgements are acceptably consistent."
        )
    else:
        st.warning(
            f"CR = {result.cr:.3f} exceeds {CR_THRESHOLD:.2f}: "
            "the judgements are inconsistent. Please revise them."
        )

        i, j, given, implied = most_inconsistent_pair(matrix)

        st.info(
            f"Suggestion: reconsider **{CRITERIA_NAMES[i]} vs "
            f"{CRITERIA_NAMES[j]}** (currently {given:.2f}); "
            f"the other judgements imply about {implied:.2f}."
        )

    # --------------------------------------------------------
    # APPLY AHP WEIGHTS - ALWAYS VISIBLE
    # --------------------------------------------------------

    override = False

    if not result.consistent:
        override = st.checkbox(
            "Apply these weights anyway (not recommended)",
            key="ahp_override_inconsistent",
        )

    st.button(
        "Apply AHP weights to the evaluation",
        type="primary",
        on_click=apply_ahp,
        disabled=(not result.consistent and not override),
        use_container_width=True,
        help=(
            "Saves the current AHP priority weights and switches "
            "the active evaluation source to AHP."
        ),
    )

    if ss.get("ahp_weights"):
        stored_ahp_weights = pd.DataFrame({
            "Criterion": CRITERIA_NAMES,
            "Stored AHP Weight (%)": [
                ss.ahp_weights[criterion] * 100
                for criterion in CRITERIA_NAMES
            ],
        })

        if source == "AHP":
            st.success(
                f"Stored AHP weights are currently active "
                f"(saved CR = {ss.ahp_cr:.3f})."
            )
        else:
            st.caption(
                f"AHP weights are saved (CR = {ss.ahp_cr:.3f}) "
                "but are not currently active. Select AHP under "
                "'Weight source used in the evaluation' to use them."
            )
