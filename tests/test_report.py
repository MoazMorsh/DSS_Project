import io
import pandas as pd
from core.schema import DEFAULT_WEIGHTS
from core.data_processing import sample_dataframe
from core.report import assemble_report, build_excel_report, build_pdf_report


def test_report_contains_current_results_and_exports():
    ctx = assemble_report(sample_dataframe(), DEFAULT_WEIGHTS, "Default", None, 5, 72)
    assert ctx["optimal"].total_cost <= 72
    assert str(ctx["optimal"].n_selected) in ctx["summary"][2]
    xl = pd.ExcelFile(io.BytesIO(build_excel_report(ctx)))
    assert {"Executive Summary", "Ranking", "Recommended Portfolio", "Scenarios", "Limitations"} <= set(xl.sheet_names)
    assert len(xl.parse("Ranking")) == 15
    pdf = build_pdf_report(ctx)
    assert pdf[:4] == b"%PDF"
