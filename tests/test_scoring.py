import pytest
import pandas as pd
from core.schema import *
from core.weighted_scoring import (normalize_qualitative, normalize_minmax, compute_scores,
                                   compute_normalized, normalize_weights)
from tests.helpers import make_df, best_row, worst_row


def test_qualitative_benefit_normalisation():
    s = normalize_qualitative([1, 2, 3, 4, 5], "benefit")
    assert list(s) == [0, 25, 50, 75, 100]


def test_qualitative_cost_normalisation_inverts():
    s = normalize_qualitative([1, 3, 5], "cost")
    assert list(s) == [100, 50, 0]


def test_configurable_scale():
    assert list(normalize_qualitative([1, 7, 10], "benefit", scale_max=10)) == pytest.approx([0, 66.6666667, 100])


def test_minmax_benefit_and_cost():
    assert list(normalize_minmax([10, 20, 30], "benefit")) == [0, 50, 100]
    assert list(normalize_minmax([1, 2, 5], "cost")) == pytest.approx([100, 75, 0])   # payback: shorter is better


def test_minmax_constant_column_is_neutral():
    assert list(normalize_minmax([7, 7, 7], "benefit")) == [50, 50, 50]


def test_risk_direction_low_risk_scores_higher():
    df = make_df([{"Financial Risk": 1}, {"Financial Risk": 5}])
    n = compute_normalized(df)
    assert n.loc[0, "Financial Risk"] == 100 and n.loc[1, "Financial Risk"] == 0


def test_risk_is_never_a_negative_contribution():
    df = make_df([best_row(), worst_row()])
    r = compute_scores(df, DEFAULT_WEIGHTS).summary
    contrib_cols = [c for c in r.columns if c.endswith("(contribution)")]
    assert (r[contrib_cols] >= 0).all().all()


def test_best_vs_worst_scores_0_100():
    df = make_df([best_row(), worst_row()])
    s = compute_scores(df, DEFAULT_WEIGHTS).summary.set_index(COL_ID)
    assert s.loc["I1", "Final Score"] == pytest.approx(100)
    assert s.loc["I2", "Final Score"] == pytest.approx(0)
    assert s.loc["I1", "Rank"] == 1 and s.loc["I2", "Rank"] == 2


def test_hand_calculated_example():
    # I1: every 1-5 rating is 4 (->75) except risks 2 (->75); financial quant is best (100)
    # => Strategic 75, Financial 100, Impact 75, Feasibility 75, Risk 75
    r1 = {s.label: (4 if s.direction == "benefit" else 2) for s in ALL_SUBCRITERIA if s.kind == "qual"}
    r1.update({COL_ROI: 30.0, COL_NPV: 10.0, COL_PAYBACK: 1.0})
    r2 = {COL_ROI: 10.0, COL_NPV: 2.0, COL_PAYBACK: 5.0}      # other rows neutral (3 -> 50) / worst financial
    df = make_df([r1, r2])
    res = compute_scores(df, DEFAULT_WEIGHTS)
    s = res.summary.set_index(COL_ID)
    expected = 0.25 * 75 + 0.25 * 100 + 0.20 * 75 + 0.15 * 75 + 0.15 * 75   # = 81.25
    assert s.loc["I1", "Final Score"] == pytest.approx(expected)
    assert s.loc["I2", "Final Score"] == pytest.approx(0.25 * 50 + 0 + 0.20 * 50 + 0.15 * 50 + 0.15 * 50)  # 47.5


def test_contributions_sum_to_final_score():
    df = make_df([best_row(), worst_row(), {}])
    s = compute_scores(df, DEFAULT_WEIGHTS).summary
    cols = [f"{c} (contribution)" for c in CRITERIA_NAMES]
    assert (s[cols].sum(axis=1) - s["Final Score"]).abs().max() < 1e-9


def test_weights_are_normalised():
    w = normalize_weights({c: 2 for c in CRITERIA_NAMES})
    assert sum(w.values()) == pytest.approx(1) and w["Risk Assessment"] == pytest.approx(0.2)
    df = make_df([best_row(), worst_row()])
    a = compute_scores(df, DEFAULT_WEIGHTS).summary["Final Score"]
    b = compute_scores(df, {c: v * 100 for c, v in DEFAULT_WEIGHTS.items()}).summary["Final Score"]
    assert a.tolist() == pytest.approx(b.tolist())


def test_weight_change_changes_ranking():
    a = best_row(**{COL_ROI: 40.0, COL_NPV: 20.0, COL_PAYBACK: 1.0})
    for s in ALL_SUBCRITERIA:
        if s.kind == "qual":
            a[s.label] = 3
    b = {s.label: (5 if s.direction == "benefit" else 1) for s in ALL_SUBCRITERIA if s.kind == "qual"}
    b.update({COL_ROI: 5.0, COL_NPV: 1.0, COL_PAYBACK: 8.0})      # strong qualitative, weak financial
    df = make_df([a, b])
    fin = {c: 0.01 for c in CRITERIA_NAMES}; fin["Financial Attractiveness"] = 0.96
    qual = {c: 0.24 for c in CRITERIA_NAMES}; qual["Financial Attractiveness"] = 0.04
    assert compute_scores(df, fin).summary.iloc[0][COL_ID] == "I1"
    assert compute_scores(df, qual).summary.iloc[0][COL_ID] == "I2"


def test_invalid_weights_rejected():
    df = make_df([{}])
    with pytest.raises(ValueError):
        compute_scores(df, {c: 0 for c in CRITERIA_NAMES})
    with pytest.raises(ValueError):
        compute_scores(df, {**DEFAULT_WEIGHTS, "Risk Assessment": -1})


def test_subcriterion_weights_used():
    df = make_df([{"Financial Risk": 1, "Operational Risk": 5, "Market & Execution Risk": 5},
                  {"Financial Risk": 5, "Operational Risk": 5, "Market & Execution Risk": 5}])
    only_fin = {"Risk Assessment": {"Financial Risk": 1, "Operational Risk": 0, "Market & Execution Risk": 0}}
    s = compute_scores(df, DEFAULT_WEIGHTS, only_fin).summary.set_index(COL_ID)
    assert s.loc["I1", "Risk Assessment"] == 100 and s.loc["I2", "Risk Assessment"] == 0
