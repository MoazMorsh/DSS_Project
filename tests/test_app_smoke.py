"""Headless UI smoke tests: every page must render without exceptions and react to inputs."""
import pytest
from streamlit.testing.v1 import AppTest

PAGES = ["pages/1_Executive_Dashboard.py", "pages/2_Data_Management.py", "pages/3_Criteria_Weighting.py",
         "pages/4_Initiative_Evaluation.py", "pages/5_Decision_Analysis.py",
         "pages/6_Scenario_Sensitivity.py", "pages/7_Decision_Report.py"]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parent.parent / page), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]


def test_budget_change_recalculates_dashboard():
    from pathlib import Path
    f = str(Path(__file__).resolve().parent.parent / "pages/1_Executive_Dashboard.py")
    at = AppTest.from_file(f, default_timeout=90).run()
    at.session_state["budget"] = 30.0
    at.run()
    assert not at.exception
    html = " ".join(m.value for m in at.markdown)
    assert "30.0" in html
