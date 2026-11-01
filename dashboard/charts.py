"""Dashboard 的 Plotly 图表构造函数。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from data_utils import (
    CATEGORY_LABELS,
    SUBCATEGORY_LABELS,
    aggregate_discount,
    aggregate_monthly,
    aggregate_region,
    aggregate_returns_by_region,
    aggregate_state,
    aggregate_subcategory,
)


SALES_COLOR = "#3B5CCC"
SALES_DARK = "#29449C"
PROFIT_POSITIVE = "#2563A6"
PROFIT_NEGATIVE = "#D45A3A"
TEXT_COLOR = "#263142"
MUTED_COLOR = "#667085"
GRID_COLOR = "#E8EBF0"
PLOT_BG = "#FFFFFF"
DIVERGING_SCALE = [
    [0.00, "#B6422E"],
    [0.35, "#E8A58F"],
    [0.50, "#F4F1EC"],
    [0.65, "#9DBCDD"],
    [1.00, "#24568A"],
]
DISCOUNT_SCALE = [
    [0.00, "#E9EEF8"],
    [0.45, "#7794CA"],
    [1.00, "#273E78"],
]

PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
    "modeBarButtonsToRemove": [
        "lasso2d",
        "select2d",
        "autoScale2d",
        "toggleSpikelines",
    ],
    "toImageButtonOptions": {"format": "png", "filename": "superstore_chart", "scale": 2},
}


def _symmetric_limit(values: pd.Series, minimum: float = 0.01) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    clean = numeric.loc[numeric.notna()]
    if clean.empty:
        return minimum
    return max(abs(float(clean.min())), abs(float(clean.max())), minimum)


def _base_layout(fig: go.Figure, height: int, *, show_legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=PLOT_BG,
        plot_bgcolor=PLOT_BG,
        font={"family": "Aptos, Microsoft YaHei, sans-serif", "size": 13, "color": TEXT_COLOR},
        margin={"l": 16, "r": 16, "t": 16, "b": 28},
        hoverlabel={
            "bgcolor": "#172033",
            "bordercolor": "#172033",
            "font": {"family": "Microsoft YaHei, sans-serif", "size": 13, "color": "white"},
        },
        showlegend=show_legend,
        hovermode="closest",
    )
    return fig


def _style_cartesian(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        zeroline=False,
        linecolor="#D8DDE6",
        tickfont={"color": MUTED_COLOR},
        title_font={"color": MUTED_COLOR},
        fixedrange=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        zeroline=False,
        linecolor="#D8DDE6",
        tickfont={"color": MUTED_COLOR},
        title_font={"color": MUTED_COLOR},
        fixedrange=False,
    )
    return fig


def create_monthly_sales_chart(df: pd.DataFrame) -> go.Figure:
    monthly = aggregate_monthly(df)
    custom = np.column_stack([monthly["Order_Count"], monthly["Profit"]])
    fig = go.Figure(
        go.Scatter(
            x=monthly["Order Year-Month"],
            y=monthly["Sales"],
            mode="lines+markers",
            line={"color": SALES_COLOR, "width": 2.6},
            marker={"size": 5.5, "color": SALES_DARK, "line": {"width": 1, "color": "white"}},
            customdata=custom,
            hovertemplate=(
                "<b>%{x|%Y年%m月}</b><br>"
                "销售额：$%{y:,.2f}<br>"
                "唯一订单数：%{customdata[0]:,.0f}<br>"
                "利润：$%{customdata[1]:,.2f}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, 330)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="订单月份", tickformat="%Y-%m", dtick="M6")
    fig.update_yaxes(title_text="销售额", tickprefix="$", separatethousands=True)
    return fig


def create_monthly_profit_chart(df: pd.DataFrame) -> go.Figure:
    monthly = aggregate_monthly(df)
    marker_colors = np.where(monthly["Profit"] >= 0, PROFIT_POSITIVE, PROFIT_NEGATIVE)
    custom = np.column_stack([monthly["Sales"], monthly["Profit Margin"].fillna(np.nan)])
    fig = go.Figure(
        go.Scatter(
            x=monthly["Order Year-Month"],
            y=monthly["Profit"],
            mode="lines+markers",
            line={"color": PROFIT_POSITIVE, "width": 2.4},
            marker={"size": 6, "color": marker_colors, "line": {"width": 1, "color": "white"}},
            customdata=custom,
            hovertemplate=(
                "<b>%{x|%Y年%m月}</b><br>"
                "利润：$%{y:,.2f}<br>"
                "销售额：$%{customdata[0]:,.2f}<br>"
                "利润率：%{customdata[1]:.2%}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_width=1.2, line_dash="dash", line_color="#9AA2B1")
    _base_layout(fig, 320)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="订单月份", tickformat="%Y-%m", dtick="M6")
    fig.update_yaxes(title_text="利润", tickprefix="$", separatethousands=True)
    return fig


def create_region_chart(df: pd.DataFrame) -> go.Figure:
    region = aggregate_region(df)
    color_limit = _symmetric_limit(region["Profit Margin"])
    custom = np.column_stack(
        [
            region["Profit"],
            region["Profit Margin"].fillna(np.nan),
            region["Order_Count"],
            region["Customer_Count"],
        ]
    )
    fig = go.Figure(
        go.Bar(
            x=region["Sales"],
            y=region["Region Label"],
            orientation="h",
            marker={
                "color": region["Profit Margin"],
                "colorscale": DIVERGING_SCALE,
                "cmin": -color_limit,
                "cmax": color_limit,
                "colorbar": {"title": "利润率", "tickformat": ".0%", "thickness": 12},
                "line": {"width": 0},
            },
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "销售额：$%{x:,.2f}<br>"
                "利润：$%{customdata[0]:,.2f}<br>"
                "利润率：%{customdata[1]:.2%}<br>"
                "唯一订单数：%{customdata[2]:,.0f}<br>"
                "客户数：%{customdata[3]:,.0f}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, 410)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="销售额", tickprefix="$", separatethousands=True)
    fig.update_yaxes(title_text="", showgrid=False)
    return fig


def create_state_map(df: pd.DataFrame) -> go.Figure:
    state = aggregate_state(df)
    color_limit = _symmetric_limit(state["Profit"])
    custom = np.column_stack(
        [
            state["State"],
            state["Sales"],
            state["Profit Margin"].fillna(np.nan),
            state["Order_Count"],
            state["Customer_Count"],
        ]
    )
    fig = go.Figure(
        go.Choropleth(
            locations=state["State Code"],
            z=state["Profit"],
            locationmode="USA-states",
            colorscale=DIVERGING_SCALE,
            zmin=-color_limit,
            zmax=color_limit,
            zmid=0,
            marker_line_color="white",
            marker_line_width=0.8,
            colorbar={"title": "利润", "tickprefix": "$", "thickness": 13, "len": 0.72},
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "销售额：$%{customdata[1]:,.2f}<br>"
                "利润：$%{z:,.2f}<br>"
                "利润率：%{customdata[2]:.2%}<br>"
                "唯一订单数：%{customdata[3]:,.0f}<br>"
                "客户数：%{customdata[4]:,.0f}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, 410)
    fig.update_layout(
        geo={
            "scope": "usa",
            "projection": {"type": "albers usa"},
            "showlakes": False,
            "showland": True,
            "landcolor": "#EEF1F5",
            "bgcolor": PLOT_BG,
        },
        margin={"l": 0, "r": 0, "t": 4, "b": 4},
    )
    return fig


def create_subcategory_chart(df: pd.DataFrame) -> go.Figure:
    subcategory = aggregate_subcategory(df)
    color_limit = _symmetric_limit(subcategory["Profit"])
    custom = np.column_stack(
        [
            subcategory["Category Label"],
            subcategory["Sub-Category Label"],
            subcategory["Profit"],
            subcategory["Profit Margin"].fillna(np.nan),
            subcategory["Quantity"],
            subcategory["Order_Count"],
        ]
    )
    fig = go.Figure(
        go.Bar(
            x=subcategory["Sales"],
            y=subcategory["Sub-Category Label"],
            orientation="h",
            marker={
                "color": subcategory["Profit"],
                "colorscale": DIVERGING_SCALE,
                "cmin": -color_limit,
                "cmax": color_limit,
                "colorbar": {"title": "利润", "tickprefix": "$", "thickness": 13, "len": 0.72},
            },
            customdata=custom,
            hovertemplate=(
                "商品类别：%{customdata[0]}<br>"
                "<b>商品子类别：%{customdata[1]}</b><br>"
                "销售额：$%{x:,.2f}<br>"
                "利润：$%{customdata[2]:,.2f}<br>"
                "利润率：%{customdata[3]:.2%}<br>"
                "商品销量：%{customdata[4]:,.0f}<br>"
                "唯一订单数：%{customdata[5]:,.0f}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, max(520, 31 * len(subcategory) + 100))
    _style_cartesian(fig)
    fig.update_xaxes(title_text="销售额", tickprefix="$", separatethousands=True)
    fig.update_yaxes(title_text="", showgrid=False, automargin=True)
    return fig


def create_sales_profit_scatter(df: pd.DataFrame) -> go.Figure:
    category_labels = df["Category"].map(CATEGORY_LABELS).fillna(df["Category"])
    subcategory_labels = df["Sub-Category"].map(SUBCATEGORY_LABELS).fillna(df["Sub-Category"])
    custom = np.column_stack(
        [
            df["Order ID"],
            df["Product Name"],
            category_labels,
            subcategory_labels,
            df["Discount"],
        ]
    )
    fig = go.Figure(
        go.Scattergl(
            x=df["Sales"],
            y=df["Profit"],
            mode="markers",
            marker={
                "size": 6,
                "opacity": 0.52,
                "color": df["Discount"],
                "colorscale": DISCOUNT_SCALE,
                "cmin": 0,
                "cmax": max(float(df["Discount"].max()), 0.01),
                "colorbar": {"title": "折扣", "tickformat": ".0%", "thickness": 12},
                "line": {"width": 0},
            },
            customdata=custom,
            hovertemplate=(
                "订单编号：%{customdata[0]}<br>"
                "商品名称：%{customdata[1]}<br>"
                "商品类别：%{customdata[2]}<br>"
                "商品子类别：%{customdata[3]}<br>"
                "销售额：$%{x:,.2f}<br>"
                "利润：$%{y:,.2f}<br>"
                "折扣：%{customdata[4]:.0%}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_width=1.2, line_dash="dash", line_color="#8C95A5")
    _base_layout(fig, 510)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="交易明细销售额", tickprefix="$", separatethousands=True)
    fig.update_yaxes(title_text="交易明细利润", tickprefix="$", separatethousands=True)
    return fig


def create_discount_profit_chart(df: pd.DataFrame) -> go.Figure:
    discount = aggregate_discount(df)
    color_limit = _symmetric_limit(discount["Profit Margin"])
    counts = discount["Transaction_Count"].astype(float)
    if counts.max() == counts.min():
        marker_size = np.full(len(counts), 11.0)
    else:
        marker_size = 8 + 16 * np.sqrt((counts - counts.min()) / (counts.max() - counts.min()))
    custom = np.column_stack(
        [
            discount["Sales"],
            discount["Profit"],
            discount["Transaction_Count"],
            discount["Order_Count"],
        ]
    )
    fig = go.Figure(
        go.Scatter(
            x=discount["Discount"],
            y=discount["Profit Margin"],
            mode="lines+markers",
            line={"color": "#596579", "width": 2},
            marker={
                "size": marker_size,
                "color": discount["Profit Margin"],
                "colorscale": DIVERGING_SCALE,
                "cmin": -color_limit,
                "cmax": color_limit,
                "line": {"width": 1.2, "color": "white"},
                "colorbar": {"title": "利润率", "tickformat": ".0%", "thickness": 12},
            },
            customdata=custom,
            hovertemplate=(
                "<b>折扣：%{x:.0%}</b><br>"
                "销售额：$%{customdata[0]:,.2f}<br>"
                "利润：$%{customdata[1]:,.2f}<br>"
                "利润率：%{y:.2%}<br>"
                "交易明细数：%{customdata[2]:,.0f}<br>"
                "唯一订单数：%{customdata[3]:,.0f}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_width=1.2, line_dash="dash", line_color="#8C95A5")
    _base_layout(fig, 510)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="折扣水平", tickformat=".0%")
    fig.update_yaxes(title_text="汇总利润率", tickformat=".0%")
    return fig


def create_returns_chart(df: pd.DataFrame) -> go.Figure:
    returns = aggregate_returns_by_region(df)
    custom = np.column_stack([returns["Returned Order Count"], returns["Order Count"]])
    fig = go.Figure(
        go.Bar(
            x=returns["Return Rate"],
            y=returns["Region Label"],
            orientation="h",
            marker={"color": "#7085A8"},
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "退货订单数：%{customdata[0]:,.0f}<br>"
                "唯一订单数：%{customdata[1]:,.0f}<br>"
                "订单级退货率：%{x:.2%}<extra></extra>"
            ),
        )
    )
    _base_layout(fig, 310)
    _style_cartesian(fig)
    fig.update_xaxes(title_text="订单级退货率", tickformat=".0%")
    fig.update_yaxes(title_text="", showgrid=False)
    return fig
