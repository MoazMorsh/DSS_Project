import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core.scenario_analysis import Scenario, run_scenario, default_scenarios, compare_scenarios, validate_scenario
from core.sensitivity_analysis import adjust_weights, compare_ranking, one_at_a_time, random_weight_simulation, UNSTABLE_RANGE
from core.optimization import optimize_portfolio
from core.weighted_scoring import compute_scores
from core import ui

init_state()
require_data()
ss = st.session_state
ui.page_header("Scenario & Sensitivity Analysis", "Compare alternative assumptions and test how stable the recommendation is.")
a = get_analysis()
df = ss.df

tab_s, tab_t = st.tabs(["Scenario analysis", "Sensitivity analysis"])

# =========================== SCENARIOS ======================================
with tab_s:
    if not ss.scenarios:
        ss.scenarios = default_scenarios(a.weights, ss.budget)
    if ss.get("flash"):
        st.success(ss.pop("flash"))

    base = ss.scenarios.get("Base")
    if base and (abs(base.budget - ss.budget) > 1e-9 or any(abs(base.weights[c] - a.weights[c]) > 1e-9 for c in CRITERIA_NAMES)):
        st.info("The saved **Base** scenario differs from the current budget / active weights. "
                "Use *Rebuild the three standard scenarios* to re-derive them from the current inputs.")

    def rebuild():
        ss.scenarios = default_scenarios(a.weights, ss.budget)
        ss.flash = "Standard scenarios rebuilt from the current weights and budget."

    st.button("Rebuild the three standard scenarios from current inputs", on_click=rebuild)
    st.caption("Standard scenarios - Base: current inputs. Growth-Oriented: budget +15%, weights shifted to financial return and impact. "
               "Risk-Averse: budget -15%, costs +10%, weights shifted to risk and feasibility. All values below are editable assumptions.")

    st.subheader("Create or modify a scenario")
    NEW = "+ New scenario"
    choice = st.selectbox("Scenario", list(ss.scenarios) + [NEW])
    cur = ss.scenarios.get(choice) or Scenario("New scenario", ss.budget, dict(a.weights), 1.0, [], "")
    ids = df[COL_ID].tolist()
    names = dict(zip(df[COL_ID], df[COL_NAME]))
    with st.form(f"scen_{choice}"):
        name = st.text_input("Scenario name", cur.name)
        c1, c2 = st.columns(2)
        budget = c1.number_input("Available budget", min_value=0.0, value=float(cur.budget), step=1.0)
        mult = c2.number_input("Cost multiplier (1.10 = all costs +10%)", min_value=0.1, max_value=5.0,
                               value=float(cur.cost_multiplier), step=0.05)
        st.markdown("**Criteria weights (%)** - rescaled to 100% on use")
        wc = st.columns(len(CRITERIA_NAMES))
        wvals = {c: col.number_input(c, min_value=0.0, max_value=100.0, value=float(cur.weights[c] * 100), step=1.0,
                                     key=f"sf_{choice}_{c}") for col, c in zip(wc, CRITERIA_NAMES)}
        excl = st.multiselect("Exclude initiatives from this scenario", ids,
                              default=[i for i in cur.excluded_ids if i in ids], format_func=lambda i: f"{i} - {names[i]}")
        desc = st.text_area("Assumptions / description", cur.description)
        ok = st.form_submit_button("Save scenario", type="primary")
    if ok:
        sc = Scenario(name.strip(), budget, {c: v / 100 for c, v in wvals.items()}, mult, excl, desc)
        errs = validate_scenario(sc)
        if not sc.name:
            errs.append("Scenario name is required.")
        if sc.name != cur.name and sc.name in ss.scenarios:
            errs.append(f"A scenario named '{sc.name}' already exists.")
        if len(excl) >= len(ids):
            errs.append("At least one initiative must remain in the scenario.")
        if errs:
            for e in errs:
                st.error(e)
        else:
            if choice != NEW and choice != sc.name:
                ss.scenarios.pop(choice, None)
            ss.scenarios[sc.name] = sc
            ss.flash = f"Scenario '{sc.name}' saved."
            st.rerun()
    if choice != NEW and len(ss.scenarios) > 3:
        if st.button(f"Delete scenario '{choice}'"):
            ss.scenarios.pop(choice)
            st.rerun()

    # ---- comparison --------------------------------------------------------
    st.subheader("Scenario comparison")
    chosen = st.multiselect("Scenarios to compare", list(ss.scenarios), default=list(ss.scenarios))
    results = {}
    for n_ in chosen:
        try:
            results[n_] = run_scenario(df, ss.scenarios[n_], ss.sub_weights, ss.scale_max)
        except ValueError as e:
            st.error(f"{n_}: {e}")
    if not results:
        st.info("Select at least one valid scenario.")
    else:
        comp = compare_scenarios(results)
        summ = comp["summary"]
        st.markdown("**Assumptions (labelled inputs)**")
        ass = pd.DataFrame([{"Scenario": n_, "Budget": r.scenario.budget, "Cost multiplier": r.scenario.cost_multiplier,
                             **{f"w: {c}": f"{r.scenario.weights[c] / sum(r.scenario.weights.values()) * 100:.1f}%" for c in CRITERIA_NAMES},
                             "Excluded": ", ".join(r.scenario.excluded_ids) or "-", "Description": r.scenario.description}
                            for n_, r in results.items()])
        st.dataframe(ass, hide_index=True, **ui.stretch())
        st.markdown("**Results (recalculated from the actual model)**")
        ui.table(summ)
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_bar(name="Total investment", x=summ["Scenario"], y=summ["Total investment"], marker_color=ui.NAVY)
            fig.add_bar(name="Remaining budget", x=summ["Scenario"], y=summ["Remaining budget"], marker_color=ui.LIGHT)
            fig.add_scatter(name="Budget", x=summ["Scenario"], y=summ["Budget"], mode="markers",
                            marker=dict(symbol="line-ew", size=30, line=dict(width=3, color=ui.RED)))
            fig.update_layout(barmode="stack", title="Budget allocation by scenario")
            ui.chart(fig, 380)
        with c2:
            fig = go.Figure(go.Bar(x=summ["Scenario"], y=summ["Portfolio value"], marker_color=ui.BLUE,
                                   text=summ["Portfolio value"].round(1), textposition="outside"))
            fig.update_layout(title="Portfolio value by scenario", yaxis_title="sum of final scores")
            ui.chart(fig, 380)
        sel = comp["selection"].set_index(COL_ID)
        scols = [c for c in sel.columns if c != COL_NAME]
        fig = go.Figure(go.Heatmap(z=sel[scols].astype(int).values, x=scols, y=sel[COL_NAME], colorscale=[[0, "#E6EBF2"], [1, ui.NAVY]],
                                   showscale=False, xgap=2, ygap=2))
        fig.update_layout(title="Selected initiatives (navy = selected)", yaxis=dict(autorange="reversed"))
        ui.chart(fig, 520)
        rk = comp["ranks"].set_index(COL_ID)
        st.markdown("**Initiative ranks per scenario** (`NaN` = excluded)")
        rk["Rank spread"] = rk[scols].max(axis=1) - rk[scols].min(axis=1)
        st.dataframe(rk.sort_values("Rank spread", ascending=False), **ui.stretch())
        varying = sel[sel[scols].nunique(axis=1) > 1][COL_NAME].tolist()
        st.markdown("**Initiatives whose funding decision depends on the scenario:** " + (", ".join(varying) or "none"))

# =========================== SENSITIVITY ====================================
with tab_t:
    st.write("Test how changes in criterion weights affect scores, ranks and the optimal portfolio. "
             "Adjusted weights are renormalised to 100% before recalculation.")
    weights = a.weights
    base_scores = a.scoring.summary

    st.subheader("1. What-if: adjust weights")
    st.caption("Relative change applied to each weight (e.g. +50% multiplies the weight by 1.5), then all weights are renormalised.")

    def reset_sliders():
        for c in CRITERIA_NAMES:
            ss[f"sens_{c}"] = 0

    cols = st.columns(len(CRITERIA_NAMES))
    changes = {}
    for col, c in zip(cols, CRITERIA_NAMES):
        k = f"sens_{c}"
        if k not in ss:
            ss[k] = 0
        changes[c] = col.slider(c, -100, 200, step=5, key=k, format="%d%%")
    st.button("Reset adjustments", on_click=reset_sliders)
    try:
        new_w = adjust_weights(weights, changes)
        new_scores = compute_scores(df, new_w, ss.sub_weights, ss.scale_max).summary
        cmp_ = compare_ranking(base_scores, new_scores)
        wt = pd.DataFrame({"Criterion": CRITERIA_NAMES, "Original weight (%)": [weights[c] * 100 for c in CRITERIA_NAMES],
                           "Adjusted weight (%)": [new_w[c] * 100 for c in CRITERIA_NAMES]})
        c1, c2 = st.columns([2, 3])
        with c1:
            ui.table(wt)
        with c2:
            fig = go.Figure()
            fig.add_bar(name="Original", x=CRITERIA_NAMES, y=wt["Original weight (%)"], marker_color=ui.LIGHT)
            fig.add_bar(name="Adjusted", x=CRITERIA_NAMES, y=wt["Adjusted weight (%)"], marker_color=ui.NAVY)
            fig.update_layout(barmode="group", yaxis_title="%")
            ui.chart(fig, 280)
        moved = int((cmp_["Rank change"] != 0).sum())
        st.markdown(f"**{moved}** of {len(cmp_)} initiatives change rank.")
        ui.table(cmp_[[COL_ID, COL_NAME, "Rank (before)", "Rank (after)", "Rank change", "Final Score (before)", "Final Score (after)"]])
        d = cmp_.sort_values("Rank (before)")
        fig = go.Figure(go.Bar(x=d[COL_NAME], y=d["Rank change"],
                               marker_color=[ui.GREEN if v > 0 else ui.RED if v < 0 else ui.GREY for v in d["Rank change"]]))
        fig.update_layout(title="Rank change (positive = moves up)", xaxis_tickangle=-45)
        ui.chart(fig, 380)
        if a.optimal.status != "invalid":
            p_new = optimize_portfolio(new_scores, a.budget)
            before, after = set(a.optimal.selected_ids), set(p_new.selected_ids)
            nm = dict(zip(df[COL_ID], df[COL_NAME]))
            st.markdown(f"**Portfolio before:** {len(before)} initiatives, value {a.optimal.total_value:,.1f}  |  "
                        f"**after:** {len(after)} initiatives, value {p_new.total_value:,.1f}")
            st.markdown("Newly selected: " + (", ".join(nm[i] for i in sorted(after - before)) or "-") +
                        "  \nNo longer selected: " + (", ".join(nm[i] for i in sorted(before - after)) or "-"))
    except ValueError as e:
        st.error(str(e))

    st.divider()
    st.subheader("2. Ranking stability (one-at-a-time analysis)")
    steps = st.multiselect("Relative weight changes tested for each criterion", [-75, -50, -25, 25, 50, 75, 100],
                           default=[-50, -25, 25, 50], format_func=lambda v: f"{v:+d}%")
    if not steps:
        st.info("Select at least one change level.")
    else:
        out = one_at_a_time(df, weights, tuple(steps), ss.sub_weights, ss.scale_max,
                            budget=a.budget if a.optimal.status != "invalid" else None)
        infl, stab = out["influence"], out["stability"]
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure(go.Bar(x=infl["Mean absolute rank shift"], y=infl["Criterion"], orientation="h", marker_color=ui.NAVY))
            fig.update_layout(title="Criteria influence on the ranking", xaxis_title="mean absolute rank shift",
                              yaxis=dict(autorange="reversed"))
            ui.chart(fig, 330)
            top = infl.iloc[0]
            st.markdown(f"Most influential criterion: **{top['Criterion']}** (mean shift {top['Mean absolute rank shift']:.2f}, max {int(top['Max rank shift'])} places).")
        with c2:
            sd = stab.sort_values("Base rank")
            fig = go.Figure(go.Scatter(x=sd["Base rank"], y=sd[COL_NAME], mode="markers", marker=dict(size=9, color=ui.NAVY),
                                       error_x=dict(type="data", symmetric=False, array=(sd["Worst rank"] - sd["Base rank"]),
                                                    arrayminus=(sd["Base rank"] - sd["Best rank"]), color=ui.LIGHT)))
            fig.update_layout(title="Rank range under weight changes", xaxis_title="rank (1 = best)", yaxis=dict(autorange="reversed"))
            ui.chart(fig, 330)
        unstable = stab[stab["Unstable"]]
        if len(unstable):
            st.warning(f"Unstable rankings (rank moves by {UNSTABLE_RANGE}+ places): " + ", ".join(unstable[COL_NAME]))
        else:
            st.success(f"No initiative moves by {UNSTABLE_RANGE} or more places under the tested changes.")
        ui.table(stab)
        if "Selection frequency (%)" in stab:
            st.caption("Selection frequency = share of the tested weight settings in which the initiative is part of the optimal portfolio "
                       "(100% = robustly selected, 0% = never).")

    st.divider()
    st.subheader("3. Random weight perturbation (robustness)")
    c1, c2, c3 = st.columns(3)
    nsim = c1.number_input("Simulations", 20, 1000, 200, 20)
    spread = c2.slider("Max change per weight (+/- %)", 5, 80, 30)
    seed = c3.number_input("Random seed", 0, 10_000, 42)
    if st.button("Run simulation"):
        with st.spinner("Simulating..."):
            ss.mc = random_weight_simulation(df, weights, a.budget, int(nsim), float(spread), int(seed), ss.sub_weights, ss.scale_max)
    if ss.get("mc") is not None:
        mc = ss.mc
        if set(mc[COL_ID]) == set(df[COL_ID]):
            ui.table(mc)
            fig = go.Figure(go.Bar(x=mc[COL_NAME], y=mc["Selection frequency (%)"], marker_color=ui.NAVY))
            fig.update_layout(title="How often each initiative enters the optimal portfolio", yaxis_title="%", xaxis_tickangle=-45)
            ui.chart(fig, 380)
        else:
            st.info("Data changed since the last simulation - run it again.")
