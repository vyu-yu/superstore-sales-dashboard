"""阶段 3：基于清洗数据的探索性数据分析。

只读取 data/processed/superstore_clean.csv，不修改或重新清洗输入数据。
输出统计表、少量诊断图和阶段报告。
"""

from __future__ import annotations

import hashlib
import math
import platform
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "superstore_clean.csv"
TABLE_DIR = PROJECT_ROOT / "output" / "tables"
FIGURE_DIR = PROJECT_ROOT / "output" / "figures"
REPORT_FILE = PROJECT_ROOT / "output" / "阶段3_探索性分析报告.md"

OUTPUT_FILES = {
    "overall": TABLE_DIR / "overall_metrics.csv",
    "yearly": TABLE_DIR / "yearly_analysis.csv",
    "monthly": TABLE_DIR / "monthly_analysis.csv",
    "month_of_year": TABLE_DIR / "month_of_year_analysis.csv",
    "quarter": TABLE_DIR / "quarter_analysis.csv",
    "region": TABLE_DIR / "region_analysis.csv",
    "state": TABLE_DIR / "state_analysis.csv",
    "city": TABLE_DIR / "city_analysis.csv",
    "category": TABLE_DIR / "category_analysis.csv",
    "subcategory": TABLE_DIR / "subcategory_analysis.csv",
    "segment": TABLE_DIR / "segment_analysis.csv",
    "discount": TABLE_DIR / "discount_analysis.csv",
    "correlation": TABLE_DIR / "correlation_analysis.csv",
    "returns": TABLE_DIR / "returns_analysis.csv",
    "category_discount": TABLE_DIR / "category_discount_analysis.csv",
    "findings": TABLE_DIR / "candidate_findings.csv",
}

FIGURE_FILES = {
    "monthly": FIGURE_DIR / "monthly_sales_profit_diagnostic.png",
    "state": FIGURE_DIR / "state_sales_profit_diagnostic.png",
    "subcategory": FIGURE_DIR / "subcategory_sales_profit_diagnostic.png",
    "sales_profit": FIGURE_DIR / "sales_profit_scatter_diagnostic.png",
    "discount_profit": FIGURE_DIR / "discount_profit_diagnostic.png",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")


def safe_ratio(numerator: pd.Series | float, denominator: pd.Series | float) -> Any:
    if isinstance(denominator, pd.Series):
        return numerator.div(denominator.where(denominator != 0))
    return numerator / denominator if denominator != 0 else float("nan")


def grouped_metrics(frame: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    """按统一业务口径生成分组指标。"""
    grouped = (
        frame.groupby(group_columns, dropna=False, observed=True)
        .agg(
            **{
                "Transaction Lines": ("Row ID", "count"),
                "Sales": ("Sales", "sum"),
                "Profit": ("Profit", "sum"),
                "Unique Orders": ("Order ID", "nunique"),
                "Unique Customers": ("Customer ID", "nunique"),
                "Quantity": ("Quantity", "sum"),
            }
        )
        .reset_index()
    )
    grouped["Average Order Sales"] = safe_ratio(grouped["Sales"], grouped["Unique Orders"])
    grouped["Profit Margin"] = safe_ratio(grouped["Profit"], grouped["Sales"])
    return grouped


def pearson_correlation(x: pd.Series, y: pd.Series) -> tuple[int, float]:
    pairs = pd.concat([x, y], axis=1).dropna()
    return len(pairs), float(pairs.iloc[:, 0].corr(pairs.iloc[:, 1], method="pearson"))


def spearman_correlation(x: pd.Series, y: pd.Series) -> tuple[int, float]:
    pairs = pd.concat([x, y], axis=1).dropna()
    ranked_x = pairs.iloc[:, 0].rank(method="average")
    ranked_y = pairs.iloc[:, 1].rank(method="average")
    return len(pairs), float(ranked_x.corr(ranked_y, method="pearson"))


def correlation_rows(
    relationship: str,
    x: pd.Series,
    y: pd.Series,
    scope: str,
    note: str,
) -> list[dict[str, Any]]:
    pearson_n, pearson = pearson_correlation(x, y)
    spearman_n, spearman = spearman_correlation(x, y)
    return [
        {
            "Relationship": relationship,
            "Method": "Pearson",
            "Scope": scope,
            "N": pearson_n,
            "Coefficient": pearson,
            "Note": note,
        },
        {
            "Relationship": relationship,
            "Method": "Spearman",
            "Scope": scope,
            "N": spearman_n,
            "Coefficient": spearman,
            "Note": note,
        },
    ]


def money(value: float) -> str:
    return f"{value:,.2f}"


def percent(value: float) -> str:
    return f"{value:.2%}"


def display_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(frame: pd.DataFrame, max_rows: int | None = None) -> str:
    view = frame if max_rows is None else frame.head(max_rows)
    if view.empty:
        return "（无记录）"
    headers = [str(column) for column in view.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in view.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(display_value(value) for value in row) + " |")
    if max_rows is not None and len(frame) > max_rows:
        lines.append(f"\n仅显示前 {max_rows} 行，共 {len(frame)} 行。")
    return "\n".join(lines)


def finding_row(
    area: str,
    finding: str,
    evidence: str,
    metric_value: str,
    source: str,
    caution: str,
    visualization: str,
) -> dict[str, str]:
    return {
        "Analysis Area": area,
        "Finding": finding,
        "Evidence": evidence,
        "Metric / Value": metric_value,
        "Source Table": source,
        "Caution": caution,
        "Potential Visualization": visualization,
    }


def plot_monthly(monthly: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(monthly["Order Year-Month"], monthly["Sales"], color="#2563EB", linewidth=1.8)
    axes[0].set_title("Monthly Sales (diagnostic)")
    axes[0].set_ylabel("Sales")
    axes[0].grid(alpha=0.25)
    axes[1].plot(monthly["Order Year-Month"], monthly["Profit"], color="#D97706", linewidth=1.8)
    axes[1].axhline(0, color="#444444", linewidth=0.8)
    axes[1].set_title("Monthly Profit (diagnostic)")
    axes[1].set_ylabel("Profit")
    axes[1].grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(FIGURE_FILES["monthly"], dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_states(state: pd.DataFrame) -> None:
    top = state.nlargest(15, "Sales").sort_values("Sales")
    colors = ["#DC2626" if value < 0 else "#2563EB" for value in top["Profit"]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 7))
    axes[0].barh(top["State"], top["Sales"], color=colors)
    axes[0].set_title("Top 15 states by Sales")
    axes[0].set_xlabel("Sales")
    profit_order = state.nsmallest(15, "Profit").sort_values("Profit", ascending=False)
    profit_colors = ["#DC2626" if value < 0 else "#2563EB" for value in profit_order["Profit"]]
    axes[1].barh(profit_order["State"], profit_order["Profit"], color=profit_colors)
    axes[1].axvline(0, color="#444444", linewidth=0.8)
    axes[1].set_title("Bottom 15 states by Profit")
    axes[1].set_xlabel("Profit")
    fig.suptitle("State comparison (diagnostic)")
    fig.tight_layout()
    fig.savefig(FIGURE_FILES["state"], dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_subcategories(subcategory: pd.DataFrame) -> None:
    ordered = subcategory.sort_values("Sales")
    colors = ["#DC2626" if value < 0 else "#2563EB" for value in ordered["Profit"]]
    fig, axes = plt.subplots(1, 2, figsize=(13, 7), sharey=True)
    axes[0].barh(ordered["Sub-Category"], ordered["Sales"], color=colors)
    axes[0].set_title("Sub-category Sales")
    axes[0].set_xlabel("Sales")
    axes[1].barh(ordered["Sub-Category"], ordered["Profit"], color=colors)
    axes[1].axvline(0, color="#444444", linewidth=0.8)
    axes[1].set_title("Sub-category Profit")
    axes[1].set_xlabel("Profit")
    fig.suptitle("Sub-category comparison (diagnostic)")
    fig.tight_layout()
    fig.savefig(FIGURE_FILES["subcategory"], dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_sales_profit(data: pd.DataFrame) -> None:
    sales_low, sales_high = data["Sales"].quantile([0.01, 0.99])
    profit_low, profit_high = data["Profit"].quantile([0.01, 0.99])
    central = data[
        data["Sales"].between(sales_low, sales_high)
        & data["Profit"].between(profit_low, profit_high)
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    axes[0].scatter(data["Sales"], data["Profit"], s=10, alpha=0.25, color="#2563EB")
    axes[0].axhline(0, color="#444444", linewidth=0.8)
    axes[0].set_title("Full data")
    axes[0].set_xlabel("Sales")
    axes[0].set_ylabel("Profit")
    axes[1].scatter(central["Sales"], central["Profit"], s=10, alpha=0.25, color="#0F766E")
    axes[1].axhline(0, color="#444444", linewidth=0.8)
    axes[1].set_title("Middle 98% view only; statistics use full data")
    axes[1].set_xlabel("Sales")
    axes[1].set_ylabel("Profit")
    fig.suptitle("Sales vs Profit (diagnostic)")
    fig.tight_layout()
    fig.savefig(FIGURE_FILES["sales_profit"], dpi=160, bbox_inches="tight")
    plt.close(fig)


def plot_discount_profit(data: pd.DataFrame, discount: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    axes[0].scatter(data["Discount"], data["Profit"], s=10, alpha=0.2, color="#7C3AED")
    axes[0].axhline(0, color="#444444", linewidth=0.8)
    axes[0].set_title("Transaction-level Discount vs Profit")
    axes[0].set_xlabel("Discount")
    axes[0].set_ylabel("Profit")
    axes[1].plot(discount["Discount"], discount["Profit Margin"], marker="o", color="#D97706")
    axes[1].axhline(0, color="#444444", linewidth=0.8)
    axes[1].set_title("Aggregated profit margin by exact discount")
    axes[1].set_xlabel("Discount")
    axes[1].set_ylabel("Profit Margin")
    fig.suptitle("Discount and Profit (diagnostic, observational)")
    fig.tight_layout()
    fig.savefig(FIGURE_FILES["discount_profit"], dpi=160, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(f"未找到阶段 2 清洗数据：{INPUT_FILE}")
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    before_hash = file_sha256(INPUT_FILE)

    dtype_map = {
        "Order ID": "string",
        "Customer ID": "string",
        "Product ID": "string",
        "Postal Code": "string",
        "Returned": "string",
        "Order Quarter": "string",
    }
    data = pd.read_csv(
        INPUT_FILE,
        encoding="utf-8-sig",
        dtype=dtype_map,
        parse_dates=["Order Date", "Ship Date", "Order Year-Month"],
    )

    required_columns = {
        "Row ID", "Order ID", "Order Date", "Region", "State", "City", "Category",
        "Sub-Category", "Segment", "Customer ID", "Product ID", "Sales", "Profit",
        "Quantity", "Discount", "Returned", "Order Year", "Order Quarter", "Order Month",
        "Order Year-Month",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(f"清洗数据缺少阶段 3 必需字段：{sorted(missing_columns)}")

    integrity = {
        "rows": len(data),
        "orders": data["Order ID"].nunique(),
        "customers": data["Customer ID"].nunique(),
        "products": data["Product ID"].nunique(),
    }
    expected_integrity = {"rows": 9994, "orders": 5009, "customers": 793, "products": 1862}
    if integrity != expected_integrity:
        raise ValueError(f"阶段 2 规模核对失败：实际 {integrity}，预期 {expected_integrity}")
    if data["Row ID"].nunique() != len(data):
        raise ValueError("Row ID 不是唯一交易明细键。")
    if data[["Order Date", "Sales", "Profit", "Quantity", "Discount"]].isna().any().any():
        raise ValueError("核心分析字段存在缺失值，停止 EDA。")
    if not (data["Order Year"] == data["Order Date"].dt.year).all():
        raise ValueError("Order Year 与 Order Date 不一致。")
    if not (data["Order Month"] == data["Order Date"].dt.month).all():
        raise ValueError("Order Month 与 Order Date 不一致。")
    expected_month_start = data["Order Date"].dt.to_period("M").dt.to_timestamp()
    if not (data["Order Year-Month"] == expected_month_start).all():
        raise ValueError("Order Year-Month 与 Order Date 不一致。")

    sales_total = float(data["Sales"].sum())
    profit_total = float(data["Profit"].sum())
    order_date_min = data["Order Date"].min()
    order_date_max = data["Order Date"].max()
    if not math.isclose(sales_total, 2297200.8603, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"Sales 总额与阶段 2 审核结果不一致：{sales_total}")
    if not math.isclose(profit_total, 286397.0217, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"Profit 总额与阶段 2 审核结果不一致：{profit_total}")
    if order_date_min != pd.Timestamp("2016-01-03") or order_date_max != pd.Timestamp("2019-12-30"):
        raise ValueError(f"Order Date 范围与阶段 2 审核结果不一致：{order_date_min} 至 {order_date_max}")

    # 整体经营指标。
    unique_returned_orders = data.loc[data["Returned"] == "Yes", "Order ID"].nunique()
    loss_line_count = int((data["Profit"] < 0).sum())
    overall = pd.DataFrame(
        [
            {
                "Transaction Lines": len(data),
                "Total Sales": sales_total,
                "Total Profit": profit_total,
                "Unique Orders": data["Order ID"].nunique(),
                "Unique Customers": data["Customer ID"].nunique(),
                "Unique Products": data["Product ID"].nunique(),
                "Quantity": int(data["Quantity"].sum()),
                "Average Order Sales": sales_total / data["Order ID"].nunique(),
                "Overall Profit Margin": profit_total / sales_total,
                "Loss Transaction Lines": loss_line_count,
                "Loss Transaction Line Rate": loss_line_count / len(data),
                "Unique Returned Orders": unique_returned_orders,
                "Returned Order Rate": unique_returned_orders / data["Order ID"].nunique(),
            }
        ]
    )

    yearly = grouped_metrics(data, ["Order Year"]).sort_values("Order Year")
    yearly["Sales YoY"] = yearly["Sales"].pct_change()
    yearly["Profit YoY"] = yearly["Profit"].pct_change()

    monthly_observed = grouped_metrics(data, ["Order Year-Month"])
    complete_months = pd.DataFrame(
        {"Order Year-Month": pd.date_range(order_date_min.to_period("M").start_time, order_date_max.to_period("M").start_time, freq="MS")}
    )
    monthly = complete_months.merge(monthly_observed, on="Order Year-Month", how="left")
    monthly["Has Data"] = monthly["Transaction Lines"].notna()
    count_columns = ["Transaction Lines", "Unique Orders", "Unique Customers", "Quantity"]
    value_columns = ["Sales", "Profit"]
    monthly[count_columns + value_columns] = monthly[count_columns + value_columns].fillna(0)
    monthly["Average Order Sales"] = safe_ratio(monthly["Sales"], monthly["Unique Orders"])
    monthly["Profit Margin"] = safe_ratio(monthly["Profit"], monthly["Sales"])

    month_of_year = grouped_metrics(data, ["Order Month"]).sort_values("Order Month")
    annual_month = grouped_metrics(data, ["Order Year", "Order Month"])
    year_counts = annual_month.groupby("Order Month")["Order Year"].nunique()
    average_annual = annual_month.groupby("Order Month")[["Sales", "Profit"]].mean()
    sales_top3 = (
        annual_month.assign(
            _rank=annual_month.groupby("Order Year")["Sales"].rank(method="min", ascending=False)
        )
        .groupby("Order Month")["_rank"]
        .apply(lambda series: int((series <= 3).sum()))
    )
    profit_positive = annual_month.groupby("Order Month")["Profit"].apply(lambda series: int((series > 0).sum()))
    month_of_year["Years Covered"] = month_of_year["Order Month"].map(year_counts)
    month_of_year["Average Annual Sales"] = month_of_year["Order Month"].map(average_annual["Sales"])
    month_of_year["Average Annual Profit"] = month_of_year["Order Month"].map(average_annual["Profit"])
    month_of_year["Sales Top-3 Year Count"] = month_of_year["Order Month"].map(sales_top3)
    month_of_year["Profit Positive Year Count"] = month_of_year["Order Month"].map(profit_positive)

    quarter_all = grouped_metrics(data, ["Order Quarter"])
    quarter_all.insert(0, "Analysis Level", "All Years by Quarter")
    quarter_all.insert(1, "Order Year", pd.Series([pd.NA] * len(quarter_all), dtype="Int64"))
    quarter_all["Years Covered"] = data["Order Year"].nunique()
    quarter_year = grouped_metrics(data, ["Order Year", "Order Quarter"])
    quarter_year.insert(0, "Analysis Level", "Year-Quarter")
    quarter_year["Years Covered"] = 1
    quarter = pd.concat([quarter_all, quarter_year], ignore_index=True, sort=False)
    quarter["Quarter Number"] = quarter["Order Quarter"].str.extract(r"(\d)").astype(int)
    quarter = quarter.sort_values(["Analysis Level", "Order Year", "Quarter Number"], na_position="first")

    region = grouped_metrics(data, ["Region"]).sort_values("Sales", ascending=False)
    region["Sales Rank"] = region["Sales"].rank(method="min", ascending=False).astype(int)
    region["Profit Rank"] = region["Profit"].rank(method="min", ascending=False).astype(int)

    state = grouped_metrics(data, ["State"]).sort_values("Sales", ascending=False)
    state["Sales Rank"] = state["Sales"].rank(method="min", ascending=False).astype(int)
    state["Profit Rank"] = state["Profit"].rank(method="min", ascending=False).astype(int)
    state["Rank Difference (Profit-Sales)"] = state["Profit Rank"] - state["Sales Rank"]

    city = grouped_metrics(data, ["City", "State"]).sort_values("Sales", ascending=False)
    city["Sales Rank"] = city["Sales"].rank(method="min", ascending=False).astype(int)
    city["Profit Rank"] = city["Profit"].rank(method="min", ascending=False).astype(int)

    category = grouped_metrics(data, ["Category"]).sort_values("Sales", ascending=False)
    category["Sales Rank"] = category["Sales"].rank(method="min", ascending=False).astype(int)
    category["Profit Rank"] = category["Profit"].rank(method="min", ascending=False).astype(int)

    subcategory = grouped_metrics(data, ["Sub-Category"]).sort_values("Sales", ascending=False)
    subcategory["Sales Rank"] = subcategory["Sales"].rank(method="min", ascending=False).astype(int)
    subcategory["Profit Rank"] = subcategory["Profit"].rank(method="min", ascending=False).astype(int)
    subcategory["Rank Difference (Profit-Sales)"] = subcategory["Profit Rank"] - subcategory["Sales Rank"]

    segment = grouped_metrics(data, ["Segment"]).sort_values("Sales", ascending=False)
    segment["Sales Rank"] = segment["Sales"].rank(method="min", ascending=False).astype(int)
    segment["Profit Rank"] = segment["Profit"].rank(method="min", ascending=False).astype(int)

    discount = grouped_metrics(data, ["Discount"]).sort_values("Discount")
    category_discount = grouped_metrics(data, ["Category", "Discount"]).sort_values(["Category", "Discount"])

    # 相关性全部基于完整数据；中间 98% 仅做极端值敏感性检查。
    correlation_records: list[dict[str, Any]] = []
    correlation_records += correlation_rows(
        "Sales vs Profit", data["Sales"], data["Profit"], "All transaction lines", "观察性相关，不代表因果。"
    )
    sales_bounds = data["Sales"].quantile([0.01, 0.99])
    profit_bounds = data["Profit"].quantile([0.01, 0.99])
    central = data[
        data["Sales"].between(sales_bounds.iloc[0], sales_bounds.iloc[1])
        & data["Profit"].between(profit_bounds.iloc[0], profit_bounds.iloc[1])
    ]
    correlation_records += correlation_rows(
        "Sales vs Profit",
        central["Sales"],
        central["Profit"],
        "Middle 98% sensitivity subset",
        "仅用于检查极端记录影响，不替代完整数据统计。",
    )
    correlation_records += correlation_rows(
        "Discount vs Profit", data["Discount"], data["Profit"], "All transaction lines", "观察性相关；商品结构可能同时影响折扣和利润。"
    )
    correlation_records += correlation_rows(
        "Discount vs Sales", data["Discount"], data["Sales"], "All transaction lines", "观察性相关；不解释因果。"
    )
    correlation_records += correlation_rows(
        "Monthly Sales vs Monthly Profit",
        monthly["Sales"],
        monthly["Profit"],
        "48 monthly aggregates",
        "用于描述月度同步程度，不解释原因。",
    )
    for category_name, category_frame in data.groupby("Category", observed=True):
        correlation_records += correlation_rows(
            "Discount vs Profit",
            category_frame["Discount"],
            category_frame["Profit"],
            f"Category={category_name}",
            "分类内观察性相关，用于检查商品结构差异。",
        )
    correlation = pd.DataFrame(correlation_records)

    # Returned 是订单级标记，先聚合为唯一订单后再比较。
    if data.groupby("Order ID")["Returned"].nunique().max() != 1:
        raise ValueError("同一 Order ID 出现多个 Returned 状态。")
    for column in ["Region", "Segment"]:
        if data.groupby("Order ID")[column].nunique().max() != 1:
            raise ValueError(f"同一 Order ID 出现多个 {column}，无法进行订单级退货比较。")
    order_level = (
        data.groupby("Order ID", observed=True)
        .agg(
            Returned=("Returned", "first"),
            Region=("Region", "first"),
            Segment=("Segment", "first"),
            Order_Sales=("Sales", "sum"),
            Order_Profit=("Profit", "sum"),
        )
        .reset_index()
    )

    def return_summary(frame: pd.DataFrame, level: str, value: str) -> dict[str, Any]:
        returned_orders = int((frame["Returned"] == "Yes").sum())
        return {
            "Analysis Level": level,
            "Group": value,
            "Total Orders": len(frame),
            "Returned Orders": returned_orders,
            "Non-returned Orders": len(frame) - returned_orders,
            "Returned Order Rate": returned_orders / len(frame) if len(frame) else float("nan"),
        }

    returns_records = [return_summary(order_level, "Overall", "All")]
    for dimension in ["Region", "Segment"]:
        for value, frame in order_level.groupby(dimension, observed=True):
            returns_records.append(return_summary(frame, dimension, str(value)))
    returns_analysis = pd.DataFrame(returns_records)

    # 候选发现只记录有明确数字证据的内容。
    findings: list[dict[str, str]] = []
    findings.append(
        finding_row(
            "Overall",
            "整体销售为正且保持盈利，但亏损交易明细并不少见。",
            f"总销售额 {money(sales_total)}，总利润 {money(profit_total)}；亏损明细 {loss_line_count:,} 条。",
            f"利润率 {percent(profit_total / sales_total)}；亏损明细占比 {percent(loss_line_count / len(data))}",
            "overall_metrics.csv",
            "亏损明细占比是商品明细层级，不等于亏损订单占比。",
            "KPI / 利润结构说明",
        )
    )

    latest_year = yearly.iloc[-1]
    findings.append(
        finding_row(
            "Yearly Trend",
            f"{int(latest_year['Order Year'])} 年销售和利润均增长，但利润增速低于销售增速。",
            f"Sales 同比 {percent(latest_year['Sales YoY'])}，Profit 同比 {percent(latest_year['Profit YoY'])}，利润率 {percent(latest_year['Profit Margin'])}。",
            f"Sales {money(latest_year['Sales'])}；Profit {money(latest_year['Profit'])}",
            "yearly_analysis.csv",
            "同比只描述变化，不能直接解释增长原因。",
            "年度销售与利润组合趋势",
        )
    )
    divergence_years = yearly.dropna(subset=["Sales YoY", "Profit YoY"])
    divergence_years = divergence_years[
        (divergence_years["Sales YoY"] * divergence_years["Profit YoY"] < 0)
    ]
    if not divergence_years.empty:
        row = divergence_years.iloc[0]
        findings.append(
            finding_row(
                "Yearly Trend",
                f"{int(row['Order Year'])} 年销售与利润同比方向不同。",
                f"Sales 同比 {percent(row['Sales YoY'])}，Profit 同比 {percent(row['Profit YoY'])}。",
                f"利润率 {percent(row['Profit Margin'])}",
                "yearly_analysis.csv",
                "方向不同不说明具体原因，需要结合品类、地区和折扣结构分析。",
                "年度销售与利润对比",
            )
        )

    top_month = monthly.loc[monthly["Sales"].idxmax()]
    low_sales_month = monthly.loc[monthly["Sales"].idxmin()]
    low_profit_month = monthly.loc[monthly["Profit"].idxmin()]
    negative_profit_month_count = int((monthly["Profit"] < 0).sum())
    high_sales_threshold = monthly["Sales"].quantile(0.75)
    high_sales_months = monthly[monthly["Sales"] >= high_sales_threshold]
    weakest_high_sales_month = high_sales_months.loc[high_sales_months["Profit Margin"].idxmin()]
    findings.append(
        finding_row(
            "Monthly Trend",
            "最高销售月份与高销售月份中的最低利润率月份并不相同。",
            f"最高销售月份为 {top_month['Order Year-Month']:%Y-%m}，Sales {money(top_month['Sales'])}；高销售月份中利润率最低的是 {weakest_high_sales_month['Order Year-Month']:%Y-%m}，利润率 {percent(weakest_high_sales_month['Profit Margin'])}。",
            f"后者 Sales {money(weakest_high_sales_month['Sales'])}，Profit {money(weakest_high_sales_month['Profit'])}",
            "monthly_analysis.csv",
            "单月差异不能直接解释为稳定季节规律或因果影响。",
            "月度 Sales 与 Profit 双趋势",
        )
    )
    recurring_month = month_of_year.sort_values(
        ["Sales Top-3 Year Count", "Average Annual Sales"], ascending=False
    ).iloc[0]
    if recurring_month["Sales Top-3 Year Count"] >= 3:
        findings.append(
            finding_row(
                "Month of Year",
                f"{int(recurring_month['Order Month'])} 月在多个年份中反复进入销售额前三。",
                f"4 个年份中有 {int(recurring_month['Sales Top-3 Year Count'])} 年进入月销售前三，平均年度 Sales {money(recurring_month['Average Annual Sales'])}。",
                f"汇总利润率 {percent(recurring_month['Profit Margin'])}",
                "month_of_year_analysis.csv",
                "仅有 4 年数据，可视为季节性线索，不能确认长期稳定季节规律。",
                "按自然月的跨年对比",
            )
        )

    strongest_region = region.loc[region["Profit"].idxmax()]
    lowest_margin_region = region.loc[region["Profit Margin"].idxmin()]
    findings.append(
        finding_row(
            "Region",
            f"{strongest_region['Region']} 的利润最高；{lowest_margin_region['Region']} 的利润率最低。",
            f"{strongest_region['Region']} Sales {money(strongest_region['Sales'])}、Profit {money(strongest_region['Profit'])}、利润率 {percent(strongest_region['Profit Margin'])}；{lowest_margin_region['Region']} Sales {money(lowest_margin_region['Sales'])}、Profit {money(lowest_margin_region['Profit'])}、利润率 {percent(lowest_margin_region['Profit Margin'])}。",
            f"利润率差 {percent(strongest_region['Profit Margin'] - lowest_margin_region['Profit Margin'])}",
            "region_analysis.csv",
            "地区汇总差异不说明差异由地区本身造成。",
            "地区 Sales / Profit / 利润率对比",
        )
    )

    negative_states = state[state["Profit"] < 0]
    if not negative_states.empty:
        high_sales_negative_state = negative_states.nlargest(1, "Sales").iloc[0]
        findings.append(
            finding_row(
                "State",
                f"{high_sales_negative_state['State']} 在较高销售规模下仍为负利润。",
                f"Sales {money(high_sales_negative_state['Sales'])}（排名 {int(high_sales_negative_state['Sales Rank'])}），Profit {money(high_sales_negative_state['Profit'])}（排名 {int(high_sales_negative_state['Profit Rank'])}），利润率 {percent(high_sales_negative_state['Profit Margin'])}。",
                f"负利润州共 {len(negative_states)} 个",
                "state_analysis.csv",
                "州级汇总未控制品类、折扣和客户结构。",
                "州级地图 / Sales-Profit 排名对比",
            )
        )

    lowest_category_margin = category.loc[category["Profit Margin"].idxmin()]
    findings.append(
        finding_row(
            "Category",
            f"{lowest_category_margin['Category']} 的销售规模不低，但利润率明显最低。",
            f"Sales {money(lowest_category_margin['Sales'])}，Profit {money(lowest_category_margin['Profit'])}，利润率 {percent(lowest_category_margin['Profit Margin'])}；Sales 排名 {int(lowest_category_margin['Sales Rank'])}，Profit 排名 {int(lowest_category_margin['Profit Rank'])}。",
            f"利润率 {percent(lowest_category_margin['Profit Margin'])}",
            "category_analysis.csv",
            "品类汇总不能说明具体子类别或折扣是唯一原因。",
            "Category Sales-Profit 对比",
        )
    )

    negative_subcategories = subcategory[subcategory["Profit"] < 0]
    if not negative_subcategories.empty:
        negative_sub = negative_subcategories.nlargest(1, "Sales").iloc[0]
        findings.append(
            finding_row(
                "Sub-Category",
                f"{negative_sub['Sub-Category']} 的销售额较高但汇总利润为负。",
                f"Sales {money(negative_sub['Sales'])}（排名 {int(negative_sub['Sales Rank'])}），Profit {money(negative_sub['Profit'])}（排名 {int(negative_sub['Profit Rank'])}），利润率 {percent(negative_sub['Profit Margin'])}。",
                f"负利润子类别共 {len(negative_subcategories)} 个",
                "subcategory_analysis.csv",
                "描述性汇总未解释亏损原因，也不构成停售建议。",
                "子类别 Sales-Profit 横向对比",
            )
        )
    best_sub_margin = subcategory.loc[subcategory["Profit Margin"].idxmax()]
    findings.append(
        finding_row(
            "Sub-Category",
            f"{best_sub_margin['Sub-Category']} 的汇总利润率最高。",
            f"Sales {money(best_sub_margin['Sales'])}，Profit {money(best_sub_margin['Profit'])}，利润率 {percent(best_sub_margin['Profit Margin'])}。",
            f"Sales 排名 {int(best_sub_margin['Sales Rank'])}；Profit 排名 {int(best_sub_margin['Profit Rank'])}",
            "subcategory_analysis.csv",
            "高历史利润率不保证未来表现。",
            "子类别利润率排名",
        )
    )

    segment_margin_range = segment["Profit Margin"].max() - segment["Profit Margin"].min()
    findings.append(
        finding_row(
            "Segment",
            "三个客户 Segment 均为正利润，利润率存在差异但信息维度较少。",
            "; ".join(
                f"{row['Segment']} {percent(row['Profit Margin'])}" for _, row in segment.iterrows()
            ),
            f"利润率极差 {percent(segment_margin_range)}",
            "segment_analysis.csv",
            "只有三个类别，更适合作为筛选器或辅助拆分，是否进入核心视图需结合版面。",
            "筛选器 / 辅助分组条形图",
        )
    )

    full_sales_profit_pearson = correlation.query(
        "Relationship == 'Sales vs Profit' and Method == 'Pearson' and Scope == 'All transaction lines'"
    ).iloc[0]
    full_sales_profit_spearman = correlation.query(
        "Relationship == 'Sales vs Profit' and Method == 'Spearman' and Scope == 'All transaction lines'"
    ).iloc[0]
    central_sales_profit_pearson = correlation.query(
        "Relationship == 'Sales vs Profit' and Method == 'Pearson' and Scope == 'Middle 98% sensitivity subset'"
    ).iloc[0]
    findings.append(
        finding_row(
            "Sales × Profit",
            "交易明细层面的 Sales 与 Profit 呈正相关，但极端记录会影响线性相关强度。",
            f"完整数据 Pearson {full_sales_profit_pearson['Coefficient']:.3f}、Spearman {full_sales_profit_spearman['Coefficient']:.3f}；中间 98% 敏感性子集 Pearson {central_sales_profit_pearson['Coefficient']:.3f}。",
            f"完整 N={int(full_sales_profit_pearson['N'])}；敏感性 N={int(central_sales_profit_pearson['N'])}",
            "correlation_analysis.csv",
            "相关不等于因果；敏感性子集没有替代完整数据统计。",
            "Sales × Profit 散点图",
        )
    )

    discount_profit_pearson = correlation.query(
        "Relationship == 'Discount vs Profit' and Method == 'Pearson' and Scope == 'All transaction lines'"
    ).iloc[0]
    discount_profit_spearman = correlation.query(
        "Relationship == 'Discount vs Profit' and Method == 'Spearman' and Scope == 'All transaction lines'"
    ).iloc[0]
    negative_discount_levels = discount[discount["Profit"] < 0]
    findings.append(
        finding_row(
            "Discount × Profit",
            "Discount 与 Profit 呈负相关，且部分实际折扣水平的汇总利润为负。",
            f"Pearson {discount_profit_pearson['Coefficient']:.3f}，Spearman {discount_profit_spearman['Coefficient']:.3f}；负利润折扣水平 {len(negative_discount_levels)} 个。",
            "; ".join(
                f"{row['Discount']:.0%}: Profit {money(row['Profit'])}, margin {percent(row['Profit Margin'])}, n={int(row['Transaction Lines'])}"
                for _, row in negative_discount_levels.iterrows()
            ),
            "discount_analysis.csv",
            "这是观察性关联，Category 和 Sub-Category 等结构变量可能同时影响折扣与利润。",
            "折扣取值汇总 / Discount × Profit 散点",
        )
    )

    overall_return_row = returns_analysis.query("`Analysis Level` == 'Overall'").iloc[0]
    grouped_return_rows = returns_analysis[returns_analysis["Analysis Level"].isin(["Region", "Segment"])]
    return_rate_range = grouped_return_rows["Returned Order Rate"].max() - grouped_return_rows["Returned Order Rate"].min()
    west_return_row = returns_analysis.query("`Analysis Level` == 'Region' and Group == 'West'").iloc[0]
    other_region_returns = returns_analysis.query("`Analysis Level` == 'Region' and Group != 'West'")
    findings.append(
        finding_row(
            "Returns",
            "West 的订单级退货率明显高于其他 Region，但当前数据只支持订单级比较。",
            f"整体唯一退货订单 {int(overall_return_row['Returned Orders'])} / {int(overall_return_row['Total Orders'])}，退货率 {percent(overall_return_row['Returned Order Rate'])}；West 为 {percent(west_return_row['Returned Order Rate'])}，其他 Region 为 {percent(other_region_returns['Returned Order Rate'].min())}–{percent(other_region_returns['Returned Order Rate'].max())}。",
            f"West 退货订单率 {percent(west_return_row['Returned Order Rate'])}；Region/Segment 分组率极差 {percent(return_rate_range)}",
            "returns_analysis.csv",
            "不能把 Returned=Yes 的商品明细视为具体商品被退货，也没有退货原因字段。",
            "辅助 KPI / Region 或 Segment 订单级对比",
        )
    )
    candidate_findings = pd.DataFrame(findings)

    outputs = {
        "overall": overall,
        "yearly": yearly,
        "monthly": monthly,
        "month_of_year": month_of_year,
        "quarter": quarter,
        "region": region,
        "state": state,
        "city": city,
        "category": category,
        "subcategory": subcategory,
        "segment": segment,
        "discount": discount,
        "correlation": correlation,
        "returns": returns_analysis,
        "category_discount": category_discount,
        "findings": candidate_findings,
    }
    for name, frame in outputs.items():
        save_csv(frame, OUTPUT_FILES[name])

    plot_monthly(monthly)
    plot_states(state)
    plot_subcategories(subcategory)
    plot_sales_profit(data)
    plot_discount_profit(data, discount)

    monthly_corr = correlation.query(
        "Relationship == 'Monthly Sales vs Monthly Profit' and Method == 'Pearson'"
    ).iloc[0]["Coefficient"]
    discount_sales_pearson = correlation.query(
        "Relationship == 'Discount vs Sales' and Method == 'Pearson' and Scope == 'All transaction lines'"
    ).iloc[0]
    discount_sales_spearman = correlation.query(
        "Relationship == 'Discount vs Sales' and Method == 'Spearman' and Scope == 'All transaction lines'"
    ).iloc[0]
    category_discount_spearman = correlation[
        (correlation["Relationship"] == "Discount vs Profit")
        & (correlation["Method"] == "Spearman")
        & correlation["Scope"].str.startswith("Category=")
    ]
    highest_sales_year = yearly.loc[yearly["Sales"].idxmax()]
    highest_profit_year = yearly.loc[yearly["Profit"].idxmax()]
    quarter_all_view = quarter[quarter["Analysis Level"] == "All Years by Quarter"]
    top_sales_quarter = quarter_all_view.loc[quarter_all_view["Sales"].idxmax()]
    top_profit_quarter = quarter_all_view.loc[quarter_all_view["Profit"].idxmax()]
    top_state_sales = state.nlargest(5, "Sales")[["State", "Sales", "Profit", "Profit Margin", "Sales Rank", "Profit Rank"]]
    bottom_state_profit = state.nsmallest(5, "Profit")[["State", "Sales", "Profit", "Profit Margin", "Sales Rank", "Profit Rank"]]
    top_city_sales = city.nlargest(1, "Sales").iloc[0]
    lowest_city_profit = city.nsmallest(1, "Profit").iloc[0]
    top_sub_sales = subcategory.nlargest(8, "Sales")[["Sub-Category", "Sales", "Profit", "Profit Margin", "Sales Rank", "Profit Rank"]]
    segment_report = segment[["Segment", "Sales", "Profit", "Unique Orders", "Unique Customers", "Average Order Sales", "Profit Margin"]]

    report = [
        "# 阶段 3：探索性数据分析",
        "",
        "## 1. 输入验证与统计口径",
        "",
        f"- 输入文件：`{INPUT_FILE.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- 输入文件 SHA-256：`{before_hash}`",
        f"- Python：{platform.python_version()}，pandas：{pd.__version__}，Matplotlib：{matplotlib.__version__}",
        f"- 交易明细数：{len(data):,}；唯一订单数：{data['Order ID'].nunique():,}；唯一客户数：{data['Customer ID'].nunique():,}；唯一产品数：{data['Product ID'].nunique():,}。",
        f"- Sales 总额：{money(sales_total)}；Profit 总额：{money(profit_total)}；日期范围：{order_date_min:%Y-%m-%d} 至 {order_date_max:%Y-%m-%d}。",
        "- 订单数全部使用 `COUNTD(Order ID)`；整体利润率使用 `SUM(Profit) / SUM(Sales)`；平均订单销售额使用 `SUM(Sales) / COUNTD(Order ID)`。",
        "",
        "## 2. 整体经营表现",
        "",
        "### 【观察到的现象】",
        "整体保持盈利，但负利润交易明细占比不可忽略。",
        "",
        "### 【数据证据】",
        f"Sales {money(sales_total)}，Profit {money(profit_total)}，整体利润率 {percent(profit_total / sales_total)}；平均订单销售额 {money(sales_total / data['Order ID'].nunique())}；亏损明细 {loss_line_count:,} 条，占 {percent(loss_line_count / len(data))}。",
        "",
        "### 【可以说明什么】",
        "可以描述总体经营规模、汇总盈利能力以及明细层面的亏损分布。",
        "",
        "### 【不能说明什么】",
        "亏损明细数不等于亏损订单数，也不能单独解释亏损原因。",
        "",
        "## 3. 时间变化",
        "",
        "### 【观察到的现象】",
        f"销售最高年份为 {int(highest_sales_year['Order Year'])} 年，利润最高年份为 {int(highest_profit_year['Order Year'])} 年。完整月份数为 {len(monthly)}，缺月数为 {int((~monthly['Has Data']).sum())}。月度 Sales 与 Profit 的 Pearson 相关为 {monthly_corr:.3f}，并非完全同步。",
        "",
        "### 【数据证据】",
        markdown_table(yearly[["Order Year", "Sales", "Profit", "Unique Orders", "Quantity", "Unique Customers", "Average Order Sales", "Profit Margin", "Sales YoY", "Profit YoY"]]),
        "",
        f"最高销售月份为 {top_month['Order Year-Month']:%Y-%m}，Sales {money(top_month['Sales'])}、Profit {money(top_month['Profit'])}。最低销售月份为 {low_sales_month['Order Year-Month']:%Y-%m}，Sales {money(low_sales_month['Sales'])}；最低利润月份为 {low_profit_month['Order Year-Month']:%Y-%m}，Profit {money(low_profit_month['Profit'])}，共有 {negative_profit_month_count} 个月汇总利润为负。",
        "",
        f"高销售月份中利润率最低的是 {weakest_high_sales_month['Order Year-Month']:%Y-%m}，Sales {money(weakest_high_sales_month['Sales'])}、Profit {money(weakest_high_sales_month['Profit'])}、利润率 {percent(weakest_high_sales_month['Profit Margin'])}。跨年季度汇总中，Sales 最高为 {top_sales_quarter['Order Quarter']}（{money(top_sales_quarter['Sales'])}），Profit 最高为 {top_profit_quarter['Order Quarter']}（{money(top_profit_quarter['Profit'])}）。9、11、12 月均在 4 个年份中进入月销售额前三。",
        "",
        "### 【可以说明什么】",
        "可以描述年度和月度变化、同比方向以及销售和利润不同步的月份。跨年月份统计可提供季节性线索。",
        "",
        "### 【不能说明什么】",
        "不能仅凭最高月份或 4 年数据确认长期稳定季节规律，也不能把同比变化归因于单一变量。",
        "",
        "## 4. 地区差异",
        "",
        "### 【观察到的现象】",
        f"Region 的销售、利润和利润率排名并不完全一致；共有 {len(negative_states)} 个 State 汇总利润为负。City 数量为 {len(city)}，更适合作为地图下钻或 Tooltip。",
        "",
        "### 【数据证据】",
        markdown_table(region[["Region", "Sales", "Profit", "Unique Orders", "Unique Customers", "Quantity", "Average Order Sales", "Profit Margin", "Sales Rank", "Profit Rank"]]),
        "",
        "Sales 最高的 State（前 5）：",
        "",
        markdown_table(top_state_sales),
        "",
        "Profit 最低的 State（后 5）：",
        "",
        markdown_table(bottom_state_profit),
        "",
        f"按 City + State 汇总后共有 {len(city)} 个城市组合。Sales 最高的是 {top_city_sales['City']}, {top_city_sales['State']}（{money(top_city_sales['Sales'])}）；Profit 最低的是 {lowest_city_profit['City']}, {lowest_city_profit['State']}（{money(lowest_city_profit['Profit'])}）。",
        "",
        "### 【可以说明什么】",
        "可以根据销售规模、利润、利润率和排名差异识别地区表现不匹配的现象。",
        "",
        "### 【不能说明什么】",
        "不能仅按 Sales 排名判断经营最好，也不能断言地区本身导致利润差异。",
        "",
        "## 5. 商品结构",
        "",
        "### 【观察到的现象】",
        f"Category 的销售规模和盈利效率差异明显；{len(negative_subcategories)} 个 Sub-Category 汇总利润为负。",
        "",
        "### 【数据证据】",
        markdown_table(category[["Category", "Sales", "Profit", "Unique Orders", "Quantity", "Profit Margin", "Sales Rank", "Profit Rank"]]),
        "",
        "Sales 最高的子类别（前 8）：",
        "",
        markdown_table(top_sub_sales),
        "",
        "### 【可以说明什么】",
        "可以识别销售贡献、利润贡献和利润率不一致的品类与子类别。",
        "",
        "### 【不能说明什么】",
        "负利润汇总不说明具体成因，也不构成自动删除商品或停售建议。",
        "",
        "## 6. Segment",
        "",
        "### 【观察到的现象】",
        "三个 Segment 均为正利润，规模和利润率存在差异，但类别数量有限。",
        "",
        "### 【数据证据】",
        markdown_table(segment_report),
        "",
        "### 【可以说明什么】",
        "Segment 可以作为客户结构的辅助拆分和筛选维度。",
        "",
        "### 【不能说明什么】",
        "不能仅凭 Segment 汇总解释地区、品类或折扣差异。是否进入核心 Dashboard 仍需结合版面和信息增量。",
        "",
        "## 7. Sales 与 Profit",
        "",
        "### 【观察到的现象】",
        f"完整交易明细的 Pearson 为 {full_sales_profit_pearson['Coefficient']:.3f}，Spearman 为 {full_sales_profit_spearman['Coefficient']:.3f}；中间 98% 敏感性子集 Pearson 为 {central_sales_profit_pearson['Coefficient']:.3f}。",
        "",
        "### 【数据证据】",
        f"完整统计使用 {int(full_sales_profit_pearson['N']):,} 条记录；敏感性子集使用 {int(central_sales_profit_pearson['N']):,} 条记录，仅用于检查极端值影响。",
        "",
        "### 【可以说明什么】",
        "可以说明交易明细层面 Sales 与 Profit 存在正向关联，且极端记录影响 Pearson 的大小。",
        "",
        "### 【不能说明什么】",
        "相关关系不等于 Sales 增加导致 Profit 增加；敏感性子集不能替代完整数据结论。",
        "",
        "## 8. Discount 与 Profit",
        "",
        "### 【观察到的现象】",
        f"Discount 与 Profit 的 Pearson 为 {discount_profit_pearson['Coefficient']:.3f}，Spearman 为 {discount_profit_spearman['Coefficient']:.3f}；{len(negative_discount_levels)} 个实际折扣水平汇总利润为负。Discount 与 Sales 的 Pearson 为 {discount_sales_pearson['Coefficient']:.3f}，Spearman 为 {discount_sales_spearman['Coefficient']:.3f}，线性和秩相关均接近 0。",
        "",
        "### 【数据证据】",
        markdown_table(discount[["Discount", "Transaction Lines", "Unique Orders", "Sales", "Profit", "Profit Margin"]]),
        "",
        f"Category 内部的 Discount–Profit Spearman 系数范围为 {category_discount_spearman['Coefficient'].min():.3f} 至 {category_discount_spearman['Coefficient'].max():.3f}，说明负向关联在三个大类内均存在，但强度不同。`category_discount_analysis.csv` 保留了每个 Category × Discount 的样本量、Sales、Profit 和利润率。",
        "",
        "### 【可以说明什么】",
        "可以描述不同实际折扣取值下的样本量、销售、利润和利润率，并识别观察性关联。",
        "",
        "### 【不能说明什么】",
        "不能据此断言折扣导致利润下降；Category、Sub-Category 等结构变量可能同时影响二者。",
        "",
        "## 9. Returns",
        "",
        "### 【观察到的现象】",
        f"唯一退货订单 {unique_returned_orders:,} 个，占全部 {data['Order ID'].nunique():,} 个订单的 {percent(unique_returned_orders / data['Order ID'].nunique())}。West 的订单级退货率为 {percent(west_return_row['Returned Order Rate'])}，其他 Region 为 {percent(other_region_returns['Returned Order Rate'].min())}–{percent(other_region_returns['Returned Order Rate'].max())}。",
        "",
        "### 【数据证据】",
        markdown_table(returns_analysis),
        "",
        "### 【可以说明什么】",
        "可以在订单层级比较整体、Region 和 Segment 的退货订单率。",
        "",
        "### 【不能说明什么】",
        "不能把 Returned=Yes 的商品明细数称为退货订单数，不能声称某一具体商品被退货，也没有退货原因证据。Returns 更适合作为辅助分析。",
        "",
        "## 10. 没有得到充分证据的方向",
        "",
        "- 数据只有 United States，不能开展国家间比较。",
        "- 只有 4 个完整年份。即使部分月份在多个年份重复表现较高，也不足以确认长期稳定季节性。",
        "- 相关分析和分组汇总都不能建立折扣、销售、地区或商品结构之间的因果关系。",
        "- Returns 缺少商品行级退货映射、退货原因和退货日期，不适合作为核心经营解释变量。",
        "- City 数量较多，未发现将全部 City 直接放入核心图表的必要；更适合作为下钻和 Tooltip。",
        "",
        "## 11. 候选发现",
        "",
        f"共保留 {len(candidate_findings)} 条有明确数字证据的候选发现，详见 `output/tables/candidate_findings.csv`。这些发现用于下一阶段筛选可视化主题，不代表已确定最终 Tableau 图表。",
        "",
        "## 12. 诊断图说明",
        "",
        "- 月度 Sales/Profit、State、Sub-Category、Sales × Profit、Discount × Profit 图均为探索性诊断图。",
        "- Sales × Profit 的中间 98% 图明确标注只用于观察主体分布，相关统计仍使用完整数据。",
        "- 本阶段未制作 Tableau 图表或 Dashboard。",
    ]
    REPORT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

    after_hash = file_sha256(INPUT_FILE)
    if before_hash != after_hash:
        raise RuntimeError("探索性分析前后 superstore_clean.csv 哈希发生变化。")

    expected_outputs = list(OUTPUT_FILES.values()) + list(FIGURE_FILES.values()) + [REPORT_FILE]
    missing_outputs = [str(path) for path in expected_outputs if not path.is_file()]
    if missing_outputs:
        raise RuntimeError(f"阶段 3 输出文件缺失：{missing_outputs}")
    empty_outputs = [str(path) for path in expected_outputs if path.stat().st_size == 0]
    if empty_outputs:
        raise RuntimeError(f"阶段 3 输出文件为空：{empty_outputs}")

    print("阶段 3 探索性分析执行成功。")
    print(f"输入：{len(data)} 行，唯一订单 {data['Order ID'].nunique()}，Sales={sales_total:.4f}，Profit={profit_total:.4f}")
    print(f"统计表：{len(OUTPUT_FILES)} 个；诊断图：{len(FIGURE_FILES)} 个；候选发现：{len(candidate_findings)} 条")
    print(f"输入文件 SHA-256 未变化：{before_hash == after_hash}")
    print(f"报告：{REPORT_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
