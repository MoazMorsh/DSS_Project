# Strategic Initiative Prioritization and Resource Allocation Decision Support System

*A Multi-Criteria Decision Analysis Approach for Corporate Strategic Planning* — Advanced Decision Support Systems, Master's-level academic prototype.

An interactive Streamlit application that helps managers **evaluate, rank and select strategic initiatives under a budget constraint**, using AHP, a Weighted Sum Model, binary (0-1) portfolio optimisation, scenario analysis and sensitivity analysis. It supports — and never replaces — managerial judgement. **All bundled data is fictional.**

---

## 1. Quick start (local)

Requires Python 3.10+ (developed and tested on 3.12, Streamlit 1.67).

```bash
cd DSS
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
streamlit run app.py
```
The app opens at http://localhost:8501 and starts with the sample dataset already loaded.

**Run the tests** (from the `DSS` folder):
```bash
python -m pytest
```
Expected: all tests pass (95 at the time of writing).

## 2. What you can do (pages)

| Page | Purpose |
|---|---|
| Executive Dashboard | KPI cards, score/budget/value-for-money charts, auto-generated insights |
| Data Management | Load sample, upload Excel/CSV, validation with row-level messages, add/edit/delete initiatives, template download |
| Criteria & Weighting | Default (25/25/20/15/15), manual weights (must total 100%) or **AHP** pairwise matrix with eigenvector weights, CI, CR, RI and inconsistency warning |
| Initiative Evaluation | Raw inputs → normalised 0-100 scores → weighted contributions (radar, heat map, stacked bars) |
| Decision Analysis | Weighted-sum ranking, **optimal portfolio under budget**, selected/rejected lists, explanations, comparison with "highest-ranking-first" |
| Scenario & Sensitivity | Base / Growth-Oriented / Risk-Averse (editable, new scenarios), side-by-side comparison; weight what-if, one-at-a-time stability, random perturbation |
| Decision Report | Executive summary, methodology, weights, ranking, portfolio, scenarios, sensitivity, assumptions, limitations → **PDF and Excel** |

The **available budget** is set in the sidebar and is a *constraint*, not a criterion. Changing it recalculates every page.

## 3. Input data format

Download the template from *Data Management → Template & definitions*. One row per initiative:

* Required: `Initiative ID` (unique), `Initiative Name`, `Estimated Cost` (> 0), `Expected ROI (%)`, `NPV`, `Payback Period (Years)` (> 0) and twelve 1-5 ratings (Alignment with Corporate Objectives, Contribution to Long-term Strategy, Competitive Advantage, Revenue Growth Potential, Customer Impact, Operational Efficiency, Resource Availability, Technical Capability, Implementation Complexity, Financial Risk, Operational Risk, Market & Execution Risk).
* Optional: `Description`, `Business Function`.
* **Risk and complexity: higher = worse.** The system inverts them so that every normalised score means "higher is better". Payback is also inverted (shorter is better).
* Cost and NPV must use the same currency unit (the sample uses millions). The rating scale maximum is configurable (3-10, default 5).

## 4. Project structure

```
DSS/
├── app.py                      entry point + navigation + branding
├── requirements.txt            runtime dependencies (used by Streamlit Cloud)
├── requirements-dev.txt        + pytest
├── pytest.ini
├── .streamlit/config.toml      navy/white theme
├── pages/                      the 7 application pages
├── core/                       all logic (no Streamlit code except state.py / ui.py)
│   ├── schema.py               column names, criteria hierarchy, score definitions
│   ├── validation.py           input validation (never raises on bad data)
│   ├── data_processing.py      sample data, import, Excel template
│   ├── ahp.py                  AHP (eigenvector, CI, CR, RI)
│   ├── weighted_scoring.py     normalisation + Weighted Sum Model
│   ├── optimization.py         0-1 knapsack (SciPy MILP) + rank-first benchmark + explanations
│   ├── scenario_analysis.py    scenarios
│   ├── sensitivity_analysis.py weight sensitivity
│   ├── report.py               report assembly, Excel and PDF export
│   ├── state.py / ui.py        session state and look-and-feel
├── data/sample_initiatives.xlsx
├── docs/METHODOLOGY.md         theory, formulas, assumptions, limitations, references
├── assets/
└── tests/                      pytest suite (models, validation, report, UI)
```
Improvements over the suggested structure: `core/schema.py` (single source of truth for column names), `core/report.py`, `core/state.py`, `core/ui.py`, extra tests, and `docs/`.

## 5. Implementation decisions worth knowing (for your viva)

* **Why SciPy `milp`:** exact integer optimisation, free, no solver install. An exact dynamic-programming fallback exists, and tests compare the optimiser with brute force.
* **Why subcriteria are averaged first:** each criterion score is the (equal by default, editable) weighted mean of its three subcriteria, so the five criterion weights keep their meaning.
* **Why min-max for ROI/NPV/payback:** the three have different units; min-max makes them comparable and is easy to explain. Its drawback (scores are relative to the evaluated set) is documented.
* **AHP is used for criteria weights only**, avoiding the well-known rank-reversal debate about AHP for alternatives.
* **Ties:** equal scores share the same rank.
* **Highest-ranking-first benchmark:** walks down the ranking and takes each initiative that still fits.
* **Scenarios** store their own assumptions; the *Base* scenario is a snapshot of the inputs when created (the app warns if it becomes outdated and offers *Rebuild*).

## 6. Verification status (be precise in your report)

| Level | Status |
|---|---|
| Model verification (code computes what the formulas say) | Done — automated tests with hand-calculable examples |
| Functional testing of the UI | Done — headless Streamlit tests of every page and key interactions |
| Empirical validation with real decisions / users | **Not done** |
| Impact on real organisational performance | **Not claimed** |

Known modelling limitations: additive/compensatory scoring, independent initiatives, single-period budget, point estimates, no mandatory-project or dependency constraints. See `docs/METHODOLOGY.md`.

## 7. Upload to GitHub

1. Create a free account at https://github.com and click **New repository** (e.g. `strategic-dss`, public, *no* README/gitignore — this project has them).
2. Install Git (https://git-scm.com). In a terminal inside the `DSS` folder:
```bash
git init
git add .
git commit -m "Initial commit: Strategic DSS"
git branch -M main
git remote add origin https://github.com/<your-username>/strategic-dss.git
git push -u origin main
```
No-terminal alternative: on the new repository page choose **Add file → Upload files** and drag in the *contents* of the `DSS` folder (keep sub-folders; include the hidden `.streamlit` folder).

## 8. Deploy free on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Repository: `<your-username>/strategic-dss` · Branch: `main` · Main file path: `app.py`.
4. (Optional) **Advanced settings** → choose Python 3.11 or 3.12.
5. Click **Deploy**. The first start installs `requirements.txt` (a few minutes). You get a public URL to put in your report.

Notes
* All paths are relative to the code (`pathlib`), so no local absolute paths are used.
* **Secrets:** the app needs none. If you later add an integration, put keys in *App settings → Secrets* (or a local `.streamlit/secrets.toml`, which is git-ignored) and read them with `st.secrets["NAME"]`. Never write keys in source code.
* **Temporary storage:** session data (uploaded data, edits, scenarios) lives in the browser session only. It disappears on refresh/timeout, and the Cloud file system is not a database. Use the download buttons to keep your work. Free apps go to sleep after inactivity and wake on the next visit.
* Do not upload confidential company data to a public deployment.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `streamlit: command not found` | Activate the virtual environment, or use `python -m streamlit run app.py` |
| Upload rejected | Read the validation messages (row numbers refer to Excel rows); use the template |
| Everything reset | You refreshed the page; session data is not persisted |
| PDF export fails | Ensure `reportlab` is installed (`pip install -r requirements.txt`) |
