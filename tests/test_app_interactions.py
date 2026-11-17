"""End-to-end UI behaviour through the real multipage entry point (app.py)."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGE = {"dash": "pages/1_Executive_Dashboard.py", "data": "pages/2_Data_Management.py",
        "crit": "pages/3_Criteria_Weighting.py", "dec": "pages/5_Decision_Analysis.py",
        "scen": "pages/6_Scenario_Sensitivity.py", "rep": "pages/7_Decision_Report.py"}


def app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


def go(at, key):
    return at.switch_page(PAGE[key]).run()


def button(at, label):
    return next(b for b in at.button if label in b.label)


def test_ahp_default_equal_judgements_apply_equal_weights():
    at = go(app(), "crit")
    button(at, "Apply AHP weights").click().run()
    assert not at.exception
    assert at.session_state["weight_source"] == "AHP"
    w = at.session_state["ahp_weights"]
    assert sum(w.values()) == pytest.approx(1) and all(v == pytest.approx(0.2) for v in w.values())


def test_consistent_judgements_button_gives_acceptable_cr_and_non_equal_weights():
    at = go(app(), "crit")
    button(at, "consistent with proposed").click().run()
    button(at, "Apply AHP weights").click().run()
    assert not at.exception
    assert at.session_state["ahp_cr"] < 0.10
    w = at.session_state["ahp_weights"]
    assert w["Strategic Alignment"] > w["Risk Assessment"]


def test_inconsistent_judgements_warn_and_block_apply():
    at = go(app(), "crit")
    at.select_slider(key="ahp_0_1").set_value(8)     # A >> B
    at.select_slider(key="ahp_1_2").set_value(8)     # B >> C
    at.select_slider(key="ahp_0_2").set_value(-8)    # C >> A  (cycle)
    at.run()
    assert not at.exception
    assert any("inconsistent" in w.value for w in at.warning)
    assert button(at, "Apply AHP weights").disabled
    assert not at.session_state["ahp_weights"]


def test_manual_weights_flow_into_results():
    at = go(app(), "crit")
    at.radio[0].set_value("Manual").run()
    at.number_input(key="mw_Risk Assessment").set_value(60.0).run()
    assert at.session_state["manual_weights"]["Risk Assessment"] == 60.0
    at = go(at, "dec")
    assert not at.exception
    assert any("Risk Assessment: 4" in c.value or "Risk Assessment: 5" in c.value or "Risk Assessment: 6" in c.value
               for c in at.caption)      # 60/(100-15+60)=41.4% -> shown as 41.4%


def test_budget_change_recalculates_decision_page():
    at = app()
    at.number_input(key="budget_input").set_value(20.0).run()
    at = go(at, "dec")
    assert not at.exception
    assert at.session_state["budget"] == 20.0
    html = " ".join(m.value for m in at.markdown)
    assert "20.00" in html


def test_zero_budget_does_not_crash():
    at = app()
    at.number_input(key="budget_input").set_value(0.0).run()
    for k in ("dash", "dec", "rep"):
        at = go(at, k)
        assert not at.exception, k


def test_standard_scenarios_created_and_new_scenario_saved():
    at = go(app(), "scen")
    assert set(at.session_state["scenarios"]) == {"Base", "Growth-Oriented", "Risk-Averse"}
    sb = next(s for s in at.selectbox if s.label == "Scenario")
    sb.set_value("+ New scenario").run()
    at.text_input[0].set_value("Stress test")           # form values are committed on submit
    next(b for b in at.button if b.label == "Save scenario").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Stress test" in at.session_state["scenarios"]
    assert len(at.session_state["scenarios"]) == 4


def test_invalid_scenario_rejected():
    at = go(app(), "scen")
    next(s for s in at.selectbox if s.label == "Scenario").set_value("+ New scenario").run()
    for c in ("Strategic Alignment", "Financial Attractiveness", "Business Impact", "Implementation Feasibility", "Risk Assessment"):
        at.number_input(key=f"sf_+ New scenario_{c}").set_value(0.0)
    next(b for b in at.button if b.label == "Save scenario").click().run()
    assert any("greater than zero" in e.value for e in at.error)
    assert len(at.session_state["scenarios"]) == 3


def test_sensitivity_slider_changes_ranking_table():
    at = go(app(), "scen")
    at.slider(key="sens_Risk Assessment").set_value(200).run()
    assert not at.exception
    assert any("change rank" in m.value for m in at.markdown)
    txt = next(m.value for m in at.markdown if "change rank" in m.value)
    assert not txt.startswith("**0**")          # at +200 % on risk weight, ranks must move


def test_report_page_has_downloads():
    at = go(app(), "rep")
    assert not at.exception
    assert len(at.get("download_button")) == 2
