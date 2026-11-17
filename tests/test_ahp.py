import numpy as np
import pytest
from core.ahp import (ahp, build_matrix, priority_vector, most_inconsistent_pair,
                      signed_to_value, value_to_signed, RANDOM_INDEX)


def test_consistent_matrix_weights_and_cr_zero():
    # perfectly consistent: weights must be exactly 4/7, 2/7, 1/7 (hand calculation)
    m = np.array([[1, 2, 4], [1 / 2, 1, 2], [1 / 4, 1 / 2, 1]])
    r = ahp(m)
    assert r.weights == pytest.approx([4 / 7, 2 / 7, 1 / 7], abs=1e-9)
    assert r.lambda_max == pytest.approx(3.0, abs=1e-9)
    assert r.ci == pytest.approx(0.0, abs=1e-9)
    assert r.cr == pytest.approx(0.0, abs=1e-9)
    assert r.consistent


def test_weights_sum_to_one_and_positive():
    m = build_matrix(4, {(0, 1): 3, (0, 2): 5, (0, 3): 7, (1, 2): 2, (1, 3): 4, (2, 3): 2})
    w = ahp(m).weights
    assert w.sum() == pytest.approx(1.0)
    assert (w > 0).all()


def test_equal_matrix_gives_equal_weights():
    r = ahp(np.ones((5, 5)))
    assert r.weights == pytest.approx([0.2] * 5)
    assert r.cr == pytest.approx(0.0, abs=1e-12)


def test_consistency_index_matches_definition():
    m = build_matrix(3, {(0, 1): 3, (0, 2): 5, (1, 2): 3})
    r = ahp(m)
    lam = max(np.linalg.eigvals(m).real)              # independent computation
    assert r.lambda_max == pytest.approx(lam, abs=1e-9)
    assert r.ci == pytest.approx((lam - 3) / 2, abs=1e-9)
    assert r.cr == pytest.approx(r.ci / 0.58, abs=1e-9)
    assert r.lambda_max >= 3                           # lambda_max >= n always


def test_inconsistent_matrix_flagged():
    # A>B 9x, B>C 9x, but C>A 9x -> cyclic, very inconsistent
    m = build_matrix(3, {(0, 1): 9, (1, 2): 9, (0, 2): 1 / 9})
    r = ahp(m)
    assert r.cr > 0.10
    assert not r.consistent


def test_random_index_table_values():
    assert RANDOM_INDEX[3] == 0.58 and RANDOM_INDEX[5] == 1.12 and RANDOM_INDEX[10] == 1.49


def test_size_2_has_zero_cr():
    assert ahp(build_matrix(2, {(0, 1): 5})).cr == 0.0


def test_geometric_mean_close_to_eigenvector_when_consistent():
    m = np.array([[1, 2, 4], [1 / 2, 1, 2], [1 / 4, 1 / 2, 1]])
    assert priority_vector(m, "geometric") == pytest.approx(priority_vector(m, "eigen"), abs=1e-9)


def test_reciprocity_enforced():
    with pytest.raises(ValueError):
        ahp(np.array([[1, 3], [3, 1]]))                # not reciprocal
    with pytest.raises(ValueError):
        build_matrix(3, {(0, 1): 12})                  # off the Saaty scale
    with pytest.raises(ValueError):
        ahp(np.array([[1, 0], [0, 1]]))


def test_signed_value_roundtrip():
    for k in range(-8, 9):
        assert value_to_signed(signed_to_value(k)) == k
    assert signed_to_value(0) == 1 and signed_to_value(8) == 9 and signed_to_value(-8) == pytest.approx(1 / 9)


def test_most_inconsistent_pair_points_at_the_outlier():
    # consistent 4x4 from weights 8:4:2:1 (a_ij = w_i / w_j), then tamper ONE judgement
    w = [8, 4, 2, 1]
    upper = {(i, j): w[i] / w[j] for i in range(4) for j in range(i + 1, 4)}
    upper[(0, 3)] = 1.0                      # should be 8
    i, j, given, implied = most_inconsistent_pair(build_matrix(4, upper))
    assert (i, j) == (0, 3) and given == 1.0 and implied > 1.5
