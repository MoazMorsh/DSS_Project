import io
import numpy as np
import pandas as pd
import pytest
from core.schema import *
from core.validation import validate_initiatives, validate_weights, validate_budget
from core.data_processing import (sample_dataframe, template_bytes, load_sample, read_uploaded,
                                  dataframe_to_excel_bytes)


def good():
    return sample_dataframe()


def test_sample_dataset_is_valid_and_has_15_rows():
    r = validate_initiatives(good())
    assert r.is_valid and len(r.data) == 15 and not r.warnings
    assert r.data[COL_ID].is_unique


def test_bundled_sample_file_loads():
    assert validate_initiatives(load_sample()).is_valid


def test_template_roundtrip_is_valid():
    df = pd.read_excel(io.BytesIO(template_bytes()), sheet_name="Initiatives")
    assert validate_initiatives(df).is_valid


def test_excel_export_roundtrip():
    out = pd.read_excel(io.BytesIO(dataframe_to_excel_bytes(good())), sheet_name="Initiatives")
    assert validate_initiatives(out).is_valid


def test_missing_required_column():
    r = validate_initiatives(good().drop(columns=[COL_COST]))
    assert not r.is_valid and COL_COST in r.errors[0]


def test_missing_value_detected_with_row_number():
    df = good(); df.loc[2, COL_NPV] = np.nan
    r = validate_initiatives(df)
    assert not r.is_valid and any("Row 4" in e and COL_NPV in e for e in r.errors)


def test_non_numeric_value():
    df = good(); df[COL_ROI] = df[COL_ROI].astype(object); df.loc[0, COL_ROI] = "abc"
    r = validate_initiatives(df)
    assert any("not a number" in e for e in r.errors)


def test_rating_out_of_range():
    df = good(); df.loc[0, "Financial Risk"] = 7; df.loc[1, "Customer Impact"] = 0
    r = validate_initiatives(df)
    assert len([e for e in r.errors if "outside the 1-5" in e]) == 2


def test_scale_is_configurable():
    df = good(); df.loc[0, "Financial Risk"] = 7
    assert validate_initiatives(df, scale_max=10).is_valid


def test_negative_or_zero_cost_and_payback():
    df = good(); df.loc[0, COL_COST] = 0; df.loc[1, COL_PAYBACK] = -1
    r = validate_initiatives(df)
    assert len(r.errors) == 2


def test_duplicate_ids():
    df = good(); df.loc[1, COL_ID] = df.loc[0, COL_ID]
    assert any("Duplicate" in e for e in validate_initiatives(df).errors)


def test_blank_id_and_name():
    df = good(); df.loc[0, COL_ID] = ""; df.loc[1, COL_NAME] = None
    assert len(validate_initiatives(df).errors) >= 2


def test_empty_and_none_input():
    assert not validate_initiatives(pd.DataFrame()).is_valid
    assert not validate_initiatives(None).is_valid


def test_header_case_insensitive_and_extra_columns_warned():
    df = good(); df.columns = [c.upper() for c in df.columns]; df["Notes"] = "x"
    r = validate_initiatives(df)
    assert r.is_valid and any("Ignored" in w for w in r.warnings)


def test_blank_trailing_rows_dropped():
    df = pd.concat([good(), pd.DataFrame([{}, {}])], ignore_index=True)
    r = validate_initiatives(df)
    assert r.is_valid and len(r.data) == 15


def test_csv_upload():
    csv = good().to_csv(index=False).encode()
    assert validate_initiatives(read_uploaded(io.BytesIO(csv), "x.csv")).is_valid
    with pytest.raises(ValueError):
        read_uploaded(io.BytesIO(b""), "x.txt")


def test_weights_validation():
    assert validate_weights(DEFAULT_WEIGHTS) == []
    assert validate_weights({**DEFAULT_WEIGHTS, "Risk Assessment": -0.1})
    assert validate_weights({c: 0 for c in CRITERIA_NAMES})
    assert validate_weights({"Risk Assessment": 1})
    assert validate_weights({**DEFAULT_WEIGHTS, "Business Impact": float("nan")})


def test_budget_validation():
    assert validate_budget(100) == [] and validate_budget("12.5") == []
    for bad in (-5, None, "x", float("inf")):
        assert validate_budget(bad)
