"""阶段 1：原始数据结构与数据质量检查。

只读取 data/raw/sample_-_superstore.xls，不修改、覆盖或重新保存原始文件。
"""

from __future__ import annotations

import hashlib
import platform
import stat
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import xlrd


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "sample_-_superstore.xls"
TABLE_DIR = PROJECT_ROOT / "output" / "tables"
REPORT_FILE = PROJECT_ROOT / "output" / "阶段1_数据检查报告.md"

FIELD_INFO_FILE = TABLE_DIR / "字段信息.csv"
MISSING_FILE = TABLE_DIR / "缺失值检查.csv"
NUMERIC_FILE = TABLE_DIR / "数值字段统计.csv"
DUPLICATE_FILE = TABLE_DIR / "疑似重复记录.csv"
RETURNS_FILE = TABLE_DIR / "Returns检查.csv"


def file_sha256(path: Path) -> str:
    """分块计算文件哈希，避免修改原始文件。"""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def is_read_only(path: Path) -> bool:
    """检查 Windows 文件只读属性。"""
    attributes = path.stat().st_file_attributes
    return bool(attributes & stat.FILE_ATTRIBUTE_READONLY)


def csv_value(value: Any) -> Any:
    """将日期等对象转为稳定、可读的 CSV 值。"""
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    return value


def display_value(value: Any) -> str:
    """生成 Markdown 表格中的紧凑显示值。"""
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(frame: pd.DataFrame, max_rows: int | None = None) -> str:
    """不依赖额外库生成 Markdown 表格。"""
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


def save_csv(frame: pd.DataFrame, path: Path) -> None:
    """统一使用 UTF-8 BOM，便于 Excel 正确显示中文。"""
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def available_columns(frame: pd.DataFrame, requested: list[str]) -> list[str]:
    return [column for column in requested if column in frame.columns]


def build_field_info(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sheet_name, frame in sheets.items():
        for column in frame.columns:
            missing_count = int(frame[column].isna().sum())
            rows.append(
                {
                    "Sheet": sheet_name,
                    "字段": column,
                    "数据类型": str(frame[column].dtype),
                    "非空数量": int(frame[column].notna().sum()),
                    "缺失数量": missing_count,
                    "缺失比例": missing_count / len(frame) if len(frame) else 0.0,
                    "缺失比例(%)": missing_count / len(frame) * 100 if len(frame) else 0.0,
                    "唯一值数量": int(frame[column].nunique(dropna=True)),
                }
            )
    return pd.DataFrame(rows)


def build_missing_records(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    all_columns: list[str] = []
    for frame in sheets.values():
        for column in frame.columns:
            if column not in all_columns:
                all_columns.append(column)

    output_columns = ["Sheet", "缺失字段", "源数据行号"] + all_columns
    rows: list[dict[str, Any]] = []
    for sheet_name, frame in sheets.items():
        missing_columns = [column for column in frame.columns if frame[column].isna().any()]
        for column in missing_columns:
            for index in frame.index[frame[column].isna()]:
                record = {
                    "Sheet": sheet_name,
                    "缺失字段": column,
                    "源数据行号": int(index) + 2,
                }
                record.update({key: csv_value(value) for key, value in frame.loc[index].items()})
                rows.append(record)
    return pd.DataFrame(rows, columns=output_columns)


def build_numeric_summary(orders: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in ["Sales", "Quantity", "Discount", "Profit"]:
        if column not in orders.columns:
            continue
        numeric = pd.to_numeric(orders[column], errors="coerce")
        description = numeric.describe(percentiles=[0.25, 0.5, 0.75])
        q1 = description.get("25%", float("nan"))
        q3 = description.get("75%", float("nan"))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        rows.append(
            {
                "字段": column,
                "count": description.get("count"),
                "mean": description.get("mean"),
                "std": description.get("std"),
                "min": description.get("min"),
                "25%": q1,
                "50%": description.get("50%"),
                "75%": q3,
                "max": description.get("max"),
                "缺失数量": int(orders[column].isna().sum()),
                "零值数量": int((numeric == 0).sum()),
                "负数数量": int((numeric < 0).sum()),
                "IQR下界": lower,
                "IQR上界": upper,
                "IQR范围外数量": int(((numeric < lower) | (numeric > upper)).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_suspected_duplicates(orders: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    full_duplicate_count = int(orders.duplicated(keep=False).sum())
    exact_duplicate_groups = int(
        orders.loc[orders.duplicated(keep=False)].drop_duplicates().shape[0]
    )

    if "Row ID" not in orders.columns:
        columns = ["重复组编号", "标记"] + list(orders.columns)
        return pd.DataFrame(columns=columns), full_duplicate_count, exact_duplicate_groups

    comparison_columns = [column for column in orders.columns if column != "Row ID"]
    duplicated_mask = orders.duplicated(subset=comparison_columns, keep=False)
    candidates = orders.loc[duplicated_mask].copy()
    if candidates.empty:
        columns = ["重复组编号", "标记"] + list(orders.columns)
        return pd.DataFrame(columns=columns), full_duplicate_count, exact_duplicate_groups

    group_key = pd.util.hash_pandas_object(
        candidates[comparison_columns], index=False
    )
    row_id_counts = candidates.groupby(group_key, dropna=False)["Row ID"].transform("nunique")
    candidates = candidates.loc[row_id_counts > 1].copy()
    if candidates.empty:
        columns = ["重复组编号", "标记"] + list(orders.columns)
        return pd.DataFrame(columns=columns), full_duplicate_count, exact_duplicate_groups

    final_key = pd.util.hash_pandas_object(
        candidates[comparison_columns], index=False
    )
    candidates.insert(0, "标记", "疑似重复交易明细")
    candidates.insert(0, "重复组编号", pd.factorize(final_key)[0] + 1)
    return candidates, full_duplicate_count, exact_duplicate_groups


def build_returns_check(
    orders: pd.DataFrame, returns: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if "Order ID" not in orders.columns or "Order ID" not in returns.columns:
        raise ValueError("Orders 或 Returns 缺少 Order ID，无法完成退货键检查。")

    order_counts = orders["Order ID"].value_counts(dropna=False)
    return_counts = returns["Order ID"].value_counts(dropna=False)
    order_ids = set(orders["Order ID"].dropna())
    return_ids = set(returns["Order ID"].dropna())
    absent_ids = sorted(return_ids - order_ids)
    duplicate_returns = return_counts[return_counts > 1]

    predicted_left_merge_rows = 0
    for order_id, order_count in order_counts.items():
        return_count = int(return_counts.get(order_id, 0))
        predicted_left_merge_rows += int(order_count) * max(return_count, 1)

    direct_merge_risk = bool((order_counts > 1).any() and (return_counts > 1).any())
    metrics = {
        "总行数": int(len(returns)),
        "字段数": int(len(returns.columns)),
        "唯一Order ID数量": int(returns["Order ID"].nunique(dropna=True)),
        "重复Order ID种数": int(len(duplicate_returns)),
        "重复Order ID涉及行数": int(duplicate_returns.sum()),
        "Returns中不在Orders的Order ID数量": int(len(absent_ids)),
        "Orders原始行数": int(len(orders)),
        "直接左连接预计行数": int(predicted_left_merge_rows),
        "直接左连接预计新增行数": int(predicted_left_merge_rows - len(orders)),
        "存在多对多膨胀风险": direct_merge_risk,
    }

    rows: list[dict[str, Any]] = []
    for key, value in metrics.items():
        rows.append(
            {
                "检查类型": "汇总",
                "指标": key,
                "Order ID": "",
                "记录数": value,
                "是否存在于Orders": "",
                "说明": "",
            }
        )
    for order_id, count in duplicate_returns.items():
        rows.append(
            {
                "检查类型": "重复Order ID",
                "指标": "Returns键重复",
                "Order ID": order_id,
                "记录数": int(count),
                "是否存在于Orders": order_id in order_ids,
                "说明": "直接连接前必须先将退货Order ID去重。",
            }
        )
    for order_id in absent_ids:
        rows.append(
            {
                "检查类型": "Orders中不存在",
                "指标": "键覆盖检查",
                "Order ID": order_id,
                "记录数": int(return_counts[order_id]),
                "是否存在于Orders": False,
                "说明": "生成Returned标记前需确认该退货订单的来源。",
            }
        )
    return pd.DataFrame(rows), metrics


def feasibility_assessment(
    orders: pd.DataFrame, returns: pd.DataFrame | None
) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    def has_usable(columns: list[str]) -> bool:
        return all(
            column in orders.columns
            and orders[column].notna().sum() > 0
            and orders[column].nunique(dropna=True) > 1
            for column in columns
        )

    order_dates = pd.to_datetime(orders.get("Order Date"), errors="coerce")
    month_count = int(order_dates.dt.to_period("M").nunique()) if order_dates.notna().any() else 0

    checks = [
        ("销售额时间趋势", has_usable(["Order Date", "Sales"]) and month_count >= 12, "适合核心分析"),
        ("利润时间趋势", has_usable(["Order Date", "Profit"]) and month_count >= 12, "适合核心分析"),
        ("地区销售分析", has_usable(["Region", "Sales"]), "适合核心分析"),
        ("地区利润分析", has_usable(["Region", "Profit"]), "适合核心分析"),
        ("商品类别分析", has_usable(["Category", "Sales", "Profit"]), "适合核心分析"),
        ("商品子类别分析", has_usable(["Sub-Category", "Sales", "Profit"]), "适合核心分析"),
        ("Sales × Profit", has_usable(["Sales", "Profit"]), "适合核心分析"),
        ("Discount × Profit", has_usable(["Discount", "Profit"]), "适合核心分析"),
        ("Segment 分析", has_usable(["Segment", "Sales", "Profit"]), "适合辅助分析"),
    ]
    for topic, suitable, preferred in checks:
        rows.append(
            {
                "方向": topic,
                "分类": preferred if suitable else "暂不建议",
                "依据": "所需字段存在、有效值充足且具有多个取值。" if suitable else "缺少所需字段、有效数据或足够变化。",
            }
        )

    returns_suitable = (
        returns is not None
        and "Order ID" in returns.columns
        and returns["Order ID"].notna().any()
        and "Order ID" in orders.columns
    )
    rows.append(
        {
            "方向": "Returns 分析",
            "分类": "适合辅助分析" if returns_suitable else "暂不建议",
            "依据": (
                "退货订单键可用于生成Returned标记，但需先去重并验证键覆盖。"
                if returns_suitable
                else "缺少可用的退货订单键。"
            ),
        }
    )
    return pd.DataFrame(rows)


def main() -> None:
    if not RAW_FILE.is_file():
        raise FileNotFoundError(f"未找到原始文件：{RAW_FILE}")
    if not is_read_only(RAW_FILE):
        raise PermissionError("原始文件未设置只读属性，停止检查以避免误修改。")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    before_hash = file_sha256(RAW_FILE)

    # 先读取工作簿结构，再逐表读取，关键读取错误直接抛出。
    excel_file = pd.ExcelFile(RAW_FILE, engine="xlrd")
    sheet_names = excel_file.sheet_names
    sheets = {
        sheet_name: pd.read_excel(RAW_FILE, sheet_name=sheet_name, engine="xlrd")
        for sheet_name in sheet_names
    }

    field_info = build_field_info(sheets)
    missing_records = build_missing_records(sheets)
    save_csv(field_info, FIELD_INFO_FILE)
    save_csv(missing_records, MISSING_FILE)

    report: list[str] = [
        "# 阶段 1：原始数据结构与数据质量检查",
        "",
        "## 1. 环境与原始文件保护",
        "",
        f"- Python：{platform.python_version()}",
        f"- pandas：{pd.__version__}",
        f"- xlrd：{xlrd.__version__}",
        f"- 原始文件：`{RAW_FILE.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- 文件大小：{RAW_FILE.stat().st_size:,} 字节",
        f"- SHA-256：`{before_hash}`",
        "- 原始文件只读：是",
        "- 读取方式：`pd.ExcelFile(..., engine=\"xlrd\")` 与 `pd.read_excel(..., engine=\"xlrd\")`",
        "- `.xls` 可可靠读取，本阶段未创建 `.xlsx` 工作副本。",
        "",
        "## 2. 工作簿结构",
        "",
        f"实际 Sheet 数量：{len(sheet_names)}。",
        "",
    ]

    structure_rows = []
    for sheet_name, frame in sheets.items():
        if sheet_name == "Orders":
            purpose = "订单商品明细主表"
        elif sheet_name == "Returns":
            purpose = "退货订单辅助表"
        elif sheet_name == "People":
            purpose = "区域负责人辅助表"
        else:
            purpose = "待确认"
        structure_rows.append(
            {
                "Sheet": sheet_name,
                "行数": len(frame),
                "列数": len(frame.columns),
                "字段": ", ".join(map(str, frame.columns)),
                "用途判断": purpose,
            }
        )
    report.extend([markdown_table(pd.DataFrame(structure_rows)), ""])

    orders = sheets.get("Orders")
    if orders is None:
        empty_numeric = pd.DataFrame(
            columns=[
                "字段", "count", "mean", "std", "min", "25%", "50%", "75%", "max",
                "缺失数量", "零值数量", "负数数量", "IQR下界", "IQR上界", "IQR范围外数量",
            ]
        )
        save_csv(empty_numeric, NUMERIC_FILE)
        save_csv(pd.DataFrame(columns=["重复组编号", "标记"]), DUPLICATE_FILE)
        report.extend(["## 3. Orders 检查", "", "未发现 `Orders` Sheet，无法执行 Orders 数据质量检查。", ""])
        feasibility = pd.DataFrame(
            [{"方向": direction, "分类": "暂不建议", "依据": "未发现Orders主表。"} for direction in [
                "销售额时间趋势", "利润时间趋势", "地区销售分析", "地区利润分析", "商品类别分析",
                "商品子类别分析", "Sales × Profit", "Discount × Profit", "Segment 分析", "Returns 分析",
            ]]
        )
    else:
        numeric_summary = build_numeric_summary(orders)
        suspected_duplicates, full_duplicate_count, exact_duplicate_groups = build_suspected_duplicates(orders)
        save_csv(numeric_summary, NUMERIC_FILE)
        save_csv(suspected_duplicates, DUPLICATE_FILE)

        report.extend(
            [
                "## 3. Orders 数据结构",
                "",
                f"- 总数据行数：{len(orders):,}",
                f"- 字段总数：{len(orders.columns)}",
                f"- 全部字段：{', '.join(map(str, orders.columns))}",
                f"- 唯一 Order ID：{orders['Order ID'].nunique(dropna=True):,}" if "Order ID" in orders else "- 缺少 Order ID",
                f"- 唯一 Customer ID：{orders['Customer ID'].nunique(dropna=True):,}" if "Customer ID" in orders else "- 缺少 Customer ID",
                f"- 唯一 Product ID：{orders['Product ID'].nunique(dropna=True):,}" if "Product ID" in orders else "- 缺少 Product ID",
                "",
                "Orders 的一行是一条商品交易明细。同一个订单可以包含多个商品，因此交易明细行数通常大于按 `Order ID` 去重后的订单数量；这属于正常业务结构，不能把重复的 `Order ID` 当作重复数据。",
                "",
                "### 字段信息",
                "",
                markdown_table(field_info[field_info["Sheet"] == "Orders"]),
                "",
                "### 前 10 行",
                "",
                markdown_table(orders.head(10)),
                "",
                "## 4. 日期字段检查",
                "",
            ]
        )

        date_rows = []
        parsed_dates: dict[str, pd.Series] = {}
        for column in ["Order Date", "Ship Date"]:
            if column not in orders.columns:
                date_rows.append({"字段": column, "状态": "字段不存在"})
                continue
            parsed = pd.to_datetime(orders[column], errors="coerce")
            parsed_dates[column] = parsed
            invalid_count = int((orders[column].notna() & parsed.isna()).sum())
            date_rows.append(
                {
                    "字段": column,
                    "最早日期": parsed.min(),
                    "最晚日期": parsed.max(),
                    "包含年份": ", ".join(map(str, sorted(parsed.dropna().dt.year.unique()))),
                    "无法解析数量": invalid_count,
                    "早于1900年数量": int((parsed.dt.year < 1900).sum()),
                    "晚于当前日期数量": int((parsed.dt.date > date.today()).sum()),
                }
            )
        report.extend([markdown_table(pd.DataFrame(date_rows)), ""])
        if "Order Date" in parsed_dates and "Ship Date" in parsed_dates:
            early_ship = parsed_dates["Ship Date"] < parsed_dates["Order Date"]
            report.extend(
                [
                    f"`Ship Date` 早于 `Order Date` 的记录数：{int(early_ship.sum())}。",
                    "跨年发货本身不判定为异常；这里只检查日期逻辑和明显超出合理日历范围的情况。",
                    "",
                ]
            )

        report.extend(["## 5. 分类字段检查", ""])
        for column in ["Ship Mode", "Segment", "Country/Region", "Region", "Category", "Sub-Category"]:
            if column not in orders.columns:
                report.extend([f"### {column}", "", "字段不存在。", ""])
                continue
            counts = orders[column].value_counts(dropna=False).rename_axis(column).reset_index(name="数量")
            report.extend([f"### {column}", "", markdown_table(counts), ""])
        state_count = orders["State"].nunique(dropna=True) if "State" in orders else "字段不存在"
        city_count = orders["City"].nunique(dropna=True) if "City" in orders else "字段不存在"
        report.extend([f"- State 唯一值数量：{state_count}", f"- City 唯一值数量：{city_count}", ""])

        report.extend(
            [
                "## 6. 数值字段检查",
                "",
                markdown_table(numeric_summary),
                "",
                "IQR 范围外记录只作为统计异常候选，不代表数据错误，本阶段不删除任何记录。",
                "",
            ]
        )
        detail_columns = available_columns(
            orders,
            ["Row ID", "Order ID", "Product Name", "Category", "Sub-Category", "Sales", "Quantity", "Discount", "Profit"],
        )
        extreme_specs = [("Sales 最大记录", "Sales", False), ("Profit 最大记录", "Profit", False), ("Profit 最小记录", "Profit", True)]
        for title, column, smallest in extreme_specs:
            report.extend([f"### {title}", ""])
            if column not in orders.columns:
                report.extend(["字段不存在。", ""])
                continue
            extreme = orders.nsmallest(5, column) if smallest else orders.nlargest(5, column)
            report.extend([markdown_table(extreme[detail_columns]), ""])

        report.extend(
            [
                "## 7. 重复数据检查",
                "",
                f"- A. 包含 `Row ID` 的整行完全重复记录数：{full_duplicate_count}",
                f"- A. 整行完全重复组数：{exact_duplicate_groups}",
                f"- B. 排除 `Row ID` 后，Row ID 不同但其他字段完全相同的疑似重复交易明细：{len(suspected_duplicates)} 行",
            ]
        )
        if "Order ID" in orders.columns:
            order_counts = orders["Order ID"].value_counts()
            repeated_orders = order_counts[order_counts > 1]
            report.extend(
                [
                    f"- C. 出现多条明细的 Order ID 数量：{len(repeated_orders):,}",
                    f"- C. 这些订单涉及的交易明细行数：{int(repeated_orders.sum()):,}",
                    f"- C. 单个 Order ID 最多包含明细数：{int(order_counts.max())}",
                    "",
                    "`Order ID` 重复反映一个订单包含多项商品，不能作为删除依据。疑似重复交易明细仅标记并输出，本阶段不删除。",
                    "",
                ]
            )

        report.extend(["## 8. 缺失值检查", ""])
        missing_summary = field_info[field_info["缺失数量"] > 0][
            ["Sheet", "字段", "缺失数量", "缺失比例", "缺失比例(%)"]
        ].copy()
        core_fields = {
            "Order ID", "Order Date", "Region", "Category", "Sub-Category",
            "Sales", "Profit", "Discount", "Quantity",
        }

        def missing_impact(row: pd.Series) -> str:
            if row["Sheet"] == "Orders" and row["字段"] == "Postal Code":
                return "不影响当前核心分析；只会限制邮编层级地图或地理细分。"
            if row["Sheet"] == "Orders" and row["字段"] in core_fields:
                return "会影响使用该字段的核心分析，后续需逐条判断。"
            if row["Sheet"] == "Returns" and row["字段"] == "Order ID":
                return "会影响退货标记，后续需核查对应记录。"
            return "当前不直接影响核心分析，不应因此删除整行。"

        missing_summary["对核心分析的影响"] = missing_summary.apply(missing_impact, axis=1)
        if missing_summary.empty:
            report.extend(["所有 Sheet 均未发现缺失值。", ""])
        else:
            report.extend(
                [
                    markdown_table(missing_summary),
                    "",
                    "对应记录已写入 `output/tables/缺失值检查.csv`。本阶段不删除缺失记录。",
                    "核心分析影响需结合缺失字段判断：核心指标、日期或主维度缺失会影响相应分析；辅助字段缺失通常不应导致整行删除。",
                    "",
                ]
            )

        feasibility = feasibility_assessment(orders, sheets.get("Returns"))

    returns = sheets.get("Returns")
    if returns is None or orders is None:
        returns_output = pd.DataFrame(
            [{"检查类型": "汇总", "指标": "Returns状态", "Order ID": "", "记录数": 0, "是否存在于Orders": "", "说明": "缺少Returns或Orders，无法检查。"}]
        )
        save_csv(returns_output, RETURNS_FILE)
        report.extend(["## 9. Returns 检查", "", "缺少 `Returns` 或 `Orders` Sheet，无法完成退货键检查。", ""])
    else:
        returns_output, returns_metrics = build_returns_check(orders, returns)
        save_csv(returns_output, RETURNS_FILE)
        report.extend(
            [
                "## 9. Returns 检查",
                "",
                f"- 总行数：{len(returns):,}",
                f"- 字段数：{len(returns.columns)}",
                f"- 字段：{', '.join(map(str, returns.columns))}",
                f"- 唯一 Order ID：{returns_metrics['唯一Order ID数量']:,}",
                f"- 重复 Order ID 种数：{returns_metrics['重复Order ID种数']:,}",
                f"- 重复 Order ID 涉及行数：{returns_metrics['重复Order ID涉及行数']:,}",
                f"- Returns 中不在 Orders 的 Order ID 数量：{returns_metrics['Returns中不在Orders的Order ID数量']:,}",
                f"- 若直接左连接，预计从 {returns_metrics['Orders原始行数']:,} 行增加到 {returns_metrics['直接左连接预计行数']:,} 行，新增 {returns_metrics['直接左连接预计新增行数']:,} 行。",
                f"- 多对多膨胀风险：{'存在' if returns_metrics['存在多对多膨胀风险'] else '未发现'}",
                "",
                "未来正确方案：先从 `Returns` 提取非空且唯一的 `Order ID` 集合，再用 `Orders['Order ID'].isin(returned_order_ids)` 生成布尔型 `Returned` 标记。生成前后必须验证 Orders 行数不变。",
                "",
            ]
        )

    people = sheets.get("People")
    report.extend(["## 10. People 检查", ""])
    if people is None:
        report.extend(["未发现 `People` Sheet。", ""])
    else:
        report.extend(
            [
                f"- 总行数：{len(people):,}",
                f"- 字段：{', '.join(map(str, people.columns))}",
                "",
                markdown_table(people),
                "",
                "People 仅提供区域与负责人映射，记录规模和字段有限。它可用于辅助说明或负责人筛选，但本阶段没有证据支持将其强行纳入核心分析。",
                "",
            ]
        )

    report.extend(
        [
            "## 11. 分析可行性评估",
            "",
            markdown_table(feasibility),
            "",
            "以上仅为数据可行性评估，不代表最终 Dashboard 图表决策。",
            "",
            "## 12. 本阶段处理结论",
            "",
            "- 只执行读取、检查、标记和结果输出。",
            "- 未删除缺失值、重复项、IQR 范围外记录或任何原始记录。",
            "- 未修改、覆盖或重新保存原始 `.xls`。",
        ]
    )

    REPORT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

    after_hash = file_sha256(RAW_FILE)
    if before_hash != after_hash:
        raise RuntimeError("原始文件读取前后哈希不一致，停止并检查文件是否被修改。")

    expected_outputs = [FIELD_INFO_FILE, MISSING_FILE, NUMERIC_FILE, DUPLICATE_FILE, RETURNS_FILE, REPORT_FILE]
    missing_outputs = [str(path) for path in expected_outputs if not path.is_file()]
    if missing_outputs:
        raise RuntimeError(f"以下输出文件未生成：{missing_outputs}")

    print("阶段 1 数据检查执行成功。")
    print(f"工作簿 Sheet：{sheet_names}")
    for sheet_name, frame in sheets.items():
        print(f"{sheet_name}: {len(frame)} 行 × {len(frame.columns)} 列")
    print(f"读取前后 SHA-256 一致：{before_hash == after_hash}")
    print(f"报告：{REPORT_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
