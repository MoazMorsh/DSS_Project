"""Sample data, file import and Excel template generation."""
import io
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .schema import (ALL_COLUMNS, COL_ID, COL_NAME, COL_DESC, COL_FUNC, COL_COST, COL_ROI,
                     COL_NPV, COL_PAYBACK, REQUIRED_COLUMNS, CRITERIA,
                     SCORE_DEFINITIONS_BENEFIT, SCORE_DEFINITIONS_RISK)

BASE_DIR = Path(__file__).resolve().parent.parent        # relative to the code -> works in the cloud
SAMPLE_PATH = BASE_DIR / "data" / "sample_initiatives.xlsx"
NAVY = "0B2545"

# name, function, description, cost, ROI, NPV, payback, then 12 ratings in schema order:
# [Align, LongTerm, CompAdv, RevGrowth, CustImpact, OpEff, ResAvail, TechCap, Complexity, FinRisk, OpRisk, MktRisk]
_SAMPLE = [
    ("Digital Transformation", "Technology & Digital", "Enterprise-wide modernisation of digital channels and core systems.", 18.0, 22, 14.5, 3.5, [5, 5, 4, 4, 4, 4, 3, 3, 5, 4, 4, 3]),
    ("Market Expansion", "Sales & Marketing", "Entry into adjacent customer segments in existing markets.", 12.5, 18, 9.0, 4.0, [4, 4, 4, 5, 3, 2, 3, 4, 3, 3, 3, 5]),
    ("New Product Development", "R&D & Product", "Development and launch of a new flagship product line.", 15.0, 26, 16.0, 3.8, [5, 4, 5, 5, 4, 2, 3, 3, 4, 4, 3, 4]),
    ("Operational Automation", "Operations", "Automation of repetitive back-office and production tasks.", 9.0, 31, 11.5, 2.6, [3, 3, 3, 3, 2, 5, 4, 4, 2, 2, 3, 2]),
    ("Customer Retention", "Sales & Marketing", "Loyalty, win-back and proactive account management programme.", 4.5, 38, 6.8, 1.6, [4, 4, 3, 4, 5, 2, 5, 5, 1, 1, 2, 2]),
    ("Supply Chain Optimization", "Operations", "Network redesign and supplier consolidation.", 10.5, 24, 8.4, 3.1, [3, 3, 3, 2, 3, 5, 3, 4, 3, 2, 3, 2]),
    ("Employee Development", "Human Resources", "Skills academy and leadership pipeline programme.", 3.0, 14, 1.9, 4.5, [3, 4, 2, 2, 2, 3, 4, 5, 1, 1, 2, 1]),
    ("Customer Experience Improvement", "Customer Service", "Redesign of key customer journeys and service touchpoints.", 6.5, 29, 7.9, 2.2, [4, 3, 4, 4, 5, 3, 4, 4, 2, 2, 2, 2]),
    ("Technology Infrastructure Upgrade", "Technology & Digital", "Replacement of ageing infrastructure and cyber-security uplift.", 14.0, 12, 4.2, 5.4, [3, 4, 2, 2, 2, 4, 3, 3, 4, 3, 4, 2]),
    ("Sustainability Program", "Corporate Affairs", "Emission reduction and responsible-sourcing initiatives.", 8.0, 10, 3.1, 6.0, [4, 5, 3, 2, 3, 2, 3, 3, 3, 2, 3, 3]),
    ("Process Standardization", "Operations", "Harmonisation of core processes across business units.", 5.0, 20, 3.9, 2.9, [2, 3, 2, 2, 2, 4, 4, 5, 2, 1, 2, 1]),
    ("Geographic Expansion", "Sales & Marketing", "Establishing operations in two new geographic regions.", 20.0, 16, 10.2, 5.0, [4, 4, 4, 5, 3, 2, 2, 3, 4, 4, 4, 5]),
    ("Data Analytics Implementation", "Technology & Digital", "Enterprise analytics platform and decision-intelligence capability.", 7.5, 34, 10.6, 2.0, [4, 4, 4, 3, 3, 5, 4, 4, 2, 2, 2, 2]),
    ("Strategic Partnership Development", "Corporate Strategy", "Alliances with complementary partners for joint offerings.", 6.0, 21, 5.1, 2.8, [4, 5, 5, 4, 3, 2, 4, 3, 3, 2, 3, 4]),
    ("Risk Management Enhancement", "Finance & Risk", "Upgrade of enterprise risk, compliance and controls framework.", 4.0, 9, 2.0, 4.2, [2, 3, 2, 1, 2, 3, 4, 4, 2, 1, 3, 1]),
]


def sample_dataframe() -> pd.DataFrame:
    """15 clearly FICTIONAL illustrative initiatives (currency units: millions)."""
    rating_cols = [s.label for subs in CRITERIA.values() for s in subs
                   if s.label not in (COL_ROI, COL_NPV, COL_PAYBACK)]
    rows = []
    for k, (name, func, desc, cost, roi, npv, pay, ratings) in enumerate(_SAMPLE, 1):
        row = {COL_ID: f"INI-{k:02d}", COL_NAME: name, COL_DESC: desc, COL_FUNC: func,
               COL_COST: cost, COL_ROI: roi, COL_NPV: npv, COL_PAYBACK: pay}
        row.update(dict(zip(rating_cols, ratings)))
        rows.append(row)
    return pd.DataFrame(rows)[ALL_COLUMNS]


def read_uploaded(file, filename: str) -> pd.DataFrame:
    """Read an uploaded .xlsx/.xls/.csv. Looks for a sheet called 'Initiatives' first."""
    name = filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        xl = pd.ExcelFile(file)
        sheet = "Initiatives" if "Initiatives" in xl.sheet_names else xl.sheet_names[0]
        return xl.parse(sheet)
    raise ValueError("Unsupported file type. Please upload .xlsx or .csv.")


def _style_header(ws, ncols, row=1):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def build_workbook(df: pd.DataFrame, with_instructions: bool) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Initiatives"
    ws.append(ALL_COLUMNS)
    _style_header(ws, len(ALL_COLUMNS))
    for rec in df[ALL_COLUMNS].itertuples(index=False):
        ws.append(list(rec))
    for r in ws.iter_rows(min_row=2):
        for cell in r:
            cell.font = Font(name="Arial", size=10, color="0000FF")   # blue = user inputs
    for i, col in enumerate(ALL_COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = 48 if col == COL_DESC else (
            28 if col in (COL_NAME, COL_FUNC) else 17)
    ws.row_dimensions[1].height = 45
    ws.freeze_panes = "C2"

    if with_instructions:
        ins = wb.create_sheet("Instructions", 0)
        lines = [
            ("How to use this template", True),
            ("1. Go to the 'Initiatives' sheet. Row 2 is a worked EXAMPLE (fictional) - overwrite or delete it.", False),
            ("2. One row per strategic initiative. Do not rename the column headers.", False),
            ("3. Required columns: " + ", ".join(REQUIRED_COLUMNS) + ".", False),
            ("4. Optional columns: Description, Business Function.", False),
            (f"5. '{COL_COST}' and '{COL_NPV}' use the same currency unit (e.g. millions). Cost must be > 0.", False),
            (f"6. '{COL_ROI}' is a percentage number (22 = 22 %). '{COL_PAYBACK}' is in years and must be > 0.", False),
            ("7. All other criteria are rated on a 1-5 scale (see 'Score Definitions').", False),
            ("8. Risk and complexity ratings: HIGHER = WORSE. The system inverts them automatically.", False),
            ("9. Blue font = values you enter. Upload the file in Data Management.", False),
        ]
        for i, (t, b) in enumerate(lines, 1):
            ins.cell(row=i, column=1, value=t).font = Font(name="Arial", bold=b, size=12 if b else 10)
        ins.column_dimensions["A"].width = 130
        sd = wb.create_sheet("Score Definitions")
        sd.append(["Score", "Benefit criteria (higher = better)", "Risk / complexity criteria (higher = worse)"])
        _style_header(sd, 3)
        for k in range(1, 6):
            sd.append([k, SCORE_DEFINITIONS_BENEFIT[k], SCORE_DEFINITIONS_RISK[k]])
        for col, wdt in zip("ABC", (8, 55, 70)):
            sd.column_dimensions[col].width = wdt
        for r in sd.iter_rows(min_row=2):
            for c in r:
                c.font = Font(name="Arial", size=10)
    return wb


def template_bytes() -> bytes:
    """Downloadable template: instructions, one fictional example row, score definitions."""
    example = sample_dataframe().head(1).copy()
    example[COL_ID] = "EXAMPLE-01"
    example[COL_NAME] = "Example initiative (replace me)"
    buf = io.BytesIO()
    build_workbook(example, True).save(buf)
    return buf.getvalue()


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    build_workbook(df, False).save(buf)
    return buf.getvalue()


def create_sample_file(path: Path = SAMPLE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = build_workbook(sample_dataframe(), True)
    wb["Instructions"]["A1"].value = "Illustrative sample dataset - ALL DATA IS FICTIONAL"
    wb.save(path)
    return path


def load_sample() -> pd.DataFrame:
    """Load the bundled sample file (falls back to the in-code copy)."""
    try:
        if SAMPLE_PATH.exists():
            return read_uploaded(SAMPLE_PATH, SAMPLE_PATH.name)
    except Exception:
        pass
    return sample_dataframe()
