"""Analytic Hierarchy Process (Saaty) - pure NumPy implementation."""
from dataclasses import dataclass
import numpy as np

# Random Index (Saaty) for matrix sizes 1..10
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12,
                6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
CR_THRESHOLD = 0.10

SAATY_LABELS = {
    1: "Equal importance", 2: "Between equal and moderate", 3: "Moderate importance",
    4: "Between moderate and strong", 5: "Strong importance", 6: "Between strong and very strong",
    7: "Very strong importance", 8: "Between very strong and extreme", 9: "Extreme importance",
}


@dataclass
class AHPResult:
    weights: np.ndarray        # priority vector, sums to 1
    lambda_max: float
    ci: float
    ri: float
    cr: float
    consistent: bool           # CR <= 0.10
    matrix: np.ndarray
    method: str


def signed_to_value(k: int) -> float:
    """UI helper. k in -8..8: k>=0 -> (k+1) (row more important), k<0 -> 1/(|k|+1)."""
    return float(k + 1) if k >= 0 else 1.0 / (abs(k) + 1)


def value_to_signed(v: float) -> int:
    """Inverse of signed_to_value (rounds to the nearest Saaty value)."""
    v = float(v)
    if v >= 1:
        return int(min(9, max(1, round(v)))) - 1
    return -(int(min(9, max(1, round(1.0 / v)))) - 1)


def saaty_label(k: int) -> str:
    n = abs(k) + 1
    return SAATY_LABELS[n]


def build_matrix(n: int, upper: dict) -> np.ndarray:
    """Build a reciprocal matrix from upper-triangle judgments {(i, j): a_ij}, i < j.

    Missing pairs default to 1. Raises ValueError for judgments outside 1/9..9.
    """
    m = np.ones((n, n))
    for (i, j), v in upper.items():
        if not (0 <= i < j < n):
            raise ValueError(f"Invalid pair index {(i, j)}.")
        v = float(v)
        if not (1 / 9 - 1e-9 <= v <= 9 + 1e-9) or v <= 0:
            raise ValueError("Judgments must lie on the Saaty scale (1/9 to 9).")
        m[i, j] = v
        m[j, i] = 1.0 / v
    return m


def _validate_matrix(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    if m.ndim != 2 or m.shape[0] != m.shape[1] or m.shape[0] < 1:
        raise ValueError("Pairwise matrix must be square.")
    if not np.all(np.isfinite(m)) or np.any(m <= 0):
        raise ValueError("Pairwise matrix must contain finite positive values.")
    if not np.allclose(m * m.T, 1.0, atol=1e-8):
        raise ValueError("Pairwise matrix must be reciprocal (a_ji = 1 / a_ij).")
    return m


def priority_vector(m: np.ndarray, method: str = "eigen") -> np.ndarray:
    """Priority weights. 'eigen' = principal right eigenvector; 'geometric' = row geometric mean."""
    m = _validate_matrix(m)
    n = m.shape[0]
    if method == "geometric":
        g = np.prod(m, axis=1) ** (1.0 / n)
        return g / g.sum()
    vals, vecs = np.linalg.eig(m)
    k = int(np.argmax(vals.real))
    v = np.abs(vecs[:, k].real)
    return v / v.sum()


def ahp(m: np.ndarray, method: str = "eigen") -> AHPResult:
    """Full AHP: weights, lambda_max, CI, RI, CR."""
    m = _validate_matrix(m)
    n = m.shape[0]
    w = priority_vector(m, method)
    # lambda_max = mean( (A w)_i / w_i )  - valid for both methods
    lam = float(np.mean((m @ w) / w))
    ci = (lam - n) / (n - 1) if n > 1 else 0.0
    ci = max(ci, 0.0) if abs(ci) < 1e-12 else ci
    ri = RANDOM_INDEX.get(n)
    if ri is None:
        raise ValueError("Random Index is only tabulated for n <= 10.")
    cr = ci / ri if ri > 0 else 0.0
    return AHPResult(w, lam, ci, ri, cr, cr <= CR_THRESHOLD + 1e-12, m, method)


def most_inconsistent_pair(m: np.ndarray):
    """Pair (i, j, a_ij, implied) where a_ij deviates most from w_i / w_j (guides revision)."""
    m = _validate_matrix(m)
    w = priority_vector(m)
    n = m.shape[0]
    best, pair = -1.0, None
    for i in range(n):
        for j in range(i + 1, n):
            implied = w[i] / w[j]
            dev = abs(np.log(m[i, j] / implied))
            if dev > best:
                best, pair = dev, (i, j, float(m[i, j]), float(implied))
    return pair
