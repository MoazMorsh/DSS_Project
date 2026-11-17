"""Input validation. Never raises on bad user data - returns messages instead."""
from dataclasses import dataclass, field
from typing import Optional
import math

import pandas as pd

from .schema import (ALL_COLUMNS, REQUIRED_COLUMNS, OPTIONAL_COLUMNS, QUAL_COLUMNS,
                     QUANT_COLUMNS, COL_ID, COL_NAME, COL_COST, COL_PAYBACK,
                     CRITERIA_NAMES, DEFAULT_SCALE_MAX)

MAX_MESSAGES_PER_COLUMN = 5


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    data: Optional[pd.DataFrame] = None   # cleaned data, only when there are no errors

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _match_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns case/space-insensitively to the canonical names."""
    lookup = {c.strip().lower(): c for c in ALL_COLUMNS}
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in lookup:
            rename[col] = lookup[key]
    return df.rename(columns=rename)


def validate_initiatives(df: pd.DataFrame, scale_max: int = DEFAULT_SCALE_MAX) -> ValidationResult:
    """Validate and clean an initiatives table."""
    res = ValidationResult()
    if df is None or len(df) == 0:
        res.errors.append("The table is empty: add at least one initiative.")
        return res

    df = _match_columns(df.copy())
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        res.errors.append("Missing required column(s): " + ", ".join(missing))
        return res

    for c in OPTIONAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    extra = [c for c in df.columns if c not in ALL_COLUMNS]
    if extra:
        res.warnings.append("Ignored unrecognised column(s): " + ", ".join(map(str, extra)))
    df = df[ALL_COLUMNS].copy()

    # drop completely empty rows (common at the bottom of Excel sheets)
    df = df.dropna(how="all").reset_index(drop=True)
    if df.empty:
        res.errors.append("The table contains no data rows.")
        return res

    def xl_row(i):  # Excel row number (header = row 1)
        return i + 2

    # ---- text columns --------------------------------------------------
    for col in (COL_ID, COL_NAME):
        blank = df[col].isna() | (df[col].astype(str).str.strip() == "")
        for i in df.index[blank][:MAX_MESSAGES_PER_COLUMN]:
            res.errors.append(f"Row {xl_row(i)}: '{col}' is missing.")
    df[COL_ID] = df[COL_ID].astype(str).str.strip()
    df[COL_NAME] = df[COL_NAME].astype(str).str.strip()
    for c in OPTIONAL_COLUMNS:
        df[c] = df[c].fillna("").astype(str)
    dups = df.loc[df[COL_ID].duplicated(keep=False) & (df[COL_ID] != ""), COL_ID].unique()
    if len(dups):
        res.errors.append("Duplicate Initiative ID(s): " + ", ".join(map(str, dups)))

    # ---- numeric columns -----------------------------------------------
    numeric_cols = [COL_COST] + QUANT_COLUMNS + QUAL_COLUMNS
    for col in numeric_cols:
        raw = df[col]
        num = pd.to_numeric(raw, errors="coerce")
        bad = num.isna()
        for i in df.index[bad][:MAX_MESSAGES_PER_COLUMN]:
            what = "missing" if pd.isna(raw[i]) or str(raw[i]).strip() == "" else f"not a number ('{raw[i]}')"
            res.errors.append(f"Row {xl_row(i)}: '{col}' is {what}.")
        if bad.sum() > MAX_MESSAGES_PER_COLUMN:
            res.errors.append(f"'{col}': {int(bad.sum()) - MAX_MESSAGES_PER_COLUMN} more invalid value(s).")
        inf = num.apply(lambda v: isinstance(v, float) and math.isinf(v))
        for i in df.index[inf][:MAX_MESSAGES_PER_COLUMN]:
            res.errors.append(f"Row {xl_row(i)}: '{col}' must be finite.")
        df[col] = num

        ok = num.notna() & ~inf
        if col == COL_COST:
            for i in df.index[ok & (num <= 0)][:MAX_MESSAGES_PER_COLUMN]:
                res.errors.append(f"Row {xl_row(i)}: '{col}' must be greater than 0.")
        elif col == COL_PAYBACK:
            for i in df.index[ok & (num <= 0)][:MAX_MESSAGES_PER_COLUMN]:
                res.errors.append(f"Row {xl_row(i)}: '{col}' must be greater than 0.")
        elif col in QUAL_COLUMNS:
            out = ok & ((num < 1) | (num > scale_max))
            for i in df.index[out][:MAX_MESSAGES_PER_COLUMN]:
                res.errors.append(f"Row {xl_row(i)}: '{col}' = {num[i]:g} is outside the 1-{scale_max} scale.")
            frac = ok & ~out & ((num - num.round()).abs() > 1e-9)
            if frac.any():
                res.warnings.append(f"'{col}' contains non-integer scores (allowed, but check intent).")

    # ---- plausibility warnings -----------------------------------------
    if COL_COST in df and df[COL_COST].notna().all() and len(df) < 3:
        res.warnings.append("Fewer than 3 initiatives: ranking and optimisation will be trivial.")

    if res.errors:
        return res
    res.data = df.reset_index(drop=True)
    return res


def validate_weights(weights: dict) -> list:
    """Return a list of error strings (empty if the weights are usable)."""
    errs = []
    for c in CRITERIA_NAMES:
        if c not in weights:
            errs.append(f"Weight for '{c}' is missing.")
            continue
        w = weights[c]
        if w is None or not isinstance(w, (int, float)) or math.isnan(w) or math.isinf(w):
            errs.append(f"Weight for '{c}' is not a valid number.")
        elif w < 0:
            errs.append(f"Weight for '{c}' cannot be negative.")
    if not errs and sum(weights[c] for c in CRITERIA_NAMES) <= 0:
        errs.append("At least one weight must be greater than zero.")
    return errs


def validate_budget(budget) -> list:
    """Return a list of error strings for the available budget."""
    try:
        b = float(budget)
    except (TypeError, ValueError):
        return ["Budget must be a number."]
    if math.isnan(b) or math.isinf(b):
        return ["Budget must be a finite number."]
    if b < 0:
        return ["Budget cannot be negative."]
    return []
