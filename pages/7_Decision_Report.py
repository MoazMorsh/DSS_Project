"""Standalone Decision Report page.

Copy this entire file to pages/7_Decision_Report.py.
The report-generation functions are embedded here, so core/report.py does not
need to be replaced for this page to work.
"""

# Embedded report engine: assembly, Excel export and PDF export.
from __future__ import annotations

import io
from datetime import date
from numbers import Real

import pandas as pd

from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core.weighted_scoring import compute_scores, normalize_weights
from core.optimization import optimize_portfolio, greedy_by_rank, explain_decisions
from core.scenario_analysis import run_scenario, compare_scenarios, default_scenarios
from core.sensitivity_analysis import one_at_a_time

METHODOLOGY = [
    "Criteria weights are obtained from the selected source: proposed defaults, user-entered manual weights, or AHP pairwise comparisons. AHP derives priorities from the principal eigenvector and checks consistency using the Consistency Ratio (CR <= 0.10).",
    "Each subcriterion is normalised to a 0-100 scale where higher is always better. Qualitative ratings use linear rescaling; ROI, NPV and Payback use min-max scaling across the evaluated initiatives. Risk, complexity and payback are cost-type measures and are inverted.",
    "The Weighted Sum Model calculates each final score as the sum of criterion weight multiplied by the corresponding criterion score. Final scores are on a 0-100 scale. Subcriteria are equally weighted within each criterion unless the user changes those weights.",
    "Portfolio selection uses binary 0-1 optimisation to maximise the sum of selected initiative scores subject to total estimated cost not exceeding the available budget. Budget is a constraint, not a scoring criterion.",
    "Scenario analysis recalculates scores and portfolio selection under each scenario's budget, criterion weights, cost multiplier and exclusions. Sensitivity analysis changes criterion weights one at a time and recalculates initiative rankings.",
    "Scenario portfolio values are scenario-specific objective values. When budgets, weights, cost multipliers or included initiatives differ, raw portfolio values should not be interpreted as a like-for-like performance comparison. The optimisation gain versus highest-ranking-first is a within-scenario benchmark.",
]

BASE_ASSUMPTIONS = [
    "Criterion scores are additive and compensatory: a weakness in one criterion can be offset by strength in another.",
    "Initiative costs are treated as known point estimates; initiatives are independent, indivisible and have no interdependencies.",
    "The budget applies to one planning period; costs and NPV are assumed to use the same currency unit.",
    "Qualitative ratings reflect the judgement of the evaluators who entered them.",
    "Min-max normalisation is relative to the set of initiatives evaluated; adding or removing initiatives can change normalised scores.",
]

LIMITATIONS = [
    "The system supports, and does not replace, managerial judgement; outputs are decision aids, not decisions.",
    "Results depend on input quality and selected weights; AHP pairwise judgements are subjective.",
    "The model does not currently represent synergies, dependencies, mandatory projects, multi-period budgets or probability distributions for uncertain inputs.",
    "This is a functional academic prototype. It has not been empirically validated against real organisational outcomes, and no claim is made that it improves corporate performance.",
    "Session data is temporary and may be lost when the browser session ends. Download the report and data exports to retain a record.",
]


def _is_illustrative_source(data_source: str | None) -> bool:
    return "illustrative" in str(data_source or "").lower() or "fictional" in str(data_source or "").lower()


def _scenario_assumptions(results: dict) -> pd.DataFrame:
    rows = []
    for name, result in results.items():
        scenario = result.scenario
        total = sum(float(scenario.weights[c]) for c in CRITERIA_NAMES)
        weights_text = " | ".join(
            f"{c}: {float(scenario.weights[c]) / total * 100:.1f}%"
            for c in CRITERIA_NAMES
        )
        rows.append({
            "Scenario": name,
            "Budget": float(scenario.budget),
            "Cost multiplier": float(scenario.cost_multiplier),
            "Criteria weights": weights_text,
            "Excluded initiatives": ", ".join(map(str, scenario.excluded_ids)) or "None",
            "Description": scenario.description or "-",
        })
    return pd.DataFrame(rows)


def _scenario_warnings(scenarios: dict | None, current_weights: dict, budget: float) -> list[str]:
    """Flag a saved Base scenario that no longer matches current app inputs."""
    if not scenarios or "Base" not in scenarios:
        return []

    base = scenarios["Base"]
    warnings = []
    if abs(float(base.budget) - float(budget)) > 1e-8:
        warnings.append(
            f"The saved Base scenario budget ({base.budget:,.2f}) differs from the current application budget ({budget:,.2f})."
        )
    try:
        base_weights = normalize_weights(base.weights)
        active_weights = normalize_weights(current_weights)
        if any(abs(base_weights[c] - active_weights[c]) > 1e-8 for c in CRITERIA_NAMES):
            warnings.append(
                "The saved Base scenario weights differ from the currently active criterion weights. Rebuild standard scenarios if Base should reflect the latest inputs."
            )
    except (ValueError, KeyError, TypeError):
        warnings.append("The saved Base scenario weights could not be validated against the current active weights.")
    return warnings


def assemble_report(
    df,
    weights,
    weight_source,
    sub_weights,
    scale_max,
    budget,
    scenarios=None,
    data_source: str | None = None,
) -> dict:
    """Calculate all report sections from the current data and model inputs.

    ``data_source`` is optional to preserve compatibility with existing callers
    and automated tests written before source tracking was added.
    """
    if df is None or len(df) == 0:
        raise ValueError("There are no initiatives to include in the report.")

    source_label = data_source or "Data source not specified"
    illustrative = _is_illustrative_source(source_label)

    scoring = compute_scores(df, weights, sub_weights, scale_max)
    scores = scoring.summary
    optimal = optimize_portfolio(scores, budget)
    greedy = greedy_by_rank(scores, budget)
    if optimal.status == "invalid":
        raise ValueError(optimal.message)
    if greedy.status == "invalid":
        raise ValueError(greedy.message)

    explanations = explain_decisions(scores, optimal, greedy)

    supplied_scenarios = scenarios or None
    scenario_definitions = supplied_scenarios or default_scenarios(weights, budget)
    scenario_results = {
        name: run_scenario(df, scenario, sub_weights, scale_max)
        for name, scenario in scenario_definitions.items()
    }
    comparison = compare_scenarios(scenario_results)

    sensitivity = one_at_a_time(
        df,
        weights,
        sub_weights=sub_weights,
        scale_max=scale_max,
        budget=budget,
    )

    top = scores.sort_values(["Rank", "Final Score"], ascending=[True, False]).iloc[0]
    selected = optimal.table[optimal.table["Selected"]].sort_values(
        "Final Score", ascending=False
    )

    summary = [
        f"{len(df)} strategic initiatives were evaluated against {len(CRITERIA_NAMES)} criteria using the Weighted Sum Model (weights source: {weight_source}).",
        f"Highest-ranked initiative: {top[COL_NAME]} (score {top['Final Score']:.1f}/100).",
        f"With an available budget of {budget:,.2f}, the optimal portfolio contains {optimal.n_selected} initiative(s), total investment {optimal.total_cost:,.2f} ({optimal.utilization:.1f}% of budget), remaining {optimal.remaining:,.2f}, portfolio value {optimal.total_value:,.1f}.",
        f"Compared with highest-ranking-first selection (value {greedy.total_value:,.1f}), optimisation changes portfolio value by {optimal.total_value - greedy.total_value:+,.1f}.",
    ]

    unstable = sensitivity["stability"].loc[
        sensitivity["stability"]["Unstable"], COL_NAME
    ].tolist()
    influence = sensitivity["influence"]
    sensitivity_findings = []
    if not influence.empty:
        top_influence = influence.iloc[0]
        sensitivity_findings.append(
            f"Most influential criterion: {top_influence['Criterion']} (mean absolute rank shift {top_influence['Mean absolute rank shift']:.2f})."
        )
    if unstable:
        sensitivity_findings.append(
            "Initiatives with unstable rankings under the tested weight changes: " + ", ".join(unstable) + "."
        )
    else:
        sensitivity_findings.append(
            "No initiative moved by 3 or more rank positions under the tested weight changes (+/-25% and +/-50%)."
        )

    assumptions = list(BASE_ASSUMPTIONS)
    if illustrative:
        assumptions.append("The bundled sample dataset is illustrative and entirely fictional.")
    else:
        assumptions.append(f"The analysis uses the user-provided dataset: {source_label}. Input values have not been independently audited by the DSS.")

    scenario_warnings = _scenario_warnings(supplied_scenarios, weights, budget)

    return {
        "date": date.today().isoformat(),
        "data_source": source_label,
        "data_is_illustrative": illustrative,
        "n": len(df),
        "budget": float(budget),
        "weight_source": weight_source,
        "weights": scoring.weights,
        "scores": scores,
        "optimal": optimal,
        "greedy": greedy,
        "selected": selected,
        "explanations": explanations,
        "scenario_summary": comparison["summary"],
        "scenario_assumptions": _scenario_assumptions(scenario_results),
        "scenario_ranks": comparison["ranks"],
        "scenario_selection": comparison["selection"],
        "scenario_warnings": scenario_warnings,
        "scenario_comparison_note": (
            "Portfolio values are the sums of initiative scores selected under each scenario's own assumptions. "
            "Because scenario budgets, weights, cost multipliers or exclusions may differ, compare each scenario's "
            "optimised result with its own highest-ranking-first benchmark rather than treating raw portfolio values "
            "across scenarios as a like-for-like performance measure."
        ),
        "stability": sensitivity["stability"],
        "influence": influence,
        "summary": summary,
        "sensitivity_findings": sensitivity_findings,
        "methodology": METHODOLOGY,
        "assumptions": assumptions,
        "limitations": LIMITATIONS,
    }


def _weights_df(ctx):
    return pd.DataFrame({
        "Criterion": CRITERIA_NAMES,
        "Weight (%)": [ctx["weights"][criterion] * 100 for criterion in CRITERIA_NAMES],
    })


def build_excel_report(ctx) -> bytes:
    """Create a multi-sheet Excel workbook containing calculations and assumptions."""
    buffer = io.BytesIO()
    score_columns = [COL_ID, COL_NAME, COL_COST] + CRITERIA_NAMES + ["Final Score", "Rank"]

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({
            "Item": ["Report date", "Dataset source", "Number of initiatives", "Active weight source", "Available budget"],
            "Value": [ctx["date"], ctx["data_source"], ctx["n"], ctx["weight_source"], ctx["budget"]],
        }).to_excel(writer, sheet_name="Dataset Info", index=False)
        pd.DataFrame({"Executive summary": ctx["summary"]}).to_excel(writer, sheet_name="Executive Summary", index=False)
        pd.DataFrame({"Evaluation methodology": ctx["methodology"]}).to_excel(writer, sheet_name="Methodology", index=False)
        _weights_df(ctx).to_excel(writer, sheet_name="Criteria Weights", index=False)
        ctx["scores"][score_columns].to_excel(writer, sheet_name="Ranking", index=False)
        ctx["selected"][[COL_ID, COL_NAME, COL_COST, "Final Score"]].to_excel(writer, sheet_name="Recommended Portfolio", index=False)
        pd.DataFrame({
            "Metric": ["Available budget", "Total investment", "Remaining budget", "Utilisation (%)", "Portfolio value", "Highest-ranking-first value", "Optimisation gain vs rank-first"],
            "Value": [
                ctx["budget"], ctx["optimal"].total_cost, ctx["optimal"].remaining,
                ctx["optimal"].utilization, ctx["optimal"].total_value,
                ctx["greedy"].total_value, ctx["optimal"].total_value - ctx["greedy"].total_value,
            ],
        }).to_excel(writer, sheet_name="Budget Allocation", index=False)
        ctx["explanations"].to_excel(writer, sheet_name="Decision Explanations", index=False)
        ctx["scenario_summary"].to_excel(writer, sheet_name="Scenarios", index=False)
        ctx["scenario_assumptions"].to_excel(writer, sheet_name="Scenario Assumptions", index=False)
        ctx["scenario_ranks"].to_excel(writer, sheet_name="Scenario Ranks", index=False)
        ctx["stability"].to_excel(writer, sheet_name="Sensitivity - Stability", index=False)
        ctx["influence"].to_excel(writer, sheet_name="Sensitivity - Influence", index=False)
        pd.DataFrame({"Key assumptions": ctx["assumptions"]}).to_excel(writer, sheet_name="Assumptions", index=False)
        pd.DataFrame({"Limitations": ctx["limitations"]}).to_excel(writer, sheet_name="Limitations", index=False)

        from openpyxl.styles import Alignment, Font, PatternFill
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = Font(name="Arial", bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="0B2545")
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            worksheet.row_dimensions[1].height = 28
            for column in worksheet.columns:
                width = max(
                    len(str(cell.value)) if cell.value is not None else 0
                    for cell in column
                )
                worksheet.column_dimensions[column[0].column_letter].width = min(max(12, width + 2), 65)
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    if isinstance(cell.value, Real) and not isinstance(cell.value, bool):
                        cell.number_format = "#,##0.00"
                    if isinstance(cell.value, str) and len(cell.value) > 70:
                        cell.alignment = Alignment(wrap_text=True, vertical="top")

    return buffer.getvalue()


def build_pdf_report(ctx) -> bytes:
    """Create a paginated PDF report with source attribution and interpretation notes."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    )

    navy = colors.HexColor("#0B2545")
    blue = colors.HexColor("#2F6690")
    light = colors.HexColor("#F2F5F9")
    grey = colors.HexColor("#64748B")
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], textColor=navy, fontSize=18, leading=22, alignment=TA_LEFT, spaceAfter=6)
    section_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], textColor=navy, fontSize=12, leading=15, spaceBefore=10, spaceAfter=5, keepWithNext=True)
    body_style = ParagraphStyle("ReportBody", parent=styles["BodyText"], fontSize=8.5, leading=11, spaceAfter=3)
    small_style = ParagraphStyle("ReportSmall", parent=body_style, fontSize=7.2, leading=9)
    cell_style = ParagraphStyle("TableCell", parent=small_style, fontSize=7, leading=8.5)
    tiny_cell_style = ParagraphStyle("TinyTableCell", parent=cell_style, fontSize=5.8, leading=7)

    def escape(value):
        text = "" if value is None else str(value)
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br/>"))

    def format_value(value):
        if pd.isna(value):
            return "-"
        if isinstance(value, Real) and not isinstance(value, bool):
            if isinstance(value, int):
                return f"{value:,}"
            return f"{float(value):,.2f}"
        return str(value)

    def make_table(frame, widths=None, compact=False):
        style = tiny_cell_style if compact else cell_style
        data = [[Paragraph(f"<b>{escape(column)}</b>", style) for column in frame.columns]]
        for row in frame.itertuples(index=False, name=None):
            data.append([Paragraph(escape(format_value(value)), style) for value in row])
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def bullets(items):
        return [Paragraph("&bull; " + escape(item), body_style) for item in items]

    def footer(canvas, document):
        canvas.saveState()
        page_width, _ = A4
        canvas.setStrokeColor(colors.HexColor("#D8DEE8"))
        canvas.line(1.6 * cm, 1.15 * cm, page_width - 1.6 * cm, 1.15 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(grey)
        canvas.drawString(1.6 * cm, 0.75 * cm, "Strategic Initiative Prioritisation & Resource Allocation DSS")
        canvas.drawRightString(page_width - 1.6 * cm, 0.75 * cm, f"Page {document.page}")
        canvas.restoreState()

    scores = ctx["scores"]
    scenario_summary = ctx["scenario_summary"]
    scenario_core_columns = [
        "Scenario", "Budget", "Cost multiplier", "Initiatives selected",
        "Total investment", "Remaining budget", "Budget utilisation (%)", "Portfolio value",
        "Value gain vs highest-ranking-first",
    ]
    scenario_core = scenario_summary[[c for c in scenario_core_columns if c in scenario_summary.columns]]

    story = [
        Paragraph("Strategic Initiative Prioritisation and Resource Allocation Decision Report", title_style),
        Paragraph(
            f"Generated {escape(ctx['date'])} &nbsp;|&nbsp; Dataset: {escape(ctx['data_source'])} &nbsp;|&nbsp; "
            f"Initiatives: {ctx['n']} &nbsp;|&nbsp; Weights: {escape(ctx['weight_source'])}",
            small_style,
        ),
        Spacer(1, 8),
        Paragraph("1. Executive Summary", section_style),
        *bullets(ctx["summary"]),
        Paragraph("2. Evaluation Methodology", section_style),
        *bullets(ctx["methodology"]),
        Paragraph(f"3. Criteria Weights (source: {escape(ctx['weight_source'])})", section_style),
        make_table(_weights_df(ctx), [9 * cm, 4 * cm]),
        Paragraph("4. Initiative Ranking", section_style),
        make_table(scores[["Rank", COL_ID, COL_NAME, COL_COST, "Final Score"]], [1.2 * cm, 2.2 * cm, 8.0 * cm, 2.4 * cm, 2.4 * cm]),
        Paragraph("5. Recommended Portfolio and Budget Allocation", section_style),
        make_table(ctx["selected"][[COL_ID, COL_NAME, COL_COST, "Final Score"]], [2.3 * cm, 8.8 * cm, 2.5 * cm, 2.5 * cm]),
        Spacer(1, 6),
        Paragraph(
            f"<b>Budget:</b> {ctx['budget']:,.2f} &nbsp;|&nbsp; "
            f"<b>Invested:</b> {ctx['optimal'].total_cost:,.2f} ({ctx['optimal'].utilization:.1f}%) &nbsp;|&nbsp; "
            f"<b>Remaining:</b> {ctx['optimal'].remaining:,.2f} &nbsp;|&nbsp; "
            f"<b>Portfolio value:</b> {ctx['optimal'].total_value:,.2f}", body_style
        ),
        PageBreak(),
        Paragraph("6. Scenario Comparison", section_style),
        Paragraph(escape(ctx["scenario_comparison_note"]), small_style),
        Spacer(1, 5),
        make_table(scenario_core, [2.2 * cm, 1.45 * cm, 1.35 * cm, 1.6 * cm, 1.7 * cm, 1.55 * cm, 1.75 * cm, 1.55 * cm, 2.45 * cm], compact=True),
        Paragraph("Scenario assumptions", section_style),
    ]

    for _, row in ctx["scenario_assumptions"].iterrows():
        story.append(KeepTogether([
            Paragraph(f"<b>{escape(row['Scenario'])}</b> — budget {float(row['Budget']):,.2f}; cost multiplier {float(row['Cost multiplier']):.2f}.", body_style),
            Paragraph(f"<b>Weights:</b> {escape(row['Criteria weights'])}", small_style),
            Paragraph(f"<b>Excluded initiatives:</b> {escape(row['Excluded initiatives'])}", small_style),
            Paragraph(f"<b>Description:</b> {escape(row['Description'])}", small_style),
            Spacer(1, 4),
        ]))

    if ctx.get("scenario_warnings"):
        story.append(Paragraph("Scenario configuration warnings", section_style))
        story.extend(bullets(ctx["scenario_warnings"]))

    story.extend([
        Paragraph("7. Decision Explanations", section_style),
        Paragraph("The following table explains the model's selection or rejection of each initiative under the current budget.", small_style),
        make_table(ctx["explanations"][["Rank", COL_ID, COL_NAME, "Decision", "Cost", "Final Score", "Explanation"]],
                   [0.9 * cm, 1.7 * cm, 4.0 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 6.5 * cm], compact=True),
        Paragraph("8. Sensitivity Findings", section_style),
        *bullets(ctx["sensitivity_findings"]),
        Paragraph("Criterion influence", small_style),
        make_table(ctx["influence"], compact=False),
        Paragraph("Initiative ranking stability", small_style),
        make_table(ctx["stability"], compact=True),
        Paragraph("9. Key Assumptions", section_style),
        *bullets(ctx["assumptions"]),
        Paragraph("10. Limitations", section_style),
        *bullets(ctx["limitations"]),
    ])

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.45 * cm,
        bottomMargin=1.55 * cm,
        title="Strategic Initiative Prioritisation and Resource Allocation Decision Report",
        author="Academic DSS Prototype",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# ============================================================================
# STREAMLIT PAGE
# ============================================================================

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core import ui


# ============================================================
# INITIALISATION AND CURRENT ANALYSIS
# ============================================================

init_state()
require_data()
ss = st.session_state

a = get_analysis()

ui.page_header(
    "Decision Report",
    "A complete, downloadable record of the current strategic evaluation, portfolio recommendation and scenario analysis."
)

if a.optimal.status == "invalid":
    st.error(a.optimal.message)
    st.stop()

if a.note:
    st.warning(a.note)

try:
    with st.spinner("Calculating report sections and preparing PDF / Excel exports..."):
        ctx = assemble_report(
            df=ss.df,
            weights=a.weights,
            weight_source=a.source,
            sub_weights=ss.sub_weights,
            scale_max=ss.scale_max,
            budget=a.budget,
            scenarios=ss.scenarios or None,
            data_source=getattr(ss, "data_source", "Data source not specified"),
        )
        pdf = build_pdf_report(ctx)
        xlsx = build_excel_report(ctx)
except Exception as exc:
    st.error(f"The report could not be generated: {exc}")
    st.exception(exc)
    st.stop()


# ============================================================
# REPORT METADATA AND DOWNLOADS
# ============================================================

st.subheader("Report details")
ui.kpi_cards([
    ("Initiatives evaluated", f"{ctx['n']}", "Current dataset"),
    ("Active weight source", ctx["weight_source"], "Used in the Weighted Sum Model"),
    ("Available budget", f"{ctx['budget']:,.2f}", "Current decision constraint"),
    ("Report date", ctx["date"], "Generated from current inputs"),
])

st.caption(f"Dataset source: **{ctx['data_source']}**")
if ctx["data_is_illustrative"]:
    st.info("This report uses the bundled illustrative / fictional sample dataset.")
else:
    st.info("This report uses a user-provided dataset. The DSS processes the uploaded values but does not independently audit their accuracy.")

if ctx["scenario_warnings"]:
    for warning in ctx["scenario_warnings"]:
        st.warning(warning)

left, right = st.columns(2)
with left:
    st.download_button(
        "Download professional report (PDF)",
        data=pdf,
        file_name="strategic_decision_report.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
with right:
    st.download_button(
        "Download analysis workbook (Excel)",
        data=xlsx,
        file_name="strategic_decision_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

st.divider()


# ============================================================
# REPORT PREVIEW TABS
# ============================================================

tab_exec, tab_decision, tab_scenarios, tab_sensitivity, tab_method = st.tabs([
    "Executive Summary",
    "Decision Results",
    "Scenario Comparison",
    "Sensitivity Analysis",
    "Methodology & Governance",
])


# ------------------------------------------------------------
# TAB 1 - EXECUTIVE SUMMARY
# ------------------------------------------------------------

with tab_exec:
    st.subheader("1. Executive summary")
    for item in ctx["summary"]:
        st.markdown(f"- {item}")

    opt = ctx["optimal"]
    st.subheader("Budget allocation")
    ui.kpi_cards([
        ("Selected initiatives", f"{opt.n_selected}", f"out of {ctx['n']} evaluated"),
        ("Total investment", f"{opt.total_cost:,.2f}", f"{opt.utilization:.1f}% of budget"),
        ("Remaining budget", f"{opt.remaining:,.2f}", "Unallocated"),
        ("Portfolio value", f"{opt.total_value:,.2f}", "Sum of selected initiative scores"),
    ])

    comparison_gain = opt.total_value - ctx["greedy"].total_value
    if comparison_gain > 1e-8:
        st.success(
            f"The optimisation model delivers {comparison_gain:,.2f} more portfolio-score points "
            "than the highest-ranking-first benchmark under the same current budget."
        )
    elif comparison_gain < -1e-8:
        st.warning(
            "The optimisation result is below the rank-first benchmark. Review the solver result and model inputs before relying on this report."
        )
    else:
        st.info("The optimal portfolio and highest-ranking-first benchmark have the same portfolio value under the current budget.")


# ------------------------------------------------------------
# TAB 2 - DECISION RESULTS
# ------------------------------------------------------------

with tab_decision:
    st.subheader("2. Criteria weights")
    weights_df = pd.DataFrame({
        "Criterion": CRITERIA_NAMES,
        "Weight (%)": [ctx["weights"][criterion] * 100 for criterion in CRITERIA_NAMES],
    })
    ui.table(weights_df)

    st.subheader("3. Initiative ranking")
    ranking_columns = ["Rank", COL_ID, COL_NAME, COL_COST] + CRITERIA_NAMES + ["Final Score"]
    ui.table(ctx["scores"][ranking_columns])

    st.subheader("4. Recommended portfolio and budget allocation")
    portfolio_columns = [COL_ID, COL_NAME, COL_COST, "Final Score"]
    ui.table(ctx["selected"][portfolio_columns])

    st.subheader("5. Why each initiative was selected or rejected")
    explanation_columns = ["Rank", COL_ID, COL_NAME, "Decision", "Cost", "Final Score", "Explanation"]
    st.dataframe(
        ctx["explanations"][explanation_columns],
        hide_index=True,
        **ui.stretch(),
        column_config={
            "Explanation": st.column_config.TextColumn(width="large"),
            "Final Score": st.column_config.NumberColumn(format="%.2f"),
            "Cost": st.column_config.NumberColumn(format="%.2f"),
        },
    )


# ------------------------------------------------------------
# TAB 3 - SCENARIO COMPARISON
# ------------------------------------------------------------

with tab_scenarios:
    st.subheader("6. Scenario comparison")
    st.markdown(ctx["scenario_comparison_note"])

    scenario_columns = [
        "Scenario", "Budget", "Cost multiplier", "Initiatives selected",
        "Total investment", "Remaining budget", "Budget utilisation (%)",
        "Portfolio value", "Highest-ranked initiative",
        "Value gain vs highest-ranking-first",
    ]
    scenario_columns = [column for column in scenario_columns if column in ctx["scenario_summary"].columns]
    ui.table(ctx["scenario_summary"][scenario_columns])

    st.subheader("Scenario assumptions")
    ui.table(ctx["scenario_assumptions"])

    st.subheader("Budget utilisation by scenario")
    scenario_df = ctx["scenario_summary"]
    fig = go.Figure()
    fig.add_bar(
        name="Invested",
        x=scenario_df["Scenario"],
        y=scenario_df["Total investment"],
        marker_color=ui.NAVY,
    )
    fig.add_bar(
        name="Remaining",
        x=scenario_df["Scenario"],
        y=scenario_df["Remaining budget"],
        marker_color=ui.LIGHT,
    )
    fig.add_scatter(
        name="Available budget",
        x=scenario_df["Scenario"],
        y=scenario_df["Budget"],
        mode="markers",
        marker=dict(symbol="line-ew", size=24, line=dict(width=3, color=ui.RED)),
    )
    fig.update_layout(
        barmode="stack",
        title="Investment and remaining budget by scenario",
        yaxis_title="Budget units",
    )
    ui.chart(fig, 380)

    st.subheader("Initiative ranking across scenarios")
    ui.table(ctx["scenario_ranks"])

    st.subheader("Initiative selection across scenarios")
    selection = ctx["scenario_selection"].copy()
    st.dataframe(selection, hide_index=True, **ui.stretch())


# ------------------------------------------------------------
# TAB 4 - SENSITIVITY ANALYSIS
# ------------------------------------------------------------

with tab_sensitivity:
    st.subheader("7. Sensitivity findings")
    for item in ctx["sensitivity_findings"]:
        st.markdown(f"- {item}")

    st.subheader("Criterion influence")
    ui.table(ctx["influence"])

    if not ctx["influence"].empty:
        influence = ctx["influence"].sort_values("Mean absolute rank shift", ascending=True)
        fig = go.Figure(go.Bar(
            x=influence["Mean absolute rank shift"],
            y=influence["Criterion"],
            orientation="h",
            marker_color=ui.NAVY,
            text=influence["Mean absolute rank shift"].round(2),
            textposition="outside",
        ))
        fig.update_layout(
            title="Average ranking movement when each criterion weight changes",
            xaxis_title="Mean absolute rank shift",
        )
        ui.chart(fig, 360)

    st.subheader("Initiative ranking stability")
    ui.table(ctx["stability"])


# ------------------------------------------------------------
# TAB 5 - METHODOLOGY AND GOVERNANCE
# ------------------------------------------------------------

with tab_method:
    st.subheader("8. Evaluation methodology")
    for item in ctx["methodology"]:
        st.markdown(f"- {item}")

    st.subheader("9. Key assumptions")
    for item in ctx["assumptions"]:
        st.markdown(f"- {item}")

    st.subheader("10. Limitations")
    for item in ctx["limitations"]:
        st.markdown(f"- {item}")

    with st.expander("Report verification checks"):
        weight_total = sum(ctx["weights"].values())
        selected_cost = float(ctx["selected"][COL_COST].sum())
        checks = pd.DataFrame([
            {"Check": "Active criteria weights sum to 100%", "Result": f"{weight_total * 100:.4f}%", "Status": "PASS" if abs(weight_total - 1) < 1e-6 else "REVIEW"},
            {"Check": "Recommended portfolio is within budget", "Result": f"{selected_cost:,.2f} <= {ctx['budget']:,.2f}", "Status": "PASS" if selected_cost <= ctx["budget"] + 1e-8 else "FAIL"},
            {"Check": "Recommended portfolio cost matches optimiser", "Result": f"{selected_cost:,.2f} vs {ctx['optimal'].total_cost:,.2f}", "Status": "PASS" if abs(selected_cost - ctx["optimal"].total_cost) < 1e-6 else "REVIEW"},
            {"Check": "Scenario portfolios are within their budgets", "Result": "Checked per scenario", "Status": "PASS" if (ctx["scenario_summary"]["Total investment"] <= ctx["scenario_summary"]["Budget"] + 1e-8).all() else "FAIL"},
        ])
        st.dataframe(checks, hide_index=True, **ui.stretch())
