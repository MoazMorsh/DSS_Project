"""Entry point:  streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Strategic Intelligence & Decision Support",
                   page_icon=":material/insights:", layout="wide",
                   initial_sidebar_state="expanded")

from core.state import init_state, active_weights
from core import ui


def home():
    init_state()
    ss = st.session_state
    ui.page_header("Strategic Initiative Prioritization and Resource Allocation Decision Support System",
                   "A Multi-Criteria Decision Analysis Approach for Corporate Strategic Planning")
    st.info("This system **supports** managerial judgement; it never replaces it. "
            "The bundled dataset is illustrative and entirely fictional.")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("How to use the platform")
        st.markdown("""
1. **Data Management** - load the sample, upload your own Excel/CSV, or edit initiatives.
2. **Criteria & Weighting** - keep the proposed weights, enter your own, or derive them with **AHP**.
3. **Initiative Evaluation** - inspect normalised scores and criterion contributions.
4. **Decision Analysis** - ranking (Weighted Sum Model) and the **budget-constrained optimal portfolio**.
5. **Scenario & Sensitivity** - compare Base / Growth / Risk-averse scenarios and test ranking stability.
6. **Decision Report** - download the full report as Excel or PDF.

Set the **available budget** in the sidebar at any time - every page recalculates.
""")
    with c2:
        st.subheader("Models used")
        st.markdown("""
| Model | Role |
|---|---|
| AHP | criteria weights + consistency check |
| Weighted Sum Model | score 0-100 and rank |
| Binary optimisation | best portfolio within budget |
| Scenario analysis | alternative budgets / weights |
| Sensitivity analysis | stability of the ranking |
""")
    weights, source, note = active_weights()
    st.subheader("Current session")
    ui.kpi_cards([("Initiatives loaded", len(ss.df) if ss.df is not None else 0, ss.data_source),
                  ("Available budget", f"{ss.budget:,.1f}", "set in the sidebar"),
                  ("Weights in use", source, "see Criteria & Weighting"),
                  ("Rating scale", f"1 - {ss.scale_max}", "qualitative criteria")])
    st.caption("Methodology, assumptions, limitations and references: see README.md and docs/METHODOLOGY.md.")


init_state()
ui.inject_css()
pages = [
    st.Page(home, title="Home", icon=":material/home:", url_path="home", default=True),
    st.Page("pages/1_Executive_Dashboard.py", title="Executive Dashboard", icon=":material/dashboard:"),
    st.Page("pages/2_Data_Management.py", title="Data Management", icon=":material/database:"),
    st.Page("pages/3_Criteria_Weighting.py", title="Criteria & Weighting", icon=":material/balance:"),
    st.Page("pages/4_Initiative_Evaluation.py", title="Initiative Evaluation", icon=":material/fact_check:"),
    st.Page("pages/5_Decision_Analysis.py", title="Decision Analysis", icon=":material/account_tree:"),
    st.Page("pages/6_Scenario_Sensitivity.py", title="Scenario & Sensitivity", icon=":material/tune:"),
    st.Page("pages/7_Decision_Report.py", title="Decision Report", icon=":material/description:"),
]
nav = st.navigation(pages)
ui.brand_bar()
ui.sidebar_status(st.session_state, active_weights()[1])
nav.run()
ui.footer()
