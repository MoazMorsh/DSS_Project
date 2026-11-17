"""Shared look-and-feel (navy / white enterprise style) and small display helpers."""
import streamlit as st
import plotly.graph_objects as go
import plotly.io as pio

NAVY = "#0B2545"
BLUE = "#2F6DB5"
LIGHT = "#8DA9C4"
BG = "#F1F4F9"
GREEN = "#2E7D32"
AMBER = "#ED6C02"
RED = "#C62828"
GREY = "#9AA5B1"
CRIT_COLORS = ["#0B2545", "#2F6DB5", "#6FA8DC", "#F2A541", "#9AA5B1"]

_template = go.layout.Template(pio.templates["plotly_white"])
_template.layout.font = dict(family="Segoe UI, Arial, sans-serif", size=12, color="#1B2A41")
_template.layout.colorway = CRIT_COLORS
pio.templates["dss"] = _template
pio.templates.default = "dss"

_STRETCH_NEW = tuple(int(x) for x in st.__version__.split(".")[:2]) >= (1, 50)


def stretch():
    """Width kwarg that works on old and new Streamlit versions."""
    return {"width": "stretch"} if _STRETCH_NEW else {"use_container_width": True}


def inject_css():
    st.markdown(f"""
    <style>
    .block-container {{padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px;}}
    .brand {{background: linear-gradient(90deg, {NAVY} 0%, #13315C 100%); color: #fff;
             padding: 14px 22px; border-radius: 8px; margin-bottom: 14px;}}
    .brand .t {{font-size: 1.15rem; font-weight: 700; letter-spacing: .2px;}}
    .brand .s {{font-size: .85rem; opacity: .85;}}
    h1, h2, h3 {{color: {NAVY};}}
    .kpi {{background: #fff; border: 1px solid #DCE3EC; border-left: 5px solid {NAVY};
           border-radius: 8px; padding: 12px 14px; height: 100%; box-shadow: 0 1px 2px rgba(11,37,69,.06);}}
    .kpi .l {{font-size: .72rem; text-transform: uppercase; letter-spacing: .6px; color: #5B6B82; font-weight: 600;}}
    .kpi .v {{font-size: 1.45rem; font-weight: 700; color: {NAVY}; line-height: 1.25; word-break: break-word;}}
    .kpi .d {{font-size: .78rem; color: #5B6B82;}}
    .pill {{display:inline-block; padding: 2px 10px; border-radius: 12px; font-size: .75rem; font-weight: 600;}}
    .pill.ok {{background:#E3F2E5; color:{GREEN};}} .pill.warn {{background:#FFF1E0; color:{AMBER};}}
    .pill.bad {{background:#FDE7E7; color:{RED};}} .pill.info {{background:#E4ECF7; color:{NAVY};}}
    .foot {{text-align:center; color:#5B6B82; font-size:.8rem; border-top:1px solid #DCE3EC;
            margin-top: 2.5rem; padding-top: .8rem;}}
    [data-testid="stSidebar"] {{background: {BG};}}
    </style>""", unsafe_allow_html=True)


def brand_bar():
    st.markdown("""<div class="brand"><div class="t">Strategic Intelligence &amp; Decision Support</div>
    <div class="s">Strategic Initiative Prioritization Platform</div></div>""", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def kpi_cards(items, per_row=4):
    """items: list of (label, value, detail)."""
    for start in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for col, (label, value, detail) in zip(cols, items[start:start + per_row]):
            col.markdown(f"""<div class="kpi"><div class="l">{label}</div>
                <div class="v">{value}</div><div class="d">{detail}</div></div>""", unsafe_allow_html=True)
        st.write("")


def pill(text: str, kind: str = "info") -> str:
    return f'<span class="pill {kind}">{text}</span>'


def chart(fig: go.Figure, height: int = 400, **layout):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.2), **layout)
    st.plotly_chart(fig, **stretch())


def table(df, round_to: int = 2, **kwargs):
    d = df.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(round_to)
    st.dataframe(d, hide_index=True, **stretch(), **kwargs)


def footer():
    st.markdown('<div class="foot">Academic Prototype | Advanced Decision Support Systems</div>',
                unsafe_allow_html=True)


def sidebar_status(ss, source: str):
    """Global inputs in the sidebar: the budget is a CONSTRAINT shared by all pages."""
    with st.sidebar:
        st.markdown("### Global inputs")
        if "pending_budget" in ss:                      # set programmatically by another page
            ss.budget_input = float(ss.pop("pending_budget"))
        if "budget_input" not in ss:
            ss.budget_input = float(ss.budget)
        st.number_input("Available budget (same unit as cost)", min_value=0.0, step=1.0,
                        format="%.2f", key="budget_input",
                        help="A decision constraint (not a weighted criterion). Changing it recalculates the optimal portfolio on every page.")
        ss.budget = float(ss.budget_input)             # plain key: survives page switches
        st.markdown(f"**Data:** {ss.data_source}  \n**Initiatives:** {len(ss.df) if ss.df is not None else 0}  \n"
                    f"**Weights:** {source}")
        st.caption("Session data is temporary. Export your work from the Data Management and Decision Report pages.")
