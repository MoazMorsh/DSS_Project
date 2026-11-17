"""Weighted Sum Model with documented normalisation (all outputs on 0-100, higher = better)."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from .schema import (CRITERIA, CRITERIA_NAMES, COL_ID, COL_NAME, COL_FUNC, COL_COST,
                     DEFAULT_SCALE_MAX)
from .validation import validate_weights


def normalize_qualitative(values, direction: str, scale_max: int = DEFAULT_SCALE_MAX,
                          scale_min: int = 1) -> pd.Series:
    """Linear rescaling of a 1..N rating to 0..100.

    benefit: (x - min) / (max - min) * 100        (5 -> 100, 1 -> 0)
    cost   : (max - x) / (max - min) * 100        (risk 1 -> 100, risk 5 -> 0)
    """
    v = pd.Series(values, dtype=float)
    span = scale_max - scale_min
    if span <= 0:
        raise ValueError("scale_max must be greater than scale_min.")
    out = (v - scale_min) / span if direction == "benefit" else (scale_max - v) / span
    return out * 100.0


def normalize_minmax(values, direction: str) -> pd.Series:
    """Min-max rescaling across the evaluated initiatives to 0..100.

    benefit: (x - min) / (max - min) * 100
    cost   : (max - x) / (max - min) * 100
    If all values are equal the criterion cannot discriminate -> neutral 50.
    """
    v = pd.Series(values, dtype=float)
    lo, hi = v.min(), v.max()
    if hi - lo < 1e-12:
        return pd.Series(50.0, index=v.index)
    out = (v - lo) / (hi - lo) if direction == "benefit" else (hi - v) / (hi - lo)
    return out * 100.0


def normalize_weights(weights: dict) -> dict:
    errs = validate_weights(weights)
    if errs:
        raise ValueError("; ".join(errs))
    total = sum(weights[c] for c in CRITERIA_NAMES)
    return {c: weights[c] / total for c in CRITERIA_NAMES}


def default_sub_weights() -> dict:
    """Equal weights for the subcriteria inside each criterion."""
    return {c: {s.label: 1.0 / len(subs) for s in subs} for c, subs in CRITERIA.items()}


def compute_normalized(df: pd.DataFrame, scale_max: int = DEFAULT_SCALE_MAX) -> pd.DataFrame:
    """0-100 normalised score for every subcriterion (same index as df)."""
    out = pd.DataFrame(index=df.index)
    for subs in CRITERIA.values():
        for s in subs:
            if s.label not in df.columns:
                raise KeyError(f"Missing column '{s.label}'.")
            if df[s.label].isna().any():
                raise ValueError(f"Column '{s.label}' contains missing values.")
            out[s.label] = (normalize_qualitative(df[s.label], s.direction, scale_max)
                            if s.kind == "qual" else normalize_minmax(df[s.label], s.direction))
    return out


@dataclass
class ScoringResult:
    summary: pd.DataFrame      # ID, Name, Function, Cost, criterion scores, contributions, Final Score, Rank
    normalized: pd.DataFrame   # subcriterion-level 0-100 scores (with ID/Name)
    weights: dict              # normalised criterion weights actually used


def compute_scores(df: pd.DataFrame, weights: dict, sub_weights: dict = None,
                   scale_max: int = DEFAULT_SCALE_MAX) -> ScoringResult:
    """Final Score_i = sum_c ( w_c * S_ic ),  S_ic = sum_s ( v_cs * norm_ics )."""
    w = normalize_weights(weights)
    sub_weights = sub_weights or default_sub_weights()
    norm = compute_normalized(df, scale_max)

    summary = pd.DataFrame({COL_ID: df[COL_ID].values, COL_NAME: df[COL_NAME].values})
    if COL_FUNC in df.columns:
        summary[COL_FUNC] = df[COL_FUNC].values
    summary[COL_COST] = df[COL_COST].values

    crit_scores, contribs = {}, {}
    for c, subs in CRITERIA.items():
        sw = np.array([sub_weights.get(c, {}).get(s.label, 1.0 / len(subs)) for s in subs], float)
        if (sw < 0).any() or sw.sum() <= 0:
            raise ValueError(f"Invalid subcriteria weights for '{c}'.")
        sw = sw / sw.sum()
        score = sum(norm[s.label].values * x for s, x in zip(subs, sw))
        crit_scores[c] = score
        contribs[c] = score * w[c]
        summary[c] = score
    for c in CRITERIA_NAMES:
        summary[f"{c} (contribution)"] = contribs[c]
    summary["Final Score"] = sum(contribs.values())
    summary["Rank"] = summary["Final Score"].round(9).rank(ascending=False, method="min").astype(int)
    summary = summary.sort_values(["Rank", COL_ID]).reset_index(drop=True)

    norm_out = norm.copy()
    norm_out.insert(0, COL_NAME, df[COL_NAME].values)
    norm_out.insert(0, COL_ID, df[COL_ID].values)
    return ScoringResult(summary, norm_out, w)
