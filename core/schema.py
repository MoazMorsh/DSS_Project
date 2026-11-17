"""Central data schema: column names, criteria hierarchy and score definitions.

Every other module imports names from here so that a column is only ever
spelled in ONE place.
"""
from dataclasses import dataclass

# ---- identification / descriptive columns -------------------------------
COL_ID = "Initiative ID"
COL_NAME = "Initiative Name"
COL_DESC = "Description"
COL_FUNC = "Business Function"

# ---- financial inputs (quantitative) -------------------------------------
COL_COST = "Estimated Cost"            # investment, in currency units (millions)
COL_ROI = "Expected ROI (%)"
COL_NPV = "NPV"                        # same currency units as cost
COL_PAYBACK = "Payback Period (Years)"


@dataclass(frozen=True)
class Subcriterion:
    """One evaluation subcriterion (= one input column)."""
    label: str      # also the DataFrame column name
    kind: str       # "qual" (1..N scale) or "quant" (numeric, min-max scaled)
    direction: str  # "benefit" (higher is better) or "cost" (lower is better)


CRITERIA = {
    "Strategic Alignment": (
        Subcriterion("Alignment with Corporate Objectives", "qual", "benefit"),
        Subcriterion("Contribution to Long-term Strategy", "qual", "benefit"),
        Subcriterion("Competitive Advantage", "qual", "benefit"),
    ),
    "Financial Attractiveness": (
        Subcriterion(COL_ROI, "quant", "benefit"),
        Subcriterion(COL_NPV, "quant", "benefit"),
        Subcriterion(COL_PAYBACK, "quant", "cost"),      # shorter payback = better
    ),
    "Business Impact": (
        Subcriterion("Revenue Growth Potential", "qual", "benefit"),
        Subcriterion("Customer Impact", "qual", "benefit"),
        Subcriterion("Operational Efficiency", "qual", "benefit"),
    ),
    "Implementation Feasibility": (
        Subcriterion("Resource Availability", "qual", "benefit"),
        Subcriterion("Technical Capability", "qual", "benefit"),
        Subcriterion("Implementation Complexity", "qual", "cost"),  # complex = worse
    ),
    "Risk Assessment": (
        Subcriterion("Financial Risk", "qual", "cost"),             # risky = worse
        Subcriterion("Operational Risk", "qual", "cost"),
        Subcriterion("Market & Execution Risk", "qual", "cost"),
    ),
}

CRITERIA_NAMES = list(CRITERIA.keys())

DEFAULT_WEIGHTS = {
    "Strategic Alignment": 0.25,
    "Financial Attractiveness": 0.25,
    "Business Impact": 0.20,
    "Implementation Feasibility": 0.15,
    "Risk Assessment": 0.15,
}

ALL_SUBCRITERIA = [s for subs in CRITERIA.values() for s in subs]
QUAL_COLUMNS = [s.label for s in ALL_SUBCRITERIA if s.kind == "qual"]
QUANT_COLUMNS = [s.label for s in ALL_SUBCRITERIA if s.kind == "quant"]

REQUIRED_COLUMNS = [COL_ID, COL_NAME, COL_COST] + [s.label for s in ALL_SUBCRITERIA]
OPTIONAL_COLUMNS = [COL_DESC, COL_FUNC]
ALL_COLUMNS = [COL_ID, COL_NAME, COL_DESC, COL_FUNC, COL_COST] + [
    s.label for s in ALL_SUBCRITERIA
]

DEFAULT_SCALE_MAX = 5

# ---- score definitions (what do the numbers 1..5 mean?) -------------------
SCORE_DEFINITIONS_BENEFIT = {
    1: "Very low - negligible / almost none",
    2: "Low - limited, below expectations",
    3: "Moderate - acceptable, meets minimum expectations",
    4: "High - strong, clearly above average",
    5: "Very high - outstanding, best-in-class",
}
SCORE_DEFINITIONS_RISK = {
    1: "Very low risk / very low complexity (scored best after inversion)",
    2: "Low risk / low complexity",
    3: "Moderate risk / moderate complexity",
    4: "High risk / high complexity",
    5: "Very high risk / very high complexity (scored worst after inversion)",
}
