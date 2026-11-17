import pytest
from core.schema import *
from core.scenario_analysis import (Scenario, run_scenario, default_scenarios, compare_scenarios,
                                    validate_scenario)
from core.sensitivity_analysis import (adjust_weights, compare_ranking, one_at_a_time,
                                       random_weight_simulation)
from core.weighted_scoring import compute_scores
from core.data_processing import sample_dataframe


@pytest.fixture(scope="module")
def df():
    return sample_dataframe()


def test_default_scenarios_exist_and_weights_sum_to_one(df):
    sc = default_scenarios(DEFAULT_WEIGHTS, 70)
    assert set(sc) == {"Base", "Growth-Oriented", "Risk-Averse"}
    for s in sc.values():
        assert sum(s.weights.values()) == pytest.approx(1)
    assert sc["Growth-Oriented"].budget > sc["Base"].budget > sc["Risk-Averse"].budget


def test_scenario_recalculation_respects_each_budget(df):
    res = {n: run_scenario(df, s) for n, s in default_scenarios(DEFAULT_WEIGHTS, 70).items()}
    for n, r in res.items():
        assert r.optimal.total_cost <= r.scenario.budget + 1e-9
        assert r.optimal.total_value >= r.greedy.total_value - 1e-9
    comp = compare_scenarios(res)["summary"]
    assert len(comp) == 3
    assert comp.set_index("Scenario").loc["Growth-Oriented", "Total investment"] >= \
        comp.set_index("Scenario").loc["Risk-Averse", "Total investment"] - 1e-9


def test_base_scenario_equals_direct_calculation(df):
    r = run_scenario(df, default_scenarios(DEFAULT_WEIGHTS, 70)["Base"])
    direct = compute_scores(df, DEFAULT_WEIGHTS).summary
    assert r.scores["Final Score"].tolist() == pytest.approx(direct["Final Score"].tolist())


def test_cost_multiplier_and_exclusion(df):
    s = Scenario("x", 70, DEFAULT_WEIGHTS, cost_multiplier=2.0, excluded_ids=["INI-01"])
    r = run_scenario(df, s)
    assert "INI-01" not in r.scores[COL_ID].tolist() and len(r.scores) == 14
    assert r.scores[COL_COST].sum() == pytest.approx((df[COL_COST].sum() - 18.0) * 2)


def test_invalid_scenarios_rejected(df):
    assert validate_scenario(Scenario("x", -1, DEFAULT_WEIGHTS))
    assert validate_scenario(Scenario("x", 10, {c: 0 for c in CRITERIA_NAMES}))
    assert validate_scenario(Scenario("x", 10, DEFAULT_WEIGHTS, cost_multiplier=0))
    with pytest.raises(ValueError):
        run_scenario(df, Scenario("x", 10, DEFAULT_WEIGHTS, excluded_ids=df[COL_ID].tolist()))


def test_adjust_weights_normalises_and_directionally_correct():
    w = adjust_weights(DEFAULT_WEIGHTS, {"Risk Assessment": 100})
    assert sum(w.values()) == pytest.approx(1)
    assert w["Risk Assessment"] > DEFAULT_WEIGHTS["Risk Assessment"]
    assert w["Strategic Alignment"] < DEFAULT_WEIGHTS["Strategic Alignment"]
    z = adjust_weights(DEFAULT_WEIGHTS, {"Risk Assessment": -100})
    assert z["Risk Assessment"] == 0
    assert adjust_weights(DEFAULT_WEIGHTS, {}) == pytest.approx(DEFAULT_WEIGHTS)
    with pytest.raises(ValueError):
        adjust_weights(DEFAULT_WEIGHTS, {c: -100 for c in CRITERIA_NAMES})


def test_compare_ranking_sign_convention(df):
    before = compute_scores(df, DEFAULT_WEIGHTS).summary
    after = compute_scores(df, adjust_weights(DEFAULT_WEIGHTS, {"Risk Assessment": 300})).summary
    t = compare_ranking(before, after)
    assert (t["Rank change"] == t["Rank (before)"] - t["Rank (after)"]).all()
    assert t["Rank change"].abs().sum() > 0              # something moved


def test_one_at_a_time_outputs_are_calculated(df):
    out = one_at_a_time(df, DEFAULT_WEIGHTS, budget=70)
    assert len(out["runs"]) == 5 * 4 * 15
    st = out["stability"]
    assert (st["Rank range"] >= 0).all()
    assert (st["Rank range"] == st["Worst rank"] - st["Best rank"]).all()
    assert st["Selection frequency (%)"].between(0, 100).all()
    assert (out["influence"]["Mean absolute rank shift"] >= 0).all()
    assert out["influence"]["Mean absolute rank shift"].is_monotonic_decreasing


def test_zero_step_gives_no_instability(df):
    out = one_at_a_time(df, DEFAULT_WEIGHTS, steps=(0,))
    assert (out["stability"]["Rank range"] == 0).all()


def test_random_simulation_reproducible(df):
    a = random_weight_simulation(df, DEFAULT_WEIGHTS, 70, n=15, seed=1)
    b = random_weight_simulation(df, DEFAULT_WEIGHTS, 70, n=15, seed=1)
    assert a.equals(b)
    assert a["Selection frequency (%)"].between(0, 100).all()
