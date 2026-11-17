import streamlit as st
import pandas as pd

from core.state import init_state, set_data, set_budget, require_data
from core.schema import (ALL_COLUMNS, REQUIRED_COLUMNS, OPTIONAL_COLUMNS, COL_ID, COL_NAME, COL_COST,
                         ALL_SUBCRITERIA, QUAL_COLUMNS, SCORE_DEFINITIONS_BENEFIT, SCORE_DEFINITIONS_RISK, CRITERIA)
from core.validation import validate_initiatives
from core.data_processing import (load_sample, read_uploaded, template_bytes, dataframe_to_excel_bytes)
from core import ui

init_state()
ss = st.session_state
ui.page_header("Data Management", "Load, validate, edit and export the strategic initiatives.")
if ss.get("data_flash"):
    st.success(ss.pop("data_flash"))


def show_messages(res):
    for e in res.errors:
        st.error(e)
    for w in res.warnings:
        st.warning(w)


def on_scale_change():
    new = ss.scale_sel
    if ss.df is not None:
        res = validate_initiatives(ss.df, new)
        if not res.is_valid:
            ss.scale_msg = f"Cannot change the scale to 1-{new}: existing ratings are outside it. " + res.errors[0]
            ss.scale_sel = ss.scale_max
            return
    ss.scale_max = new
    ss.scale_msg = ""


tab_load, tab_prev, tab_edit, tab_tpl = st.tabs(["Load data", "Preview & validation", "Add / edit / delete", "Template & definitions"])

with tab_load:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Sample dataset")
        st.write("15 fictional strategic initiatives across business functions.")
        if st.button("Load sample dataset", type="primary"):
            res = validate_initiatives(load_sample(), ss.scale_max)
            if res.is_valid:
                set_data(res.data, "Illustrative sample dataset (fictional)")
                set_budget(round(res.data[COL_COST].sum() * 0.5))
                ss.data_flash = "Sample dataset loaded. Budget reset to 50% of total cost (adjust it in the sidebar)."
                st.rerun()
            else:
                show_messages(res)
        st.subheader("Rating scale")
        ss.setdefault("scale_sel", ss.scale_max)
        st.selectbox("Maximum rating for qualitative criteria (minimum is 1)", list(range(3, 11)),
                     key="scale_sel", on_change=on_scale_change)
        if ss.get("scale_msg"):
            st.error(ss.scale_msg)
    with c2:
        st.subheader("Upload Excel / CSV")
        up = st.file_uploader("Upload initiatives", type=["xlsx", "xls", "csv"],
                              help="Use the template from the 'Template & definitions' tab.")
        if up is not None:
            try:
                raw = read_uploaded(up, up.name)
                res = validate_initiatives(raw, ss.scale_max)
            except Exception as e:
                st.error(f"Could not read the file: {e}")
                res = None
            if res is not None:
                show_messages(res)
                if res.is_valid:
                    st.success(f"Validation passed: {len(res.data)} initiatives.")
                    ui.table(res.data.head(8))
                    if st.button("Use this dataset"):
                        set_data(res.data, f"Uploaded: {up.name}")
                        set_budget(round(res.data[COL_COST].sum() * 0.5))
                        ss.data_flash = f"Dataset applied ({len(res.data)} initiatives). Budget set to 50% of total cost - adjust it in the sidebar."
                        st.rerun()
                else:
                    st.info("Fix the listed problems in your file and upload it again.")

with tab_prev:
    require_data()
    df = ss.df
    st.caption(f"Source: {ss.data_source}")
    res = validate_initiatives(df, ss.scale_max)
    if res.is_valid:
        st.success("All validation checks passed: required columns present, no missing/invalid values, "
                   f"unique IDs, costs > 0, ratings within 1-{ss.scale_max}.")
    show_messages(res)
    k = st.columns(4)
    k[0].metric("Initiatives", len(df))
    k[1].metric("Total cost", f"{df[COL_COST].sum():,.1f}")
    k[2].metric("Business functions", df["Business Function"].replace("", pd.NA).nunique())
    k[3].metric("Average cost", f"{df[COL_COST].mean():,.1f}")
    ui.table(df)
    with st.expander("Descriptive statistics"):
        num = [c for c in df.columns if df[c].dtype.kind in "fi"]
        st.dataframe(df[num].describe().round(2).T, **ui.stretch())

with tab_edit:
    require_data()
    st.write("Edit cells directly, add rows with the **+** at the bottom of the table, or delete rows "
             "(select the row checkbox, then press Delete). Press **Save changes** to validate and apply.")
    cfg = {c: st.column_config.NumberColumn(c, min_value=1, max_value=ss.scale_max, step=1) for c in QUAL_COLUMNS}
    cfg[COL_COST] = st.column_config.NumberColumn(COL_COST, min_value=0.0, format="%.2f")
    edited = st.data_editor(ss.df, num_rows="dynamic", column_config=cfg, hide_index=True,
                            key=f"editor_{ss.df_version}", **ui.stretch())
    if st.button("Save changes", type="primary"):
        res = validate_initiatives(edited, ss.scale_max)
        if res.is_valid:
            ss.df = res.data
            ss.df_version += 1
            ss.scenarios = {}
            ss.data_source = ss.data_source if ss.data_source.endswith("(edited)") else ss.data_source + " (edited)"
            ss.data_flash = "Changes saved. All analyses have been recalculated."
            st.rerun()
        else:
            show_messages(res)
            st.info("Changes were NOT applied.")
    st.divider()
    st.subheader("Delete initiatives")
    labels = {r[COL_ID]: f"{r[COL_ID]} - {r[COL_NAME]}" for _, r in ss.df.iterrows()}
    to_del = st.multiselect("Select initiatives to delete", list(labels), format_func=labels.get)
    if st.button("Delete selected", disabled=not to_del):
        remaining = ss.df[~ss.df[COL_ID].isin(to_del)].reset_index(drop=True)
        if remaining.empty:
            st.error("Cannot delete every initiative.")
        else:
            ss.df = remaining
            ss.df_version += 1
            ss.scenarios = {}
            ss.data_flash = f"Deleted {len(to_del)} initiative(s)."
            st.rerun()

with tab_tpl:
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download Excel template", template_bytes(), "initiatives_template.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    if ss.df is not None:
        c2.download_button("Download current data (Excel)", dataframe_to_excel_bytes(ss.df), "current_initiatives.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        c3.download_button("Download current data (CSV)", ss.df.to_csv(index=False).encode(), "current_initiatives.csv", "text/csv")
    st.subheader("Input fields")
    rows = [(COL_ID, "Required", "Unique text identifier", "-"), (COL_NAME, "Required", "Text", "-"),
            ("Description", "Optional", "Text", "-"), ("Business Function", "Optional", "Text", "-"),
            (COL_COST, "Required", "Number > 0 (investment; budget constraint, NOT a criterion)", "Constraint")]
    for crit, subs in CRITERIA.items():
        for s_ in subs:
            kind = f"Rating 1-{ss.scale_max}" if s_.kind == "qual" else "Number"
            rows.append((s_.label, "Required", kind, f"{crit} | " + ("higher = better" if s_.direction == "benefit" else "higher = WORSE (inverted by the system)")))
    st.dataframe(pd.DataFrame(rows, columns=["Column", "Required?", "Type", "Criterion / direction"]), hide_index=True, **ui.stretch())
    st.subheader("Score definitions (1-5)")
    st.dataframe(pd.DataFrame({"Score": range(1, 6),
                               "Benefit criteria": [SCORE_DEFINITIONS_BENEFIT[i] for i in range(1, 6)],
                               "Risk / complexity criteria": [SCORE_DEFINITIONS_RISK[i] for i in range(1, 6)]}),
                 hide_index=True, **ui.stretch())
