"""Streamlit Dashboard 的数据读取、筛选、聚合与格式化工具。"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "superstore_clean.csv"

DISPLAY_NAMES = {
    "Sales": "销售额",
    "Profit": "利润",
    "Discount": "折扣",
    "Order ID": "订单编号",
    "Order Date": "订单日期",
    "Category": "商品类别",
    "Sub-Category": "商品子类别",
    "Region": "地区",
    "State": "州",
    "Segment": "客户类型",
    "Quantity": "商品数量",
    "Returned": "退货状态",
}

REGION_LABELS = {
    "Central": "中部",
    "East": "东部",
    "South": "南部",
    "West": "西部",
}

CATEGORY_LABELS = {
    "Furniture": "家具",
    "Office Supplies": "办公用品",
    "Technology": "技术产品",
}

SEGMENT_LABELS = {
    "Consumer": "消费者",
    "Corporate": "企业",
    "Home Office": "家庭办公",
}

SUBCATEGORY_LABELS = {
    "Accessories": "配件",
    "Appliances": "电器",
    "Art": "美术用品",
    "Binders": "装订用品",
    "Bookcases": "书柜",
    "Chairs": "椅子",
    "Copiers": "复印设备",
    "Envelopes": "信封",
    "Fasteners": "紧固用品",
    "Furnishings": "家居装饰",
    "Labels": "标签",
    "Machines": "机器设备",
    "Paper": "纸张",
    "Phones": "电话设备",
    "Storage": "收纳用品",
    "Supplies": "办公耗材",
    "Tables": "桌子",
}

STATE_ABBREVIATIONS = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

EXPECTED_BASELINE = {
    "rows": 9994,
    "orders": 5009,
    "customers": 793,
    "products": 1862,
    "quantity": 37873,
    "sales": 2297200.8603,
    "profit": 286397.0217,
    "date_min": pd.Timestamp("2016-01-03"),
    "date_max": pd.Timestamp("2019-12-30"),
}


@st.cache_data(show_spinner="正在读取分析数据…")
def load_data(path: Path | None = None) -> pd.DataFrame:
    """只读取阶段 2 生成的清洗数据，并规范 Dashboard 所需数据类型。"""
    source = Path(path) if path is not None else DATA_PATH
    if not source.is_file():
        raise FileNotFoundError(f"未找到 Dashboard 数据文件：{source}")

    df = pd.read_csv(source, dtype={"Postal Code": "string"})
    required_columns = {
        "Row ID",
        "Order ID",
        "Order Date",
        "Ship Date",
        "Customer ID",
        "Product ID",
        "Region",
        "State",
        "Category",
        "Sub-Category",
        "Segment",
        "Sales",
        "Profit",
        "Discount",
        "Quantity",
        "Returned",
        "Order Year",
        "Order Year-Month",
    }
    missing_columns = sorted(required_columns.difference(df.columns))
    if missing_columns:
        raise ValueError(f"清洗数据缺少必要字段：{', '.join(missing_columns)}")

    for column in ("Order Date", "Ship Date", "Order Year-Month"):
        df[column] = pd.to_datetime(df[column], errors="raise")

    for column in ("Sales", "Profit", "Discount", "Quantity", "Row ID", "Order Year"):
        df[column] = pd.to_numeric(df[column], errors="raise")

    df["Row ID"] = df["Row ID"].astype("int64")
    df["Order Year"] = df["Order Year"].astype("int64")
    return df


def validate_source_data(df: pd.DataFrame) -> dict[str, float | int | pd.Timestamp]:
    """验证未筛选数据基线；任何不一致都应阻止 Dashboard 继续运行。"""
    actual = {
        "rows": len(df),
        "orders": df["Order ID"].nunique(),
        "customers": df["Customer ID"].nunique(),
        "products": df["Product ID"].nunique(),
        "quantity": int(df["Quantity"].sum()),
        "sales": float(df["Sales"].sum()),
        "profit": float(df["Profit"].sum()),
        "date_min": df["Order Date"].min(),
        "date_max": df["Order Date"].max(),
    }

    exact_keys = ("rows", "orders", "customers", "products", "quantity", "date_min", "date_max")
    for key in exact_keys:
        if actual[key] != EXPECTED_BASELINE[key]:
            raise ValueError(
                f"数据基线验证失败：{key} 实际为 {actual[key]}，预期为 {EXPECTED_BASELINE[key]}。"
            )
    for key in ("sales", "profit"):
        if not math.isclose(actual[key], EXPECTED_BASELINE[key], rel_tol=0, abs_tol=1e-6):
            raise ValueError(
                f"数据基线验证失败：{key} 实际为 {actual[key]:.10f}，"
                f"预期为 {EXPECTED_BASELINE[key]:.10f}。"
            )

    present_states = set(df.loc[df["State"].notna(), "State"])
    unmapped_states = sorted(present_states - set(STATE_ABBREVIATIONS))
    if unmapped_states:
        warnings.warn(f"发现未映射州名：{', '.join(unmapped_states)}", stacklevel=2)
        raise ValueError(f"州名缩写映射不完整：{', '.join(unmapped_states)}")
    return actual


def apply_filters(
    df: pd.DataFrame,
    years: Sequence[int] | None = None,
    regions: Sequence[str] | None = None,
    categories: Sequence[str] | None = None,
    segments: Sequence[str] | None = None,
) -> pd.DataFrame:
    """集中应用四个全局筛选器；空选择表示保留全部。"""
    mask = pd.Series(True, index=df.index)
    selections: Iterable[tuple[str, Sequence[object] | None]] = (
        ("Order Year", years),
        ("Region", regions),
        ("Category", categories),
        ("Segment", segments),
    )
    for column, selected in selections:
        if selected:
            mask &= df[column].isin(selected)
    return df.loc[mask].copy()


def safe_ratio(numerator: float, denominator: float) -> float | None:
    """安全计算比率，避免 0 分母产生 NaN 或 Infinity。"""
    if denominator == 0 or pd.isna(denominator):
        return None
    value = numerator / denominator
    return float(value) if math.isfinite(value) else None


def calculate_kpis(df: pd.DataFrame) -> dict[str, float | int | None]:
    sales = float(df["Sales"].sum())
    profit = float(df["Profit"].sum())
    orders = int(df["Order ID"].nunique())
    returned_orders = int(df.loc[df["Returned"].eq("Yes"), "Order ID"].nunique())
    return {
        "transaction_rows": int(len(df)),
        "orders": orders,
        "customers": int(df["Customer ID"].nunique()),
        "products": int(df["Product ID"].nunique()),
        "quantity": int(df["Quantity"].sum()),
        "sales": sales,
        "profit": profit,
        "profit_margin": safe_ratio(profit, sales),
        "average_order_sales": safe_ratio(sales, orders),
        "returned_orders": returned_orders,
        "return_rate": safe_ratio(returned_orders, orders),
    }


def _add_margin(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["Profit Margin"] = result.apply(
        lambda row: safe_ratio(float(row["Profit"]), float(row["Sales"])), axis=1
    )
    return result


def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("Order Year-Month", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Order_Count=("Order ID", "nunique"),
            Quantity=("Quantity", "sum"),
        )
        .sort_values("Order Year-Month")
    )
    return _add_margin(grouped)


def aggregate_region(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("Region", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Order_Count=("Order ID", "nunique"),
            Customer_Count=("Customer ID", "nunique"),
        )
        .sort_values("Sales")
    )
    grouped = _add_margin(grouped)
    grouped["Region Label"] = grouped["Region"].map(REGION_LABELS)
    return grouped


def aggregate_state(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("State", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Order_Count=("Order ID", "nunique"),
            Customer_Count=("Customer ID", "nunique"),
        )
        .sort_values("Sales", ascending=False)
    )
    grouped = _add_margin(grouped)
    grouped["State Code"] = grouped["State"].map(STATE_ABBREVIATIONS)
    if grouped["State Code"].isna().any():
        missing = grouped.loc[grouped["State Code"].isna(), "State"].tolist()
        warnings.warn(f"地图存在未映射州名：{', '.join(missing)}", stacklevel=2)
        raise ValueError(f"地图州名映射失败：{', '.join(missing)}")
    return grouped


def aggregate_subcategory(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["Category", "Sub-Category"], as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Quantity=("Quantity", "sum"),
            Order_Count=("Order ID", "nunique"),
        )
        .sort_values("Sales")
    )
    grouped = _add_margin(grouped)
    grouped["Category Label"] = grouped["Category"].map(CATEGORY_LABELS)
    grouped["Sub-Category Label"] = grouped["Sub-Category"].map(SUBCATEGORY_LABELS)
    grouped["Sub-Category Label"] = grouped["Sub-Category Label"].fillna(grouped["Sub-Category"])
    return grouped


def aggregate_discount(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby("Discount", as_index=False)
        .agg(
            Transaction_Count=("Row ID", "count"),
            Order_Count=("Order ID", "nunique"),
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
        )
        .sort_values("Discount")
    )
    return _add_margin(grouped)


def aggregate_returns_by_region(df: pd.DataFrame) -> pd.DataFrame:
    all_orders = df.groupby("Region")["Order ID"].nunique().rename("Order Count")
    returned = (
        df.loc[df["Returned"].eq("Yes")]
        .groupby("Region")["Order ID"]
        .nunique()
        .rename("Returned Order Count")
    )
    grouped = pd.concat([all_orders, returned], axis=1).fillna(0).reset_index()
    grouped["Returned Order Count"] = grouped["Returned Order Count"].astype(int)
    grouped["Return Rate"] = grouped.apply(
        lambda row: safe_ratio(float(row["Returned Order Count"]), float(row["Order Count"])), axis=1
    )
    grouped["Region Label"] = grouped["Region"].map(REGION_LABELS)
    return grouped.sort_values("Return Rate")


def format_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def format_compact_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "-" if value < 0 else ""
    absolute = abs(float(value))
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.2f}K"
    return f"{sign}${absolute:,.2f}"


def format_percent(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}%}"


def format_integer(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value):,}"


def month_label(value: pd.Timestamp) -> str:
    return f"{value.year}年{value.month:02d}月"
