"""Sensitivity analysis on criterion weights - everything is recomputed from real inputs."""
import numpy as np
import pandas as pd

from .schema import COL_ID, COL_NAME, CRITERIA_NAMES, DEFAULT_SCALE_MAX
from .weighted_scoring import compute_scores, normalize_weights
from .optimization import optimize_portfolio

UNSTABLE_RANGE = 3   # an initiative whose rank moves by >= this many places is flagged unstable


def adjust_weights(weights: dict, pct_changes: dict) -> dict:
    """Apply relative % changes (e.g. +30 -> x1.30; -100 -> 0), then renormalise to sum 1."""
    base = normalize_weights(weights)
    raw = {}
    for c in CRITERIA_NAMES:
        factor = 1.0 + float(pct_changes.get(c, 0.0)) / 100.0
        raw[c] = max(base[c] * factor, 0.0)
    if sum(raw.values()) <= 0:
        raise ValueError("All weights are zero after adjustment.")
    return normalize_weights(raw)


def compare_ranking(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """Before/after table. Positive 'Rank change' = moved UP the ranking."""
    b = before.set_index(COL_ID)[[COL_NAME, "Final Score", "Rank"]]
    a = after.set_index(COL_ID)[["Final Score", "Rank"]]
    out = b.join(a, lsuffix=" (before)", rsuffix=" (after)")
    out["Rank change"] = out["Rank (before)"] - out["Rank (after)"]
    out["Score change"] = out["Final Score (after)"] - out["Final Score (before)"]
    return out.reset_index().sort_values("Rank (after)")


def _scores(df, w, sub_weights, scale_max):
    return compute_scores(df, w, sub_weights, scale_max).summary.set_index(COL_ID)


def one_at_a_time(df, weights, steps=(-50, -25, 25, 50), sub_weights=None,
                  scale_max=DEFAULT_SCALE_MAX, budget=None) -> dict:
    """Vary each criterion weight alone by each % step (others rescale automatically).

    Returns:
      runs      long table: criterion, change %, initiative, rank
      stability per initiative: base rank, min/max rank, range, unstable flag, (selection frequency)
      influence per criterion: mean / max absolute rank shift (bigger = more influential)
    """
    base = _scores(df, weights, sub_weights, scale_max)
    base_rank = base["Rank"]
    records, selections = [], []
    for c in CRITERIA_NAMES:
        for s in steps:
            w = adjust_weights(weights, {c: s})
            sc = _scores(df, w, sub_weights, scale_max)
            for i, r in sc["Rank"].items():
                records.append({"Criterion": c, "Change (%)": s, COL_ID: i, "Rank": int(r)})
            if budget is not None:
                p = optimize_portfolio(sc.reset_index(), budget)
                selections.append(set(p.selected_ids))
    runs = pd.DataFrame(records)

    names = df.set_index(COL_ID)[COL_NAME]
    g = runs.groupby(COL_ID)["Rank"]
    stab = pd.DataFrame({COL_NAME: names, "Base rank": base_rank,
                         "Best rank": g.min(), "Worst rank": g.max()})
    stab["Rank range"] = stab["Worst rank"] - stab["Best rank"]
    stab["Unstable"] = stab["Rank range"] >= UNSTABLE_RANGE
    if budget is not None and selections:
        stab["Selection frequency (%)"] = [
            100.0 * sum(i in s for s in selections) / len(selections) for i in stab.index]
    stab = stab.reset_index().sort_values("Base rank")

    shifts = runs.merge(base_rank.rename("base").reset_index(), on=COL_ID)
    shifts["abs_shift"] = (shifts["Rank"] - shifts["base"]).abs()
    infl = shifts.groupby("Criterion")["abs_shift"].agg(["mean", "max"]).reindex(CRITERIA_NAMES)
    infl.columns = ["Mean absolute rank shift", "Max rank shift"]
    infl = infl.reset_index().sort_values("Mean absolute rank shift", ascending=False)
    return {"runs": runs, "stability": stab, "influence": infl}


def random_weight_simulation(df, weights, budget, n=200, spread=30.0, seed=42,
                             sub_weights=None, scale_max=DEFAULT_SCALE_MAX) -> pd.DataFrame:
    """Randomly perturb every weight by up to +/- spread % (seeded, reproducible)."""
    rng = np.random.default_rng(seed)
    counts = pd.Series(0, index=df[COL_ID], dtype=float)
    ranks = {i: [] for i in df[COL_ID]}
    for _ in range(n):
        ch = {c: rng.uniform(-spread, spread) for c in CRITERIA_NAMES}
        sc = _scores(df, adjust_weights(weights, ch), sub_weights, scale_max)
        for i, r in sc["Rank"].items():
            ranks[i].append(int(r))
        counts[optimize_portfolio(sc.reset_index(), budget).selected_ids] += 1
    out = pd.DataFrame({
        COL_ID: list(ranks), COL_NAME: df.set_index(COL_ID).loc[list(ranks), COL_NAME].values,
        "Mean rank": [np.mean(v) for v in ranks.values()],
        "Best rank": [min(v) for v in ranks.values()],
        "Worst rank": [max(v) for v in ranks.values()],
        "Selection frequency (%)": counts.reindex(list(ranks)).values / n * 100.0})
    return out.sort_values("Mean rank").reset_index(drop=True)
