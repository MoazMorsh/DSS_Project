# Academic Methodology

*Strategic Initiative Prioritization and Resource Allocation Decision Support System*

> **Status of the work.** The system is a **functional prototype**. Its calculations are verified by automated tests against hand-calculable examples (*model verification*). It has **not** been validated with real decision-makers or real organisational outcomes, so no claim is made that it improves corporate performance (*real-world impact is untested*). The bundled data is **fictional**.

## 1. Decision Support Systems (DSS)
A DSS is an interactive computer-based system that helps decision-makers use data and models to address semi-structured problems. Classic DSS architecture combines **data management**, **model management** and a **dialogue (user-interface)** component.

| DSS component | Implementation |
|---|---|
| Data | `core/data_processing.py`, `core/validation.py`, Excel/CSV import, session state |
| Model base | `core/ahp.py`, `weighted_scoring.py`, `optimization.py`, `scenario_analysis.py`, `sensitivity_analysis.py` |
| Dialogue | Streamlit pages in `pages/` |

The system *supports* managers; the human decides. Prioritising initiatives under a budget is semi-structured: criteria are partly subjective, but the selection problem has a precise mathematical form.

## 2. Multi-Criteria Decision Analysis (MCDA)
MCDA evaluates alternatives against several, often conflicting, criteria. A single measure (e.g. ROI) ignores strategic fit, feasibility and risk. The system combines **five criteria** (Strategic Alignment, Financial Attractiveness, Business Impact, Implementation Feasibility, Risk Assessment), each with three subcriteria. *Cost/budget is a constraint, not a criterion.*

**How the models interact**

```
 data ──► AHP (or manual / default) ──► criterion weights
   │                                          │
   └──► normalisation ──► Weighted Sum ◄──────┘
                              │ scores, ranks
                              ▼
          Binary optimisation  ◄── budget (constraint)
                              │ portfolio
              ┌───────────────┴───────────────┐
        Scenario analysis             Sensitivity analysis
   (budget / weights / cost)        (weights ± → ranks, portfolio)
                              └──► Decision report
```

## 3. Analytic Hierarchy Process (AHP)
* **Why / problem solved:** turns subjective pairwise judgements into ratio-scale **weights**, with a measurable consistency check.
* **Formulation:** judgements `a_ij` on Saaty's 1–9 scale, `a_ji = 1/a_ij`. Weights `w` solve `A w = λmax w` (principal right eigenvector, Σw = 1; computed with NumPy).
  `CI = (λmax − n)/(n − 1)`, `CR = CI / RI`; RI (n = 1…10) = 0, 0, 0.58, 0.90, 1.12, 1.24, 1.32, 1.41, 1.45, 1.49. Acceptable if `CR ≤ 0.10`.
* **Assumptions:** the criteria are independent enough to be compared pairwise; a judge can express ratios of importance.
* **Limitations:** subjective; sensitive to the 1–9 scale; rank-reversal issues when alternatives are compared directly (here AHP is used **only for criteria weights**); CR measures consistency, not correctness. n = 5 is within the usual 7±2 comparison limit.
* **Revision support:** the app flags the pair deviating most from the weights implied by the other judgements.

## 4. Weighted Sum Model (WSM)
* **Why:** transparent, additive, explainable scoring on a common 0–100 scale.
* **Formulation:** `Score_i = Σ_c w_c · S_ic`, `S_ic = Σ_s v_cs · n_ics`, where `n` is the normalised subcriterion value, `v` the subcriterion weight (default equal), `w` the criterion weight (Σ = 1).
* **Normalisation (higher = always better):**
  * Ratings 1…N, benefit: `(x−1)/(N−1)·100`; cost/risk/complexity: `(N−x)/(N−1)·100`.
  * Quantitative (ROI, NPV): min–max `(x−min)/(max−min)·100`; payback (cost-type): `(max−x)/(max−min)·100`; constant column → 50.
  * Low risk therefore yields a **high** score; risk is never a negative contribution.
* **Assumptions:** compensatory (a strength offsets a weakness), additive independence, commensurable scales.
* **Limitations:** min–max scores are relative to the evaluated set (adding initiatives changes scores); results depend on weights; ignores uncertainty.

## 5. Binary portfolio optimisation (0–1 knapsack)
* **Why:** ranking is not selection. Funding the top-ranked initiatives in order can leave budget unused or block a better combination.
* **Formulation:** `max Σ Score_i·x_i  s.t.  Σ Cost_i·x_i ≤ B,  x_i ∈ {0,1}`.
* **Solution:** exact mixed-integer linear programming, `scipy.optimize.milp` (HiGHS). Feasibility is re-checked after solving; an exact dynamic-programming solver is the automatic fallback and a test cross-check (also verified against brute force on random instances).
* **Benchmark:** *highest-ranking-first* (walk down the ranking, take what still fits).
* **Assumptions:** initiatives are independent and indivisible; costs are known; single period.
* **Limitations:** no synergies/dependencies, mandatory projects, multi-year budgets or risk-pooling effects; the objective sums scores, so portfolio value is an ordinal-style index, not money.

## 6. Scenario analysis
* **Why:** the future is uncertain; scenarios show how the recommendation changes under coherent alternative assumptions.
* **Implementation:** a scenario = budget + criterion weights + cost multiplier + excluded initiatives. Each scenario re-runs scoring, ranking and optimisation. Standard scenarios (Base, Growth-Oriented, Risk-Averse) are derived from the current inputs; all assumptions are editable and displayed next to the results.
* **Limitations:** scenarios are user-defined and not probability-weighted.

## 7. Sensitivity analysis
* **Why:** weights are subjective; stable recommendations are more trustworthy.
* **Implementation:** (a) interactive what-if (relative weight changes, renormalised); (b) one-at-a-time sweeps (default ±25 %, ±50 %) reporting rank range, unstable initiatives (rank range ≥ 3), criterion influence (mean absolute rank shift) and portfolio selection frequency; (c) seeded random perturbation of all weights. Everything is recomputed from the live inputs.
* **Limitations:** one-at-a-time analysis does not capture all interactions; only weights are perturbed in the automatic sweeps (scores/costs via scenarios).

## 8. Verification summary (see `tests/`)
AHP eigenvector/CI/CR vs hand-calculable matrices · normalisation of benefit/cost/risk · hand-computed WSM scores · optimiser vs brute force and DP on random instances, budget compliance · scenario recalculation · sensitivity outputs · validation of missing/invalid input · UI smoke and interaction tests.

## 9. References
*These are genuine publications, but this environment has no access to verify DOIs/pages online. Open each source and confirm the bibliographic details before citing them in your report.* DOIs are listed only where I am confident of them.

1. Keen, P. G. W., & Scott Morton, M. S. (1978). *Decision Support Systems: An Organizational Perspective*. Addison-Wesley.
2. Sprague, R. H. (1980). A framework for the development of decision support systems. *MIS Quarterly, 4*(4), 1–26. https://doi.org/10.2307/248957
3. Belton, V., & Stewart, T. J. (2002). *Multiple Criteria Decision Analysis: An Integrated Approach*. Kluwer / Springer. https://doi.org/10.1007/978-1-4615-1495-4
4. Saaty, T. L. (1977). A scaling method for priorities in hierarchical structures. *Journal of Mathematical Psychology, 15*(3), 234–281. https://doi.org/10.1016/0022-2496(77)90033-5
5. Saaty, T. L. (1980). *The Analytic Hierarchy Process*. McGraw-Hill.
6. Saaty, T. L. (2008). Decision making with the analytic hierarchy process. *International Journal of Services Sciences, 1*(1), 83–98.
7. Triantaphyllou, E. (2000). *Multi-Criteria Decision Making Methods: A Comparative Study*. Springer. https://doi.org/10.1007/978-1-4757-3157-6
8. Martello, S., & Toth, P. (1990). *Knapsack Problems: Algorithms and Computer Implementations*. Wiley.
9. Schoemaker, P. J. H. (1995). Scenario planning: A tool for strategic thinking. *Sloan Management Review, 36*(2), 25–40.
10. Triantaphyllou, E., & Sánchez, A. (1997). A sensitivity analysis approach for some deterministic multi-criteria decision-making methods. *Decision Sciences, 28*(1), 151–194.
11. Saltelli, A., Ratto, M., Andres, T., et al. (2008). *Global Sensitivity Analysis: The Primer*. Wiley.
