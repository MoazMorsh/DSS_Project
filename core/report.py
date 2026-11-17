"""Decision report: assembles current analysis results and exports to Excel / PDF."""
import io
from datetime import date
import pandas as pd

from .schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES, CRITERIA
from .weighted_scoring import compute_scores
from .optimization import optimize_portfolio, greedy_by_rank, explain_decisions
from .scenario_analysis import run_scenario, compare_scenarios, default_scenarios
from .sensitivity_analysis import one_at_a_time

METHODOLOGY = [
    "Criteria weights: obtained from the selected source (default proposed weights, manual weights or AHP pairwise comparisons; AHP uses the principal eigenvector and is checked with the Consistency Ratio, CR <= 0.10).",
    "Normalisation: every subcriterion is rescaled to 0-100 where higher is always better. 1-5 ratings use linear rescaling; ROI, NPV and Payback use min-max scaling across the evaluated initiatives. Risk, complexity and payback are cost-type criteria and are inverted.",
    "Scoring: Weighted Sum Model, Final Score = sum(criterion weight x criterion score), 0-100 scale. Subcriteria are equally weighted inside each criterion unless edited.",
    "Portfolio selection: binary optimisation (0-1 knapsack) maximising the sum of final scores subject to total cost <= available budget. Budget is a constraint, not a criterion.",
    "Scenario analysis: alternative budget, weights and cost assumptions are fully recomputed. Sensitivity analysis: criterion weights are varied one at a time and the ranking is recomputed.",
]
ASSUMPTIONS = [
    "Criterion scores are additive and compensatory (a weakness in one criterion can be offset by strength in another).",
    "Initiative costs are known point estimates; initiatives are independent, indivisible and have no interdependencies.",
    "The budget applies to one planning period; costs and NPV share the same currency unit.",
    "Qualitative ratings reflect the judgement of the evaluators who entered them; the bundled sample data is fictional.",
    "Min-max normalisation is relative to the set of initiatives evaluated: adding or removing initiatives can change scores.",
]
LIMITATIONS = [
    "The system supports, and does not replace, managerial judgement; outputs are decision aids, not decisions.",
    "Results depend on input quality and on the chosen weights; AHP judgements are subjective.",
    "The model ignores synergies, dependencies, mandatory projects, multi-period budgets and uncertainty distributions.",
    "This is a functional prototype. It has not been validated against real organisational outcomes and no claim is made that it improves corporate performance.",
    "Session data is temporary: it is lost when the browser session ends unless exported.",
]


def assemble_report(df, weights, weight_source, sub_weights, scale_max, budget, scenarios=None) -> dict:
    scoring = compute_scores(df, weights, sub_weights, scale_max)
    s = scoring.summary
    opt = optimize_portfolio(s, budget)
    gr = greedy_by_rank(s, budget)
    expl = explain_decisions(s, opt, gr)
    scen = scenarios or default_scenarios(weights, budget)
    results = {n: run_scenario(df, sc, sub_weights, scale_max) for n, sc in scen.items()}
    comp = compare_scenarios(results)
    sens = one_at_a_time(df, weights, sub_weights=sub_weights, scale_max=scale_max, budget=budget)
    top = s.iloc[0]
    sel = opt.table[opt.table["Selected"]].sort_values("Final Score", ascending=False)

    summary = [
        f"{len(df)} strategic initiatives were evaluated against {len(CRITERIA_NAMES)} criteria using the Weighted Sum Model (weights source: {weight_source}).",
        f"Highest-ranked initiative: {top[COL_NAME]} (score {top['Final Score']:.1f}/100).",
        f"With an available budget of {budget:,.2f}, the optimal portfolio contains {opt.n_selected} initiative(s), total investment {opt.total_cost:,.2f} ({opt.utilization:.1f}% of budget), remaining {opt.remaining:,.2f}, portfolio value {opt.total_value:,.1f}.",
        f"Compared with highest-ranking-first selection (value {gr.total_value:,.1f}), optimisation changes portfolio value by {opt.total_value - gr.total_value:+,.1f}.",
    ]
    unstable = sens["stability"][sens["stability"]["Unstable"]][COL_NAME].tolist()
    top_infl = sens["influence"].iloc[0]
    sens_findings = [
        f"Most influential criterion: {top_infl['Criterion']} (mean absolute rank shift {top_infl['Mean absolute rank shift']:.2f}).",
        ("Initiatives with unstable rankings: " + ", ".join(unstable)) if unstable
        else "No initiative moved by 3 or more rank positions under the tested weight changes (+/-25 %, +/-50 %).",
    ]
    return {"date": date.today().isoformat(), "n": len(df), "budget": budget, "weight_source": weight_source,
            "weights": scoring.weights, "scores": s, "optimal": opt, "greedy": gr,
            "selected": sel, "explanations": expl, "scenario_summary": comp["summary"],
            "scenario_ranks": comp["ranks"], "stability": sens["stability"],
            "influence": sens["influence"], "summary": summary, "sensitivity_findings": sens_findings,
            "methodology": METHODOLOGY, "assumptions": ASSUMPTIONS, "limitations": LIMITATIONS}


def _weights_df(ctx):
    return pd.DataFrame({"Criterion": CRITERIA_NAMES,
                         "Weight (%)": [ctx["weights"][c] * 100 for c in CRITERIA_NAMES]})


def build_excel_report(ctx) -> bytes:
    buf = io.BytesIO()
    cols = [COL_ID, COL_NAME, COL_COST] + CRITERIA_NAMES + ["Final Score", "Rank"]
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame({"Executive summary": ctx["summary"]}).to_excel(xw, sheet_name="Executive Summary", index=False)
        pd.DataFrame({"Evaluation methodology": ctx["methodology"]}).to_excel(xw, sheet_name="Methodology", index=False)
        _weights_df(ctx).to_excel(xw, sheet_name="Criteria Weights", index=False)
        ctx["scores"][cols].to_excel(xw, sheet_name="Ranking", index=False)
        ctx["selected"][[COL_ID, COL_NAME, COL_COST, "Final Score"]].to_excel(xw, sheet_name="Recommended Portfolio", index=False)
        pd.DataFrame({
            "Metric": ["Available budget", "Total investment", "Remaining budget", "Utilisation (%)", "Portfolio value"],
            "Value": [ctx["budget"], ctx["optimal"].total_cost, ctx["optimal"].remaining,
                      ctx["optimal"].utilization, ctx["optimal"].total_value]}).to_excel(xw, sheet_name="Budget Allocation", index=False)
        ctx["explanations"].to_excel(xw, sheet_name="Decision Explanations", index=False)
        ctx["scenario_summary"].to_excel(xw, sheet_name="Scenarios", index=False)
        ctx["stability"].to_excel(xw, sheet_name="Sensitivity - Stability", index=False)
        ctx["influence"].to_excel(xw, sheet_name="Sensitivity - Influence", index=False)
        pd.DataFrame({"Key assumptions": ctx["assumptions"]}).to_excel(xw, sheet_name="Assumptions", index=False)
        pd.DataFrame({"Limitations": ctx["limitations"]}).to_excel(xw, sheet_name="Limitations", index=False)
        from openpyxl.styles import Font, PatternFill, Alignment
        for ws in xw.book.worksheets:
            for c in ws[1]:
                c.font = Font(name="Arial", bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="0B2545")
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(12, width + 2), 90)
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if isinstance(c.value, float):
                        c.number_format = "#,##0.00"
                    if isinstance(c.value, str) and len(c.value) > 90:
                        c.alignment = Alignment(wrap_text=True, vertical="top")
    return buf.getvalue()


def build_pdf_report(ctx) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    navy = colors.HexColor("#0B2545")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=navy, fontSize=18)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=navy, fontSize=13, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=body, fontSize=7.5, leading=9)

    def esc(t):
        return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def table(df, widths=None):
        data = [[Paragraph(f"<b>{esc(c)}</b>", cell) for c in df.columns]]
        for row in df.itertuples(index=False):
            data.append([Paragraph(esc(f"{v:,.2f}" if isinstance(v, float) else v), cell) for v in row])
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FA")]),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        # header text must be white
        for i, c in enumerate(df.columns):
            data[0][i] = Paragraph(f"<font color='white'><b>{esc(c)}</b></font>", cell)
        return t

    def bullets(items):
        return [Paragraph("&bull; " + esc(i), body) for i in items]

    s = ctx["scores"]
    story = [Paragraph("Strategic Initiative Prioritization and Resource Allocation Decision Report", h1),
             Paragraph(f"Generated {ctx['date']} | Academic prototype - illustrative data", body),
             Paragraph("1. Executive Summary", h2), *bullets(ctx["summary"]),
             Paragraph("2. Evaluation Methodology", h2), *bullets(ctx["methodology"]),
             Paragraph(f"3. Criteria Weights (source: {esc(ctx['weight_source'])})", h2),
             table(_weights_df(ctx), [9 * cm, 4 * cm]),
             Paragraph("4. Initiative Ranking", h2),
             table(s[["Rank", COL_NAME, COL_COST, "Final Score"]], [1.5 * cm, 9 * cm, 3 * cm, 3 * cm]),
             Paragraph("5. Recommended Portfolio and Budget Allocation", h2),
             table(ctx["selected"][[COL_ID, COL_NAME, COL_COST, "Final Score"]], [2.5 * cm, 8 * cm, 3 * cm, 3 * cm]),
             Spacer(1, 6),
             Paragraph(f"Budget {ctx['budget']:,.2f} | Invested {ctx['optimal'].total_cost:,.2f} "
                       f"({ctx['optimal'].utilization:.1f}%) | Remaining {ctx['optimal'].remaining:,.2f} | "
                       f"Portfolio value {ctx['optimal'].total_value:,.1f}", body),
             PageBreak(),
             Paragraph("6. Scenario Comparison", h2),
             table(ctx["scenario_summary"][["Scenario", "Budget", "Initiatives selected", "Total investment",
                                            "Remaining budget", "Portfolio value"]]),
             Paragraph("7. Sensitivity Findings", h2), *bullets(ctx["sensitivity_findings"]),
             Spacer(1, 4), table(ctx["influence"]),
             Paragraph("8. Key Assumptions", h2), *bullets(ctx["assumptions"]),
             Paragraph("9. Limitations", h2), *bullets(ctx["limitations"])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                      topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                      title="Decision Report").build(story)
    return buf.getvalue()
