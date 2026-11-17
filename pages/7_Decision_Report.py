import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.report import assemble_report, build_excel_report, build_pdf_report
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core import ui

init_state()
require_data()
ss = st.session_state
ui.page_header("Decision Report", "A downloadable report built from the current inputs and results.")
a = get_analysis()
if a.optimal.status == "invalid":
    st.error(a.optimal.message)
    st.stop()
if a.note:
    st.warning(a.note)

try:
    with st.spinner("Assembling report from current results..."):
        ctx = assemble_report(ss.df, a.weights, a.source, ss.sub_weights, ss.scale_max, a.budget, ss.scenarios or None)
        xlsx = build_excel_report(ctx)
        pdf = build_pdf_report(ctx)
except Exception as e:
    st.error(f"The report could not be generated: {e}")
    st.stop()

c1, c2 = st.columns(2)
c1.download_button("Download report (PDF)", pdf, "decision_report.pdf", "application/pdf", type="primary")
c2.download_button("Download report (Excel)", xlsx, "decision_report.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.subheader("1. Executive summary")
for t in ctx["summary"]:
    st.markdown(f"- {t}")
st.subheader("2. Evaluation methodology")
for t in ctx["methodology"]:
    st.markdown(f"- {t}")
st.subheader(f"3. Criteria weights ({ctx['weight_source']})")
ui.table(__import__("pandas").DataFrame({"Criterion": CRITERIA_NAMES, "Weight (%)": [ctx["weights"][c] * 100 for c in CRITERIA_NAMES]}))
st.subheader("4. Initiative ranking")
ui.table(ctx["scores"][["Rank", COL_ID, COL_NAME, COL_COST, "Final Score"]])
st.subheader("5. Recommended portfolio and budget allocation")
ui.table(ctx["selected"][[COL_ID, COL_NAME, COL_COST, "Final Score"]])
o = ctx["optimal"]
st.markdown(f"Budget **{ctx['budget']:,.2f}** | invested **{o.total_cost:,.2f}** ({o.utilization:.1f}%) | remaining **{o.remaining:,.2f}** | portfolio value **{o.total_value:,.1f}**")
st.subheader("6. Scenario comparisons")
ui.table(ctx["scenario_summary"])
st.subheader("7. Sensitivity findings")
for t in ctx["sensitivity_findings"]:
    st.markdown(f"- {t}")
ui.table(ctx["influence"])
st.subheader("8. Key assumptions")
for t in ctx["assumptions"]:
    st.markdown(f"- {t}")
st.subheader("9. Limitations")
for t in ctx["limitations"]:
    st.markdown(f"- {t}")
