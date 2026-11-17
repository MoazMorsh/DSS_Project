import hashlib
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.state import init_state, require_data, get_analysis
from core.schema import COL_ID, COL_NAME, COL_COST, CRITERIA_NAMES
from core.scenario_analysis import (
    Scenario,
    run_scenario,
    default_scenarios,
    compare_scenarios,
    validate_scenario,
)
from core.sensitivity_analysis import (
    adjust_weights,
    compare_ranking,
    one_at_a_time,
    random_weight_simulation,
    UNSTABLE_RANGE,
)
from core.optimization import optimize_portfolio
from core.weighted_scoring import compute_scores
from core import ui


# ============================================================
# HELPERS
# ============================================================

def simulation_signature(
    data,
    active_weights,
    budget,
    simulations,
    weight_spread,
    random_seed,
    sub_weights,
    scale_max,
):
    """Create a stable fingerprint for every input used by the simulation."""
    payload = {
        "data": data.to_json(
            orient="split",
            date_format="iso",
            default_handler=str,
        ),
        "weights": active_weights,
        "budget": float(budget),
        "simulations": int(simulations),
        "weight_spread": float(weight_spread),
        "random_seed": int(random_seed),
        "sub_weights": sub_weights,
        "scale_max": scale_max,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ============================================================
# INITIALIZATION
# ============================================================

init_state()
require_data()

ss = st.session_state
df = ss.df

ui.page_header(
    "Scenario & Sensitivity Analysis",
    "Compare alternative assumptions and test how stable "
    "the strategic recommendations are."
)

a = get_analysis()

tab_s, tab_t = st.tabs([
    "Scenario Analysis",
    "Sensitivity Analysis"
])


# ============================================================
# TAB 1 - SCENARIO ANALYSIS
# ============================================================

with tab_s:

    # --------------------------------------------------------
    # INITIAL SCENARIOS AND BASELINE CHECK
    # --------------------------------------------------------

    if not ss.scenarios:
        ss.scenarios = default_scenarios(
            a.weights,
            ss.budget
        )

    if ss.get("flash"):
        st.success(ss.pop("flash"))

    base = ss.scenarios.get("Base")

    base_is_outdated = bool(
        base
        and (
            abs(base.budget - ss.budget) > 1e-9
            or any(
                abs(base.weights[c] - a.weights[c]) > 1e-9
                for c in CRITERIA_NAMES
            )
        )
    )

    if base_is_outdated:
        st.info(
            "The saved Base scenario differs from the current "
            "budget or active weights. You can rebuild the standard "
            "scenarios in Scenario Management below."
        )

    st.caption(
        "Base uses the current assumptions. Growth-Oriented increases "
        "the budget by 15% and places greater emphasis on financial "
        "return and business impact. Risk-Averse reduces the budget "
        "by 15%, increases costs by 10%, and places greater emphasis "
        "on risk and feasibility."
    )

    # --------------------------------------------------------
    # SCENARIO COMPARISON - SHOWN FIRST
    # --------------------------------------------------------

    st.subheader("1. Scenario Comparison")

    chosen = st.multiselect(
        "Select scenarios to compare",
        list(ss.scenarios),
        default=list(ss.scenarios),
        key="scenario_compare_selection",
    )

    results = {}

    for scenario_name in chosen:
        try:
            results[scenario_name] = run_scenario(
                df,
                ss.scenarios[scenario_name],
                ss.sub_weights,
                ss.scale_max,
            )
        except ValueError as exc:
            st.error(f"{scenario_name}: {exc}")

    if not results:
        st.info(
            "Select at least one valid scenario to display the "
            "comparison results."
        )
    else:
        comp = compare_scenarios(results)
        summ = comp["summary"]

        # Scenario assumptions are available on demand.
        with st.expander(
            "View Scenario Assumptions",
            expanded=False,
        ):
            assumptions = pd.DataFrame([
                {
                    "Scenario": scenario_name,
                    "Budget": result.scenario.budget,
                    "Cost Multiplier": result.scenario.cost_multiplier,
                    **{
                        f"{criterion} Weight": (
                           f"{result.scenario.weights[criterion] / sum(result.scenario.weights.values()):.1%}"
                        )
                        for criterion in CRITERIA_NAMES
                    },
                    "Excluded Initiatives": (
                        ", ".join(result.scenario.excluded_ids) or "-"
                    ),
                    "Description": result.scenario.description,
                }
                for scenario_name, result in results.items()
            ])

            st.dataframe(
                assumptions,
                hide_index=True,
                **ui.stretch(),
            )

        st.markdown("**Scenario Results**")
        ui.table(summ)

        st.divider()
        st.markdown("**Scenario Performance Comparison**")

        col1, col2 = st.columns(2)

        with col1:
            fig = go.Figure()

            fig.add_bar(
                name="Selected Investment",
                x=summ["Scenario"],
                y=summ["Total investment"],
                marker_color=ui.NAVY,
            )

            fig.add_bar(
                name="Remaining Budget",
                x=summ["Scenario"],
                y=summ["Remaining budget"],
                marker_color=ui.LIGHT,
            )

            fig.add_scatter(
                name="Available Budget",
                x=summ["Scenario"],
                y=summ["Budget"],
                mode="markers",
                marker=dict(
                    symbol="line-ew",
                    size=30,
                    line=dict(width=3, color=ui.RED),
                ),
            )

            fig.update_layout(
                barmode="stack",
                title="Budget Allocation by Scenario",
                yaxis_title="Investment",
                legend_title="Budget Components",
            )

            ui.chart(fig, 380)

        with col2:
            fig = go.Figure(
                go.Bar(
                    x=summ["Scenario"],
                    y=summ["Portfolio value"],
                    marker_color=ui.BLUE,
                    text=summ["Portfolio value"].round(1),
                    textposition="outside",
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        "Portfolio Value: %{y:.2f} points"
                        "<extra></extra>"
                    ),
                )
            )

            fig.update_layout(
                title="Portfolio Value by Scenario",
                yaxis_title="Total Weighted Score (Points)",
            )

            ui.chart(fig, 380)

        # ----------------------------------------------------
        # INITIATIVE SELECTION COMPARISON
        # ----------------------------------------------------

        st.divider()
        st.markdown("**Initiative Selection Across Scenarios**")

        selection = comp["selection"].set_index(COL_ID)
        scenario_columns = [
            column
            for column in selection.columns
            if column != COL_NAME
        ]

        fig = go.Figure(
            go.Heatmap(
                z=selection[scenario_columns].astype(int).values,
                x=scenario_columns,
                y=selection[COL_NAME],
                colorscale=[
                    [0, "#E6EBF2"],
                    [1, ui.NAVY],
                ],
                showscale=False,
                xgap=2,
                ygap=2,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Scenario: %{x}<br>"
                    "Selection: %{z}"
                    "<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title="Selected Initiatives by Scenario",
            yaxis=dict(autorange="reversed"),
            xaxis_title="Scenario",
        )

        ui.chart(fig, 520)
        st.caption("Navy = Selected | Light grey = Not selected")

        # ----------------------------------------------------
        # RANKING COMPARISON
        # ----------------------------------------------------

        st.subheader("Initiative Ranking Across Scenarios")

        ranking = comp["ranks"].set_index(COL_ID)

        st.caption(
            "A blank rank indicates that the initiative was excluded "
            "from that scenario."
        )

        ranking["Rank Spread"] = (
            ranking[scenario_columns].max(axis=1)
            - ranking[scenario_columns].min(axis=1)
        )

        st.dataframe(
            ranking.sort_values(
                "Rank Spread",
                ascending=False,
            ),
            **ui.stretch(),
        )

        varying = selection[
            selection[scenario_columns].nunique(axis=1) > 1
        ][COL_NAME].tolist()

        st.markdown(
            "**Initiatives whose funding decision changes across "
            "scenarios:** "
            + (", ".join(varying) or "None")
        )

    # --------------------------------------------------------
    # SCENARIO MANAGEMENT - COLLAPSED BY DEFAULT
    # --------------------------------------------------------

    st.divider()

    with st.expander(
        "Scenario Management - Create, Modify or Delete",
        expanded=False,
    ):
        st.subheader("Manage Scenarios")

        if st.button(
            "Rebuild Standard Scenarios from Current Inputs",
            key="rebuild_standard_scenarios",
        ):
            ss.scenarios = default_scenarios(
                a.weights,
                ss.budget,
            )
            ss.flash = (
                "Standard scenarios rebuilt from current inputs."
            )
            st.rerun()

        NEW_SCENARIO = "+ New Scenario"

        scenario_choice = st.selectbox(
            "Select a scenario to edit",
            list(ss.scenarios) + [NEW_SCENARIO],
            key="scenario_edit_choice",
        )

        current_scenario = (
            ss.scenarios.get(scenario_choice)
            or Scenario(
                "New Scenario",
                ss.budget,
                dict(a.weights),
                1.0,
                [],
                "",
            )
        )

        initiative_ids = df[COL_ID].tolist()
        initiative_names = dict(
            zip(df[COL_ID], df[COL_NAME])
        )

        with st.form(f"scenario_form_{scenario_choice}"):

            scenario_name = st.text_input(
                "Scenario Name",
                value=current_scenario.name,
            )

            col1, col2 = st.columns(2)

            scenario_budget = col1.number_input(
                "Available Budget",
                min_value=0.0,
                value=float(current_scenario.budget),
                step=1.0,
            )

            cost_multiplier = col2.number_input(
                "Cost Multiplier",
                min_value=0.1,
                max_value=5.0,
                value=float(current_scenario.cost_multiplier),
                step=0.05,
                help=(
                    "For example, 1.10 means all initiative "
                    "costs increase by 10%."
                ),
            )

            st.markdown("**Evaluation Criteria Weights (%)**")

            weight_columns = st.columns(len(CRITERIA_NAMES))

            scenario_weight_values = {
                criterion: column.number_input(
                    criterion,
                    min_value=0.0,
                    max_value=100.0,
                    value=float(
                        current_scenario.weights[criterion] * 100
                    ),
                    step=1.0,
                    key=f"scenario_weight_{scenario_choice}_{criterion}",
                )
                for column, criterion in zip(
                    weight_columns,
                    CRITERIA_NAMES,
                )
            }

            excluded_ids = st.multiselect(
                "Exclude Initiatives",
                initiative_ids,
                default=[
                    initiative_id
                    for initiative_id in current_scenario.excluded_ids
                    if initiative_id in initiative_ids
                ],
                format_func=lambda initiative_id: (
                    f"{initiative_id} - "
                    f"{initiative_names[initiative_id]}"
                ),
            )

            description = st.text_area(
                "Assumptions / Scenario Description",
                value=current_scenario.description,
            )

            save_scenario = st.form_submit_button(
                "Save Scenario",
                type="primary",
                use_container_width=True,
            )

        if save_scenario:
            new_scenario = Scenario(
                scenario_name.strip(),
                scenario_budget,
                {
                    criterion: value / 100
                    for criterion, value
                    in scenario_weight_values.items()
                },
                cost_multiplier,
                excluded_ids,
                description,
            )

            errors = validate_scenario(new_scenario)

            if not new_scenario.name:
                errors.append("Scenario name is required.")

            if (
                new_scenario.name != current_scenario.name
                and new_scenario.name in ss.scenarios
            ):
                errors.append(
                    f"A scenario named '{new_scenario.name}' already exists."
                )

            if len(excluded_ids) >= len(initiative_ids):
                errors.append(
                    "At least one initiative must remain in the scenario."
                )

            if errors:
                for error in errors:
                    st.error(error)
            else:
                if (
                    scenario_choice != NEW_SCENARIO
                    and scenario_choice != new_scenario.name
                ):
                    ss.scenarios.pop(scenario_choice, None)

                ss.scenarios[new_scenario.name] = new_scenario
                ss.flash = (
                    f"Scenario '{new_scenario.name}' saved successfully."
                )
                st.rerun()

        if scenario_choice != NEW_SCENARIO:
            st.warning(
                "Deleting a scenario is permanent for the current "
                "session. The standard scenarios can be rebuilt."
            )

            if st.button(
                f"Delete Scenario '{scenario_choice}'",
                key=f"delete_scenario_{scenario_choice}",
            ):
                ss.scenarios.pop(scenario_choice, None)
                ss.flash = (
                    f"Scenario '{scenario_choice}' deleted."
                )
                st.rerun()


# ============================================================
# TAB 2 - SENSITIVITY ANALYSIS
# ============================================================

with tab_t:

    st.markdown(
        "Test how changes in evaluation criteria weights affect "
        "initiative scores, rankings and portfolio selection."
    )

    st.caption(
        "Adjusted weights are automatically normalised to 100% "
        "before recalculating the decision model."
    )

    weights = a.weights
    base_scores = a.scoring.summary

    # --------------------------------------------------------
    # SECTION 1 - WHAT-IF WEIGHT ADJUSTMENT
    # --------------------------------------------------------

    st.divider()
    st.subheader("1. What-If Weight Adjustment")

    st.caption(
        "Relative percentage changes are applied to each criterion. "
        "For example, +50% multiplies its original weight by 1.5."
    )

    def reset_sensitivity_sliders():
        for criterion in CRITERIA_NAMES:
            ss[f"sens_{criterion}"] = 0

    slider_columns = st.columns(len(CRITERIA_NAMES))
    changes = {}

    for column, criterion in zip(
        slider_columns,
        CRITERIA_NAMES,
    ):
        key = f"sens_{criterion}"

        if key not in ss:
            ss[key] = 0

        changes[criterion] = column.slider(
            criterion,
            min_value=-100,
            max_value=200,
            step=5,
            key=key,
            format="%d%%",
        )

    st.button(
        "Reset Adjustments",
        on_click=reset_sensitivity_sliders,
    )

    try:
        new_weights = adjust_weights(
            weights,
            changes,
        )

        new_scores = compute_scores(
            df,
            new_weights,
            ss.sub_weights,
            ss.scale_max,
        ).summary

        ranking_comparison = compare_ranking(
            base_scores,
            new_scores,
        )

        weight_comparison = pd.DataFrame({
            "Criterion": CRITERIA_NAMES,
            "Original Weight (%)": [
                weights[criterion] * 100
                for criterion in CRITERIA_NAMES
            ],
            "Adjusted Weight (%)": [
                new_weights[criterion] * 100
                for criterion in CRITERIA_NAMES
            ],
        })

        col1, col2 = st.columns([2, 3])

        with col1:
            ui.table(weight_comparison)

        with col2:
            fig = go.Figure()

            fig.add_bar(
                name="Original",
                x=CRITERIA_NAMES,
                y=weight_comparison["Original Weight (%)"],
                marker_color=ui.LIGHT,
            )

            fig.add_bar(
                name="Adjusted",
                x=CRITERIA_NAMES,
                y=weight_comparison["Adjusted Weight (%)"],
                marker_color=ui.NAVY,
            )

            fig.update_layout(
                barmode="group",
                title="Original vs Adjusted Weights",
                yaxis_title="Weight (%)",
            )

            ui.chart(fig, 300)

        # RANKING CHANGES

        st.divider()

        moved = int(
            (ranking_comparison["Rank change"] != 0).sum()
        )

        st.markdown(
            f"**{moved} of {len(ranking_comparison)} initiatives "
            "change their ranking after weight adjustments.**"
        )

        ui.table(
            ranking_comparison[
                [
                    COL_ID,
                    COL_NAME,
                    "Rank (before)",
                    "Rank (after)",
                    "Rank change",
                    "Final Score (before)",
                    "Final Score (after)",
                ]
            ]
        )

        chart_data = ranking_comparison.sort_values(
            "Rank (before)"
        )

        fig = go.Figure(
            go.Bar(
                x=chart_data[COL_NAME],
                y=chart_data["Rank change"],
                marker_color=[
                    ui.GREEN if value > 0
                    else ui.RED if value < 0
                    else ui.GREY
                    for value in chart_data["Rank change"]
                ],
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Rank Change: %{y}"
                    "<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            title="Impact of Weight Changes on Initiative Ranking",
            xaxis_title="Strategic Initiatives",
            yaxis_title="Rank Change",
            xaxis_tickangle=-45,
        )

        ui.chart(fig, 380)

        st.caption(
            "A positive rank change indicates an improvement in "
            "ranking (moving closer to Rank 1); a negative rank "
            "change indicates a decline."
        )

        # PORTFOLIO IMPACT

        if a.optimal.status != "invalid":
            new_portfolio = optimize_portfolio(
                new_scores,
                a.budget,
            )

            original_selected = set(a.optimal.selected_ids)
            adjusted_selected = set(new_portfolio.selected_ids)

            initiative_names = dict(
                zip(df[COL_ID], df[COL_NAME])
            )

            st.divider()
            st.subheader("Impact on Portfolio Selection")

            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Original Portfolio Value",
                    f"{a.optimal.total_value:,.1f}",
                )

            with col2:
                st.metric(
                    "Adjusted Portfolio Value",
                    f"{new_portfolio.total_value:,.1f}",
                )

            st.markdown(
                f"**Original portfolio:** {len(original_selected)} initiatives"
                f" | **Adjusted portfolio:** {len(adjusted_selected)} initiatives"
            )

            st.markdown(
                "**Newly selected:** "
                + (
                    ", ".join(
                        initiative_names[i]
                        for i in sorted(
                            adjusted_selected - original_selected
                        )
                    )
                    or "-"
                )
            )

            st.markdown(
                "**No longer selected:** "
                + (
                    ", ".join(
                        initiative_names[i]
                        for i in sorted(
                            original_selected - adjusted_selected
                        )
                    )
                    or "-"
                )
            )

    except ValueError as exc:
        st.error(str(exc))

    # --------------------------------------------------------
    # SECTION 2 - ONE-AT-A-TIME ANALYSIS
    # --------------------------------------------------------

    st.divider()
    st.subheader("2. Ranking Stability - One-at-a-Time Analysis")

    st.caption(
        "Each criterion is adjusted individually while the other "
        "criteria remain unchanged. This identifies which criteria "
        "have the greatest influence on initiative rankings."
    )

    steps = st.multiselect(
        "Relative Weight Changes to Test",
        [-75, -50, -25, 25, 50, 75, 100],
        default=[-50, -25, 25, 50],
        format_func=lambda value: f"{value:+d}%",
    )

    if not steps:
        st.info("Select at least one weight change level.")
    else:
        out = one_at_a_time(
            df,
            weights,
            tuple(steps),
            ss.sub_weights,
            ss.scale_max,
            budget=(
                a.budget
                if a.optimal.status != "invalid"
                else None
            ),
        )

        influence = out["influence"]
        stability = out["stability"]

        col1, col2 = st.columns(2)

        with col1:
            fig = go.Figure(
                go.Bar(
                    x=influence["Mean absolute rank shift"],
                    y=influence["Criterion"],
                    orientation="h",
                    marker_color=ui.NAVY,
                )
            )

            fig.update_layout(
                title="Criteria Influence on Ranking",
                xaxis_title="Mean Absolute Rank Shift",
                yaxis=dict(autorange="reversed"),
            )

            ui.chart(fig, 330)

            if not influence.empty:
                most_influential = influence.iloc[0]

                st.markdown(
                    f"**Most influential criterion:** "
                    f"{most_influential['Criterion']} "
                    f"(mean shift: "
                    f"{most_influential['Mean absolute rank shift']:.2f}; "
                    f"maximum shift: "
                    f"{int(most_influential['Max rank shift'])} places)."
                )

        with col2:
            stability_sorted = stability.sort_values("Base rank")

            fig = go.Figure(
                go.Scatter(
                    x=stability_sorted["Base rank"],
                    y=stability_sorted[COL_NAME],
                    mode="markers",
                    marker=dict(
                        size=9,
                        color=ui.NAVY,
                    ),
                    error_x=dict(
                        type="data",
                        symmetric=False,
                        array=(
                            stability_sorted["Worst rank"]
                            - stability_sorted["Base rank"]
                        ),
                        arrayminus=(
                            stability_sorted["Base rank"]
                            - stability_sorted["Best rank"]
                        ),
                        color=ui.LIGHT,
                    ),
                    hovertemplate=(
                        "<b>%{y}</b><br>"
                        "Base Rank: %{x}"
                        "<extra></extra>"
                    ),
                )
            )

            fig.update_layout(
                title="Ranking Range Under Weight Changes",
                xaxis_title="Rank (1 = Best)",
                yaxis=dict(autorange="reversed"),
            )

            ui.chart(fig, 330)

        # ACCURATE RANK-RANGE INTERPRETATION

        rank_range = (
            stability["Worst rank"] - stability["Best rank"]
        )

        unstable = stability[
            rank_range >= UNSTABLE_RANGE
        ]

        if not unstable.empty:
            unstable_details = [
                (
                    f"{row[COL_NAME]} "
                    f"(Rank {row['Best rank']}–{row['Worst rank']})"
                )
                for _, row in unstable.iterrows()
            ]

            st.warning(
                f"Rank range of {UNSTABLE_RANGE}+ positions: "
                + ", ".join(unstable_details)
            )
        else:
            st.success(
                f"No initiative has a best-to-worst rank range "
                f"of {UNSTABLE_RANGE} or more positions under "
                "the tested weight changes."
            )

        ui.table(stability)

        if "Selection frequency (%)" in stability.columns:
            st.caption(
                "Selection frequency represents the percentage of "
                "tested weight settings in which an initiative is "
                "included in the optimal portfolio. 100% indicates "
                "consistently selected; 0% indicates never selected."
            )

    # --------------------------------------------------------
    # SECTION 3 - RANDOM WEIGHT SIMULATION
    # --------------------------------------------------------

    st.divider()
    st.subheader(
        "3. Random Weight Perturbation - Robustness Analysis"
    )

    st.caption(
        "Simulate alternative criteria-weight combinations to test "
        "how consistently each initiative is selected."
    )

    col1, col2, col3 = st.columns(3)

    number_of_simulations = col1.number_input(
        "Number of Simulations",
        min_value=20,
        max_value=1000,
        value=200,
        step=20,
        key="mc_number_of_simulations",
    )

    weight_spread = col2.slider(
        "Maximum Weight Change (+/- %)",
        min_value=5,
        max_value=80,
        value=30,
        key="mc_weight_spread",
    )

    random_seed = col3.number_input(
        "Random Seed",
        min_value=0,
        max_value=10000,
        value=42,
        key="mc_random_seed",
    )

    current_simulation_signature = simulation_signature(
        df,
        weights,
        a.budget,
        number_of_simulations,
        weight_spread,
        random_seed,
        ss.sub_weights,
        ss.scale_max,
    )

    if st.button(
        "Run Robustness Simulation",
        type="primary",
        key="run_robustness_simulation",
    ):
        with st.spinner(
            "Running random weight simulations..."
        ):
            ss.mc = random_weight_simulation(
                df,
                weights,
                a.budget,
                int(number_of_simulations),
                float(weight_spread),
                int(random_seed),
                ss.sub_weights,
                ss.scale_max,
            )
            ss.mc_signature = current_simulation_signature

        st.success("Robustness simulation completed.")

    # --------------------------------------------------------
    # DISPLAY ONLY CURRENT SIMULATION RESULTS
    # --------------------------------------------------------

    stored_signature = ss.get("mc_signature")
    stored_simulation = ss.get("mc")

    if stored_simulation is not None:
        if stored_signature != current_simulation_signature:
            st.info(
                "The dataset or simulation inputs have changed since "
                "the last run. The previous simulation is no longer "
                "current. Run the robustness simulation again to "
                "generate updated results."
            )
        else:
            mc = stored_simulation

            if set(mc[COL_ID]) == set(df[COL_ID]):
                st.divider()
                st.markdown("**Current Simulation Results**")

                ui.table(mc)

                fig = go.Figure(
                    go.Bar(
                        x=mc[COL_NAME],
                        y=mc["Selection frequency (%)"],
                        marker_color=ui.NAVY,
                        text=mc["Selection frequency (%)"].round(1),
                        textposition="outside",
                        hovertemplate=(
                            "<b>%{x}</b><br>"
                            "Selection Frequency: %{y:.1f}%"
                            "<extra></extra>"
                        ),
                    )
                )

                fig.update_layout(
                    title="Initiative Selection Frequency",
                    yaxis_title="Selection Frequency (%)",
                    xaxis_title="Strategic Initiatives",
                    yaxis=dict(range=[0, 110]),
                    xaxis_tickangle=-45,
                )

                ui.chart(fig, 400)

                st.caption(
                    "Selection frequency shows how often each "
                    "initiative is included in the optimal portfolio "
                    "across the simulated weight combinations."
                )
            else:
                st.info(
                    "The initiative list differs from the stored "
                    "simulation. Run the simulation again."
                )
