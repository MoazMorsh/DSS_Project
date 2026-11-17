"""Budget-constrained binary portfolio optimisation (0-1 knapsack).

    maximise   sum_i Score_i * x_i
    subject to sum_i Cost_i  * x_i <= Budget,   x_i in {0, 1}

Solved exactly with scipy.optimize.milp (HiGHS). An exact dynamic-programming
solver is kept as an automatic fallback and as an independent cross-check.
"""
from dataclasses import dataclass, field
import math
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

from .schema import COL_ID, COL_NAME, COL_COST
from .validation import validate_budget

SCORE = "Final Score"
EPS = 1e-9


@dataclass
class PortfolioResult:
    method: str
    status: str                      # "optimal", "feasible", "empty", "invalid"
    message: str
    table: pd.DataFrame              # all initiatives with 'Selected' flag
    budget: float
    total_cost: float = 0.0
    total_value: float = 0.0         # sum of final scores of selected initiatives
    remaining: float = 0.0
    utilization: float = 0.0         # percent of budget used
    selected_ids: list = field(default_factory=list)

    @property
    def n_selected(self) -> int:
        return len(self.selected_ids)

    @property
    def average_score(self) -> float:
        return self.total_value / self.n_selected if self.n_selected else 0.0


def _prepare(items: pd.DataFrame) -> pd.DataFrame:
    for col in (COL_ID, COL_NAME, COL_COST, SCORE):
        if col not in items.columns:
            raise ValueError(f"Missing column '{col}'.")
    d = items[[c for c in items.columns]].copy().reset_index(drop=True)
    if not np.all(np.isfinite(d[COL_COST].astype(float))) or (d[COL_COST] <= 0).any():
        raise ValueError("All costs must be finite and greater than zero.")
    if not np.all(np.isfinite(d[SCORE].astype(float))):
        raise ValueError("All scores must be finite.")
    return d


def _finish(d, x, budget, method, status, message) -> PortfolioResult:
    d = d.copy()
    d["Selected"] = np.asarray(x, dtype=bool)
    sel = d[d["Selected"]]
    cost = float(sel[COL_COST].sum())
    value = float(sel[SCORE].sum())
    return PortfolioResult(
        method=method, status=status, message=message, table=d, budget=float(budget),
        total_cost=cost, total_value=value, remaining=float(budget) - cost,
        utilization=(cost / budget * 100.0) if budget > 0 else 0.0,
        selected_ids=list(sel[COL_ID]))


def _invalid(items, budget, msg, method):
    t = items.copy() if isinstance(items, pd.DataFrame) else pd.DataFrame()
    t["Selected"] = False
    return PortfolioResult(method, "invalid", msg, t, float(budget) if _isnum(budget) else 0.0,
                           remaining=float(budget) if _isnum(budget) else 0.0)


def _isnum(v):
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _dp_knapsack(costs, values, budget, scale=100):
    """Exact DP on costs rounded to 1/scale units (fallback / cross-check)."""
    w = np.round(np.asarray(costs) * scale).astype(int)
    cap = int(math.floor(budget * scale + 1e-9))
    n = len(w)
    best = np.zeros((n + 1, cap + 1))
    for i in range(1, n + 1):
        best[i] = best[i - 1]
        if w[i - 1] <= cap:
            cand = best[i - 1][: cap + 1 - w[i - 1]] + values[i - 1]
            best[i][w[i - 1]:] = np.maximum(best[i][w[i - 1]:], cand)
    x = np.zeros(n, dtype=bool)
    c = cap
    for i in range(n, 0, -1):
        if best[i][c] != best[i - 1][c]:
            x[i - 1] = True
            c -= w[i - 1]
    return x


def optimize_portfolio(items: pd.DataFrame, budget: float) -> PortfolioResult:
    """Optimal (value-maximising) portfolio under the budget."""
    method = "Binary optimisation (MILP)"
    errs = validate_budget(budget)
    if errs:
        return _invalid(items, 0, errs[0], method)
    budget = float(budget)
    try:
        d = _prepare(items)
    except ValueError as e:
        return _invalid(items, budget, str(e), method)

    n = len(d)
    if n == 0:
        return _invalid(items, budget, "No initiatives to optimise.", method)
    costs = d[COL_COST].values.astype(float)
    vals = d[SCORE].values.astype(float)

    if costs.min() > budget + EPS:
        return _finish(d, np.zeros(n, bool), budget, method, "empty",
                       "No initiative is affordable: every cost exceeds the budget.")

    x = None
    try:
        res = milp(c=-vals, constraints=LinearConstraint(costs.reshape(1, -1), -np.inf, budget),
                   integrality=np.ones(n), bounds=Bounds(0, 1))
        if res.success and res.x is not None:
            cand = np.round(res.x).astype(bool)
            if costs[cand].sum() <= budget + EPS:     # verify feasibility explicitly
                x = cand
    except Exception:                                  # pragma: no cover - solver problems
        x = None
    if x is None:
        x = _dp_knapsack(costs, vals, budget)
        method = "Binary optimisation (exact DP fallback)"
        if costs[x].sum() > budget + EPS:              # pragma: no cover
            return _invalid(items, budget, "Solver could not produce a feasible portfolio.", method)

    status = "optimal" if x.any() else "empty"
    msg = "Optimal portfolio found." if x.any() else "No initiative added value within the budget."
    return _finish(d, x, budget, method, status, msg)


def greedy_by_rank(items: pd.DataFrame, budget: float) -> PortfolioResult:
    """Benchmark: walk down the ranking (highest score first), take each initiative that still fits."""
    method = "Highest-ranking-first"
    errs = validate_budget(budget)
    if errs:
        return _invalid(items, 0, errs[0], method)
    budget = float(budget)
    try:
        d = _prepare(items)
    except ValueError as e:
        return _invalid(items, budget, str(e), method)
    order = d.sort_values([SCORE, COL_ID], ascending=[False, True]).index
    x = np.zeros(len(d), bool)
    spent = 0.0
    for i in order:
        c = float(d.at[i, COL_COST])
        if spent + c <= budget + EPS:
            x[i] = True
            spent += c
    return _finish(d, x, budget, method, "feasible" if x.any() else "empty",
                   "Greedy selection by rank.")


def explain_decisions(items: pd.DataFrame, optimal: PortfolioResult, greedy: PortfolioResult) -> pd.DataFrame:
    """Plain-language reason for every initiative's inclusion / exclusion (all computed)."""
    d = optimal.table.copy()
    d["Rank"] = d[SCORE].round(9).rank(ascending=False, method="min").astype(int)
    d["Score per cost"] = d[SCORE] / d[COL_COST]
    d["Value-density rank"] = d["Score per cost"].rank(ascending=False, method="min").astype(int)
    greedy_ids = set(greedy.selected_ids)
    rows = []
    for _, r in d.sort_values("Rank").iterrows():
        cost, rem = r[COL_COST], optimal.remaining
        if r["Selected"]:
            txt = f"Selected: score {r[SCORE]:.1f} for cost {cost:g}; part of the value-maximising combination."
            if r[COL_ID] not in greedy_ids:
                txt += " Note: highest-ranking-first would NOT have chosen it."
        else:
            if cost > optimal.budget + EPS:
                txt = f"Rejected: its cost ({cost:g}) alone exceeds the total budget ({optimal.budget:g})."
            elif cost > rem + EPS:
                over = cost - rem
                txt = (f"Rejected: ranked #{r['Rank']} but adding it would exceed the budget by {over:g} "
                       f"(only {rem:g} remains); the chosen combination delivers more total value.")
            else:
                txt = "Rejected: it adds no value to the portfolio (non-positive score)."
            if r["Rank"] <= max(3, len(d) // 3):
                txt += " High rank does not guarantee selection under a budget constraint."
        rows.append({COL_ID: r[COL_ID], COL_NAME: r[COL_NAME], "Rank": int(r["Rank"]),
                     "Decision": "Selected" if r["Selected"] else "Rejected",
                     "Cost": cost, "Final Score": r[SCORE],
                     "Value-density rank": int(r["Value-density rank"]), "Explanation": txt})
    return pd.DataFrame(rows)
