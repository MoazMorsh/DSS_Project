"""Streamlit session-state helpers shared by all pages.

Session state lives only in the user's browser session (it is NOT saved on the
server). Export data/reports if you need to keep them.
"""
from dataclasses import dataclass
import streamlit as st
import pandas as pd

from .schema import CRITERIA_NAMES, DEFAULT_WEIGHTS, DEFAULT_SCALE_MAX
from .data_processing import load_sample
from .validation import validate_initiatives, validate_budget
from .weighted_scoring import compute_scores, default_sub_weights, ScoringResult
from .optimization import optimize_portfolio, greedy_by_rank, PortfolioResult

WEIGHT_SOURCES = ["Default (proposed)", "Manual", "AHP"]


def init_state():
    ss = st.session_state
    if ss.get("initialized"):
        return
    ss.scale_max = DEFAULT_SCALE_MAX
    ss.df_version = 0
    ss.weight_source = WEIGHT_SOURCES[0]
    ss.manual_weights = {c: DEFAULT_WEIGHTS[c] * 100 for c in CRITERIA_NAMES}   # percent
    ss.ahp_judgments = {}            # (i, j) -> signed Saaty integer -8..8
    ss.ahp_weights = None            # dict, set when the user applies AHP weights
    ss.ahp_cr = None
    ss.sub_weights = default_sub_weights()
    ss.scenarios = {}
    ss.scenario_signature = None
    res = validate_initiatives(load_sample(), ss.scale_max)
    ss.df = res.data
    ss.data_source = "Illustrative sample dataset (fictional)"
    ss.budget = float(round(ss.df["Estimated Cost"].sum() * 0.5))
    ss.initialized = True


def set_data(df: pd.DataFrame, source: str):
    st.session_state.df = df
    st.session_state.data_source = source
    st.session_state.df_version += 1
    st.session_state.scenarios = {}      # scenarios depend on the data -> rebuild


def set_budget(value: float):
    """Change the budget from page code; the sidebar widget picks it up on the next run."""
    st.session_state.budget = float(value)
    st.session_state.pending_budget = float(value)


def require_data():
    if st.session_state.get("df") is None or len(st.session_state.df) == 0:
        st.warning("No initiative data loaded. Go to **Data Management** and load the sample dataset or upload a file.")
        st.stop()


def active_weights():
    """(weights dict normalised to 1, source label, note)."""
    ss = st.session_state
    src = ss.weight_source
    note = ""
    if src == "AHP":
        if ss.ahp_weights:
            return dict(ss.ahp_weights), "AHP", note
        note = "AHP weights have not been applied yet - using the default proposed weights."
        src = WEIGHT_SOURCES[0]
    if src == "Manual":
        raw = {c: float(ss.manual_weights.get(c, 0)) for c in CRITERIA_NAMES}
        tot = sum(raw.values())
        if tot > 0 and all(v >= 0 for v in raw.values()):
            return {c: v / tot for c, v in raw.items()}, "Manual", note
        note = "Manual weights are invalid - using the default proposed weights."
    return dict(DEFAULT_WEIGHTS), "Default (proposed)", note


@dataclass
class Analysis:
    scoring: ScoringResult
    optimal: PortfolioResult
    greedy: PortfolioResult
    weights: dict
    source: str
    note: str
    budget: float


def get_analysis() -> Analysis:
    ss = st.session_state
    weights, source, note = active_weights()
    scoring = compute_scores(ss.df, weights, ss.sub_weights, ss.scale_max)
    budget_errors = validate_budget(ss.budget)
    budget = float(ss.budget) if not budget_errors else 0.0
    return Analysis(scoring, optimize_portfolio(scoring.summary, budget),
                    greedy_by_rank(scoring.summary, budget), weights, source, note, budget)
