"""Scenario analysis: re-run scoring + optimisation under alternative assumptions."""
from dataclasses import dataclass, field, replace
import pandas as pd

from .schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES, DEFAULT_SCALE_MAX
from .weighted_scoring import compute_scores, normalize_weights
from .optimization import optimize_portfolio, greedy_by_rank, PortfolioResult
from .validation import validate_budget, validate_weights


@dataclass
class Scenario:
    name: str
    budget: float
    weights: dict                       # criterion -> weight (any positive scale; normalised on use)
    cost_multiplier: float = 1.0        # e.g. 1.10 = every cost +10 %
    excluded_ids: list = field(default_factory=list)
    description: str = ""


@dataclass
class ScenarioResult:
    scenario: Scenario
    scores: pd.DataFrame
    optimal: PortfolioResult
    greedy: PortfolioResult


def validate_scenario(s: Scenario) -> list:
    errs = validate_budget(s.budget) + validate_weights(s.weights)
    if not (s.cost_multiplier and s.cost_multiplier > 0):
        errs.append("Cost multiplier must be greater than 0.")
    return errs


def run_scenario(df: pd.DataFrame, s: Scenario, sub_weights: dict = None,
                 scale_max: int = DEFAULT_SCALE_MAX) -> ScenarioResult:
    errs = validate_scenario(s)
    if errs:
        raise ValueError("; ".join(errs))
    d = df[~df[COL_ID].isin(s.excluded_ids)].copy().reset_index(drop=True)
    if d.empty:
        raise ValueError("All initiatives are excluded in this scenario.")
    d[COL_COST] = d[COL_COST] * float(s.cost_multiplier)
    scoring = compute_scores(d, s.weights, sub_weights, scale_max)
    return ScenarioResult(s, scoring.summary,
                          optimize_portfolio(scoring.summary, s.budget),
                          greedy_by_rank(scoring.summary, s.budget))


def default_scenarios(base_weights: dict, base_budget: float) -> dict:
    """Base / Growth-oriented / Risk-averse, derived from the CURRENT weights and budget."""
    w = normalize_weights(base_weights)

    def shifted(mult):
        raw = {c: w[c] * mult.get(c, 1.0) for c in CRITERIA_NAMES}
        t = sum(raw.values())
        return {c: raw[c] / t for c in CRITERIA_NAMES}

    return {
        "Base": Scenario("Base", base_budget, dict(w), 1.0, [],
                         "Current weights and budget."),
        "Growth-Oriented": Scenario(
            "Growth-Oriented", base_budget * 1.15,
            shifted({"Financial Attractiveness": 1.4, "Business Impact": 1.5, "Risk Assessment": 0.5}),
            1.0, [], "Budget +15 %; emphasis on financial return and business impact; risk de-emphasised."),
        "Risk-Averse": Scenario(
            "Risk-Averse", base_budget * 0.85,
            shifted({"Risk Assessment": 2.0, "Implementation Feasibility": 1.5,
                     "Financial Attractiveness": 0.8, "Business Impact": 0.7}),
            1.10, [], "Budget -15 %; costs +10 % (overrun buffer); emphasis on risk and feasibility."),
    }


def compare_scenarios(results: dict) -> dict:
    """Build comparison tables from {name: ScenarioResult}."""
    rows, rank_cols, sel_cols = [], {}, {}
    for name, r in results.items():
        opt, sc = r.optimal, r.scores
        top = sc.sort_values("Rank").iloc[0]
        rows.append({
            "Scenario": name, "Budget": r.scenario.budget,
            "Cost multiplier": r.scenario.cost_multiplier,
            "Initiatives selected": opt.n_selected, "Total investment": opt.total_cost,
            "Remaining budget": opt.remaining, "Budget utilisation (%)": opt.utilization,
            "Portfolio value": opt.total_value,
            "Highest-ranked initiative": top[COL_NAME],
            "Value gain vs highest-ranking-first": opt.total_value - r.greedy.total_value})
        rank_cols[name] = sc.set_index(COL_ID)["Rank"]
        sel_cols[name] = opt.table.set_index(COL_ID)["Selected"]
    names = {}
    for r in results.values():
        names.update(dict(zip(r.scores[COL_ID], r.scores[COL_NAME])))
    ranks = pd.DataFrame(rank_cols)
    sel = pd.DataFrame(sel_cols).fillna(False)
    ranks.insert(0, COL_NAME, [names.get(i, i) for i in ranks.index])
    sel.insert(0, COL_NAME, [names.get(i, i) for i in sel.index])
    return {"summary": pd.DataFrame(rows), "ranks": ranks.reset_index(),
            "selection": sel.reset_index()}
