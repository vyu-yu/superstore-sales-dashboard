"""Superstore 电商销售与经营特征交互式 Dashboard。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from charts import (
    PLOTLY_CONFIG,
    create_discount_profit_chart,
    create_monthly_profit_chart,
    create_monthly_sales_chart,
    create_region_chart,
    create_returns_chart,
    create_sales_profit_scatter,
    create_state_map,
    create_subcategory_chart,
)
from data_utils import (
    CATEGORY_LABELS,
    REGION_LABELS,
    SEGMENT_LABELS,
    aggregate_discount,
    aggregate_monthly,
    aggregate_subcategory,
    apply_filters,
    calculate_kpis,
    format_compact_currency,
    format_currency,
    format_integer,
    format_percent,
    load_data,
    month_label,
    validate_source_data,
)


st.set_page_config(
    page_title="Superstore 电商经营分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


CSS = """
<style>
    :root {
        --page-bg: #f5f6f8;
        --surface: #ffffff;
        --ink: #202a3b;
        --muted: #667085;
        --line: #e2e6ec;
        --accent: #3b5ccc;
    }
    .stApp { background: var(--page-bg); color: var(--ink); }
    .block-container {
        max-width: 1500px;
        padding-top: 1.35rem;
        padding-bottom: 3.5rem;
    }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.02em; }
    h1 { font-size: clamp(2rem, 3vw, 3rem) !important; line-height: 1.08 !important; margin-bottom: .5rem !important; }
    h2 { font-size: 1.45rem !important; margin-top: 1.8rem !important; }
    h3 { font-size: 1.08rem !important; margin-top: .5rem !important; }
    .project-kicker {
        color: var(--accent);
        font-size: .78rem;
        font-weight: 700;
        letter-spacing: .11em;
        text-transform: uppercase;
        margin-bottom: .55rem;
    }
    .project-subtitle {
        color: #4e5d73;
        font-size: 1.05rem;
        max-width: 960px;
        line-height: 1.65;
        margin-bottom: .45rem;
    }
    .project-meta { color: var(--muted); font-size: .86rem; margin-bottom: 1.2rem; }
    .section-rule { border-top: 1px solid var(--line); margin: 1.35rem 0 .25rem; }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 1rem 1.05rem .9rem;
        min-height: 118px;
        box-shadow: 0 1px 2px rgba(20, 30, 50, .035);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); font-weight: 600; }
    [data-testid="stMetricValue"] { color: var(--ink); font-size: clamp(1.55rem, 2.2vw, 2.15rem); }
    [data-testid="stPlotlyChart"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: .25rem;
    }
    [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 8px;
    }
    div[data-testid="stAlert"] { border-radius: 6px; }
    .filter-note { color: var(--muted); font-size: .82rem; margin-top: -.35rem; margin-bottom: .55rem; }
    .footer-note { color: var(--muted); font-size: .82rem; line-height: 1.65; }
    @media (max-width: 900px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        h1 { font-size: 2rem !important; }
    }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def dataframe_to_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def render_section_heading(title: str, caption: str) -> None:
    st.markdown('<div class="section-rule"></div>', unsafe_allow_html=True)
    st.subheader(title)
    st.caption(caption)


def markdown_currency(value: float | int | None) -> str:
    """避免 Streamlit Markdown 将美元符号解释为数学公式定界符。"""
    return format_currency(value).replace("$", "&#36;")


try:
    source_df = load_data()
    baseline = validate_source_data(source_df)
except (FileNotFoundError, ValueError, TypeError) as error:
    st.error(f"Dashboard 无法启动：{error}")
    st.stop()


st.markdown('<div class="project-kicker">DATA VISUALIZATION · COURSE PROJECT</div>', unsafe_allow_html=True)
st.title("Superstore 电商销售与经营特征可视化分析")
st.markdown(
    '<div class="project-subtitle">'
    "基于 2016—2019 年交易明细，从时间、地区、商品结构及折扣等维度分析销售规模与盈利表现。"
    "</div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="project-meta">数据来源：Tableau Sample - Superstore　·　'
    f"数据范围：{baseline['date_min']:%Y-%m-%d} 至 {baseline['date_max']:%Y-%m-%d}</div>",
    unsafe_allow_html=True,
)


st.subheader("全局筛选")
st.markdown('<div class="filter-note">留空表示选择全部；所有指标、核心图和辅助分析将同步更新。</div>', unsafe_allow_html=True)
filter_columns = st.columns(4, gap="medium")
year_options = sorted(source_df.loc[source_df["Order Year"].notna(), "Order Year"].astype(int).unique().tolist())
region_options = sorted(source_df.loc[source_df["Region"].notna(), "Region"].unique().tolist())
category_options = sorted(source_df.loc[source_df["Category"].notna(), "Category"].unique().tolist())
segment_options = sorted(source_df.loc[source_df["Segment"].notna(), "Segment"].unique().tolist())

with filter_columns[0]:
    selected_years = st.multiselect(
        "订单年份",
        options=year_options,
        default=[],
        placeholder="全部年份",
    )
with filter_columns[1]:
    selected_regions = st.multiselect(
        "地区",
        options=region_options,
        default=[],
        format_func=lambda value: REGION_LABELS.get(value, value),
        placeholder="全部地区",
    )
with filter_columns[2]:
    selected_categories = st.multiselect(
        "商品类别",
        options=category_options,
        default=[],
        format_func=lambda value: CATEGORY_LABELS.get(value, value),
        placeholder="全部类别",
    )
with filter_columns[3]:
    selected_segments = st.multiselect(
        "客户类型",
        options=segment_options,
        default=[],
        format_func=lambda value: SEGMENT_LABELS.get(value, value),
        placeholder="全部类型",
    )

filtered_df = apply_filters(
    source_df,
    years=selected_years,
    regions=selected_regions,
    categories=selected_categories,
    segments=selected_segments,
)

if filtered_df.empty:
    st.warning("当前筛选条件下暂无数据，请调整筛选条件。")
    st.stop()


kpis = calculate_kpis(filtered_df)
kpi_columns = st.columns(4, gap="medium")
with kpi_columns[0]:
    st.metric("总销售额", format_compact_currency(kpis["sales"]), help=f"精确值：{format_currency(kpis['sales'])}")
with kpi_columns[1]:
    st.metric("总利润", format_compact_currency(kpis["profit"]), help=f"精确值：{format_currency(kpis['profit'])}")
with kpi_columns[2]:
    st.metric("唯一订单", format_integer(kpis["orders"]), help="按 Order ID 去重统计")
with kpi_columns[3]:
    st.metric("整体利润率", format_percent(kpis["profit_margin"]), help="总利润 ÷ 总销售额")


render_section_heading(
    "时间变化",
    "按订单月份汇总；销售额与利润分别使用独立纵轴，避免量级差异造成误读。",
)
st.markdown("#### 月度销售额变化趋势")
st.plotly_chart(create_monthly_sales_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)

st.markdown("#### 月度利润变化趋势")
st.plotly_chart(create_monthly_profit_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)

monthly = aggregate_monthly(filtered_df)
highest_sales_month = monthly.loc[monthly["Sales"].idxmax()]
lowest_profit_month = monthly.loc[monthly["Profit"].idxmin()]
st.info(
    f"当前筛选条件下，销售额最高月份为 {month_label(highest_sales_month['Order Year-Month'])}，"
    f"销售额 {markdown_currency(highest_sales_month['Sales'])}；"
    f"利润最低月份为 {month_label(lowest_profit_month['Order Year-Month'])}，"
    f"利润 {markdown_currency(lowest_profit_month['Profit'])}。"
)


render_section_heading(
    "地区差异",
    "地图以利润填色，销售额保留在悬浮提示中；地区条形图同时呈现销售规模和利润率。",
)
geo_columns = st.columns([3, 2], gap="large")
with geo_columns[0]:
    st.markdown("#### 各州利润分布与销售表现")
    st.plotly_chart(create_state_map(filtered_df), width="stretch", config=PLOTLY_CONFIG)
with geo_columns[1]:
    st.markdown("#### 各地区销售规模与盈利效率")
    st.plotly_chart(create_region_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)


render_section_heading(
    "商品结构",
    "条形长度表示销售额，颜色表示利润；保留当前筛选条件下的全部商品子类别。",
)
st.markdown("#### 商品子类别的销售与盈利结构")
st.plotly_chart(create_subcategory_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)

subcategory = aggregate_subcategory(filtered_df)
sales_leader = subcategory.loc[subcategory["Sales"].idxmax()]
profit_laggard = subcategory.loc[subcategory["Profit"].idxmin()]
negative_subcategories = int(subcategory["Profit"].lt(0).sum())
st.info(
    f"当前筛选条件下，销售额最高的子类别为“{sales_leader['Sub-Category Label']}”，"
    f"销售额 {markdown_currency(sales_leader['Sales'])}；利润最低的子类别为“{profit_laggard['Sub-Category Label']}”，"
    f"利润 {markdown_currency(profit_laggard['Profit'])}；共有 {negative_subcategories} 个子类别汇总利润为负。"
)


render_section_heading(
    "关系分析",
    "每个散点代表一条商品交易明细；折扣图按实际折扣水平汇总。相关关系仅用于描述，不代表因果。",
)
relationship_columns = st.columns([1.12, 1], gap="large")
with relationship_columns[0]:
    st.markdown("#### 交易明细的销售额与利润分布")
    st.plotly_chart(create_sales_profit_scatter(filtered_df), width="stretch", config=PLOTLY_CONFIG)
with relationship_columns[1]:
    st.markdown("#### 折扣水平与盈利表现的观察性关系")
    st.plotly_chart(create_discount_profit_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)

discount = aggregate_discount(filtered_df)
negative_discount_levels = int(discount["Profit Margin"].lt(0).sum())
st.caption(
    f"当前筛选条件下，共有 {negative_discount_levels} 个实际折扣水平的汇总利润率低于 0。"
    "该结果反映观察性关联，商品结构等因素可能同时影响折扣与盈利表现。"
)


with st.expander("辅助分析：地区退货订单率", expanded=False):
    st.caption("退货状态按唯一 Order ID 统计；不能据此判断某一具体商品是否被退货。")
    st.plotly_chart(create_returns_chart(filtered_df), width="stretch", config=PLOTLY_CONFIG)
    st.caption(
        f"当前筛选条件下共有 {format_integer(kpis['returned_orders'])} 个唯一退货订单，"
        f"订单级退货率为 {format_percent(kpis['return_rate'])}。"
    )


with st.expander("数据与口径说明", expanded=False):
    st.markdown(
        """
        - 一行代表一条商品交易明细，不代表一个完整订单。
        - 订单数按 `Order ID` 去重；客户数按 `Customer ID` 去重。
        - 商品销量为 `Quantity` 之和；整体利润率为总利润除以总销售额。
        - 退货订单率按唯一订单统计，不使用退货交易明细行数代替订单数。
        - 图表中的相关关系均为描述性分析，不能直接解释为因果关系。
        """
    )
    st.download_button(
        "下载当前筛选数据（CSV）",
        data=dataframe_to_csv(filtered_df),
        file_name="superstore_filtered.csv",
        mime="text/csv",
        help="导出当前四个全局筛选条件下的商品交易明细。",
    )

st.markdown(
    '<div class="footer-note">Dashboard 数据源：data/processed/superstore_clean.csv　·　'
    f"当前显示 {format_integer(kpis['transaction_rows'])} 条交易明细</div>",
    unsafe_allow_html=True,
)
