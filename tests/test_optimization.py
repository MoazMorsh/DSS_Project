import itertools
import numpy as np
import pandas as pd
import pytest
from core.schema import COL_ID, COL_NAME, COL_COST
from core.optimization import (optimize_portfolio, greedy_by_rank, explain_decisions, _dp_knapsack)


def items(costs, scores):
    return pd.DataFrame({COL_ID: [f"I{i}" for i in range(len(costs))],
                         COL_NAME: [f"N{i}" for i in range(len(costs))],
                         COL_COST: costs, "Final Score": scores})


def brute(costs, scores, budget):
    best = 0
    for mask in itertools.product([0, 1], repeat=len(costs)):
        c = sum(m * x for m, x in zip(mask, costs))
        if c <= budget + 1e-9:
            best = max(best, sum(m * x for m, x in zip(mask, scores)))
    return best


def test_classic_knapsack_hand_example():
    # values 60,100,120  weights 10,20,30  budget 50 -> optimum 220 (items 2+3), greedy-by-ratio gives 160
    d = items([10, 20, 30], [60, 100, 120])
    r = optimize_portfolio(d, 50)
    assert r.total_value == pytest.approx(220)
    assert set(r.selected_ids) == {"I1", "I2"}
    assert r.total_cost == 50 and r.remaining == 0 and r.utilization == pytest.approx(100)


def test_rank_first_is_not_optimal():
    # best-ranked item (score 90, cost 60) blocks two items worth 70+70 at cost 50+50 (budget 100)
    d = items([60, 50, 50], [90, 70, 70])
    opt, gr = optimize_portfolio(d, 100), greedy_by_rank(d, 100)
    assert gr.total_value == 90 and gr.selected_ids == ["I0"]
    assert opt.total_value == pytest.approx(140) and set(opt.selected_ids) == {"I1", "I2"}
    assert opt.total_value > gr.total_value


@pytest.mark.parametrize("seed", range(10))
def test_matches_brute_force_and_respects_budget(seed):
    rng = np.random.default_rng(seed)
    n = 10
    costs = np.round(rng.uniform(1, 20, n), 1)
    scores = np.round(rng.uniform(10, 90, n), 1)
    budget = float(np.round(costs.sum() * rng.uniform(0.2, 0.7), 1))
    d = items(costs, scores)
    r = optimize_portfolio(d, budget)
    assert r.total_cost <= budget + 1e-9                      # feasibility
    assert r.total_value == pytest.approx(brute(costs, scores, budget), abs=1e-6)
    # DP cross-check
    x = _dp_knapsack(costs, scores, budget)
    assert scores[x].sum() == pytest.approx(r.total_value, abs=1e-6)
    assert costs[x].sum() <= budget + 1e-9


def test_zero_budget_gives_empty_portfolio():
    r = optimize_portfolio(items([5, 6], [50, 60]), 0)
    assert r.n_selected == 0 and r.status == "empty" and r.utilization == 0


def test_budget_covers_everything():
    r = optimize_portfolio(items([5, 6], [50, 60]), 1000)
    assert r.n_selected == 2 and r.remaining == pytest.approx(989)


def test_budget_smaller_than_every_cost():
    r = optimize_portfolio(items([5, 6], [50, 60]), 4)
    assert r.status == "empty" and "affordable" in r.message


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), "abc", None])
def test_invalid_budget_handled(bad):
    r = optimize_portfolio(items([5, 6], [50, 60]), bad)
    assert r.status == "invalid" and r.n_selected == 0


def test_invalid_costs_handled():
    r = optimize_portfolio(items([5, -6], [50, 60]), 10)
    assert r.status == "invalid"
    r = optimize_portfolio(items([5, float("nan")], [50, 60]), 10)
    assert r.status == "invalid"


def test_explanations_cover_every_initiative_and_mention_budget_for_rejected():
    d = items([60, 50, 50], [90, 70, 70])
    opt, gr = optimize_portfolio(d, 100), greedy_by_rank(d, 100)
    e = explain_decisions(d, opt, gr)
    assert len(e) == 3
    rej = e[e["Decision"] == "Rejected"].iloc[0]
    assert rej[COL_ID] == "I0" and "exceed the budget" in rej["Explanation"]
    assert rej["Rank"] == 1                                    # highest ranked, still rejected


def test_equal_scores_still_feasible():
    r = optimize_portfolio(items([3, 3, 3, 3], [10, 10, 10, 10]), 7)
    assert r.total_cost <= 7 and r.n_selected == 2
