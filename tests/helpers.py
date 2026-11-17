"""Small hand-made datasets whose answers can be verified on paper."""
import pandas as pd
from core.schema import ALL_COLUMNS, COL_ID, COL_NAME, COL_COST, COL_ROI, COL_NPV, COL_PAYBACK, COL_DESC, COL_FUNC, ALL_SUBCRITERIA


def make_df(rows):
    """rows: list of dicts with overrides on top of a neutral all-3 / mid-value initiative."""
    base = {COL_DESC: "", COL_FUNC: "", COL_COST: 10.0, COL_ROI: 20.0, COL_NPV: 5.0, COL_PAYBACK: 3.0}
    for s in ALL_SUBCRITERIA:
        base.setdefault(s.label, 3)
    out = []
    for k, r in enumerate(rows, 1):
        d = dict(base)
        d.update({COL_ID: f"I{k}", COL_NAME: f"Init {k}"})
        d.update(r)
        out.append(d)
    return pd.DataFrame(out)[ALL_COLUMNS]


def best_row(**kw):
    """Best possible on every criterion (benefit=5, risk/complexity=1)."""
    r = {s.label: (5 if s.direction == "benefit" else 1) for s in ALL_SUBCRITERIA if s.kind == "qual"}
    r.update({COL_ROI: 40.0, COL_NPV: 20.0, COL_PAYBACK: 1.0})
    r.update(kw)
    return r


def worst_row(**kw):
    r = {s.label: (1 if s.direction == "benefit" else 5) for s in ALL_SUBCRITERIA if s.kind == "qual"}
    r.update({COL_ROI: 5.0, COL_NPV: 1.0, COL_PAYBACK: 8.0})
    r.update(kw)
    return r
