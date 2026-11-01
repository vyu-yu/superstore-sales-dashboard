"""阶段 2：数据清洗与基础分析字段构造。

本脚本只读取原始 Excel，将清洗结果写入 data/processed/，不会修改原始文件。
"""

from __future__ import annotations

import hashlib
import math
import platform
import re
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
CLEAN_FILE = PROJECT_ROOT / "data" / "processed" / "superstore_clean.csv"
TABLE_DIR = PROJECT_ROOT / "output" / "tables"
CLEANING_LOG_FILE = TABLE_DIR / "数据清洗统计.csv"
COMPARISON_FILE = TABLE_DIR / "清洗前后指标对照.csv"
REPORT_FILE = PROJECT_ROOT / "output" / "阶段2_数据清洗报告.md"

DATE_COLUMNS = ["Order Date", "Ship Date"]
NUMERIC_COLUMNS = ["Sales", "Quantity", "Discount", "Profit"]
IDENTIFIER_COLUMNS = ["Order ID", "Customer ID", "Product ID"]
NEW_COLUMNS = ["Returned", "Order Year", "Order Quarter", "Order Month", "Order Year-Month"]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def is_read_only(path: Path) -> bool:
    attributes = path.stat().st_file_attributes
    return bool(attributes & stat.FILE_ATTRIBUTE_READONLY)


def display_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "（无记录）"
    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(display_value(value) for value in row) + " |")
    return "\n".join(lines)


def normalize_postal_code(value: Any) -> Any:
    """将美国邮编规范为五位字符串，并原样保留缺失。"""
    if pd.isna(value):
        return pd.NA
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if not numeric_value.is_integer():
            raise ValueError(f"Postal Code 出现非整数数值：{value}")
        text = str(int(numeric_value))
    else:
        text = str(value).strip()
        if text.endswith(".0"):
            text = text[:-2]
    if not text.isdigit() or len(text) > 5:
        raise ValueError(f"Postal Code 格式异常：{value}")
    return text.zfill(5)


def find_suspected_duplicates(orders: pd.DataFrame) -> pd.DataFrame:
    comparison_columns = [column for column in orders.columns if column != "Row ID"]
    mask = orders.duplicated(subset=comparison_columns, keep=False)
    candidates = orders.loc[mask].copy()
    if candidates.empty:
        return candidates
    group_key = pd.util.hash_pandas_object(candidates[comparison_columns], index=False)
    different_row_ids = candidates.groupby(group_key)["Row ID"].transform("nunique") > 1
    return candidates.loc[different_row_ids].copy()


def calculate_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "交易明细数": int(len(frame)),
        "唯一订单数": int(frame["Order ID"].nunique(dropna=True)),
        "唯一客户数": int(frame["Customer ID"].nunique(dropna=True)),
        "唯一产品数": int(frame["Product ID"].nunique(dropna=True)),
        "Sales总额": float(frame["Sales"].sum()),
        "Profit总额": float(frame["Profit"].sum()),
        "最早Order Date": pd.Timestamp(frame["Order Date"].min()),
        "最晚Order Date": pd.Timestamp(frame["Order Date"].max()),
    }


def metric_equal(metric: str, left: Any, right: Any) -> bool:
    if metric in {"Sales总额", "Profit总额"}:
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-6)
    if metric in {"最早Order Date", "最晚Order Date"}:
        return pd.Timestamp(left) == pd.Timestamp(right)
    return left == right


def comparison_table(
    before: dict[str, Any], after: dict[str, Any], reloaded: dict[str, Any]
) -> pd.DataFrame:
    rows = []
    for metric in before:
        consistent = metric_equal(metric, before[metric], after[metric]) and metric_equal(
            metric, before[metric], reloaded[metric]
        )
        rows.append(
            {
                "指标": metric,
                "清洗前": display_value(before[metric]),
                "清洗后（内存）": display_value(after[metric]),
                "CSV重新读取": display_value(reloaded[metric]),
                "是否一致": "是" if consistent else "否",
                "说明": "本阶段不删除交易，核心指标应保持一致。",
            }
        )
    return pd.DataFrame(rows)


def add_log(
    rows: list[dict[str, Any]],
    issue_type: str,
    fields: str,
    found: int,
    handled: int,
    method: str,
    reason: str,
    result: str,
) -> None:
    rows.append(
        {
            "问题类型": issue_type,
            "涉及字段": fields,
            "发现数量": found,
            "处理数量": handled,
            "处理方法": method,
            "处理理由": reason,
            "处理后结果": result,
        }
    )


def main() -> None:
    if not RAW_FILE.is_file():
        raise FileNotFoundError(f"未找到原始文件：{RAW_FILE}")
    if not is_read_only(RAW_FILE):
        raise PermissionError("原始文件未设置只读属性，停止清洗。")

    CLEAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    before_hash = file_sha256(RAW_FILE)
    excel_file = pd.ExcelFile(RAW_FILE, engine="xlrd")
    required_sheets = {"Orders", "Returns"}
    missing_sheets = required_sheets - set(excel_file.sheet_names)
    if missing_sheets:
        raise ValueError(f"缺少阶段 2 必需 Sheet：{sorted(missing_sheets)}")

    raw_orders = pd.read_excel(RAW_FILE, sheet_name="Orders", engine="xlrd")
    returns = pd.read_excel(RAW_FILE, sheet_name="Returns", engine="xlrd")
    original_columns = list(raw_orders.columns)
    orders = raw_orders.copy(deep=True)
    cleaning_log: list[dict[str, Any]] = []

    if len(orders) != 9994:
        raise ValueError(f"Orders 行数与人工确认结果不一致：实际 {len(orders)} 行。")
    if len(original_columns) != 21:
        raise ValueError(f"Orders 字段数与人工确认结果不一致：实际 {len(original_columns)} 个。")

    required_columns = {
        "Row ID", "Order ID", "Order Date", "Ship Date", "Customer ID", "Product ID",
        "Postal Code", "Sales", "Quantity", "Discount", "Profit", "Country/Region",
    }
    absent_columns = required_columns - set(orders.columns)
    if absent_columns:
        raise ValueError(f"Orders 缺少阶段 2 必需字段：{sorted(absent_columns)}")

    original_missing = orders.isna().sum()
    unexpected_missing = {
        column: int(count)
        for column, count in original_missing.items()
        if count > 0 and not (column == "Postal Code" and int(count) == 11)
    }
    if unexpected_missing:
        raise ValueError(f"发现未经人工确认的新缺失值，停止自动处理：{unexpected_missing}")

    before_metrics = calculate_metrics(orders)

    # 日期字段必须全部可解析，否则停止处理。
    for column in DATE_COLUMNS:
        converted = pd.to_datetime(orders[column], errors="coerce")
        introduced_missing = int((orders[column].notna() & converted.isna()).sum())
        if introduced_missing:
            raise ValueError(f"{column} 转换产生 {introduced_missing} 个新缺失值。")
        orders[column] = converted
    add_log(
        cleaning_log,
        "日期类型规范",
        ", ".join(DATE_COLUMNS),
        sum(int(raw_orders[column].notna().sum()) for column in DATE_COLUMNS),
        sum(int(orders[column].notna().sum()) for column in DATE_COLUMNS),
        "使用 pd.to_datetime 转为日期类型",
        "保证时间字段可排序和可计算",
        "未产生无法解析日期或新缺失值",
    )

    # 数值字段逐列转换，并检查是否产生新缺失。
    for column in NUMERIC_COLUMNS:
        converted = pd.to_numeric(orders[column], errors="coerce")
        introduced_missing = int((orders[column].notna() & converted.isna()).sum())
        if introduced_missing:
            raise ValueError(f"{column} 转换产生 {introduced_missing} 个新缺失值。")
        orders[column] = converted
    add_log(
        cleaning_log,
        "数值类型规范",
        ", ".join(NUMERIC_COLUMNS),
        sum(int(raw_orders[column].notna().sum()) for column in NUMERIC_COLUMNS),
        sum(int(orders[column].notna().sum()) for column in NUMERIC_COLUMNS),
        "使用 pd.to_numeric 转为数值类型",
        "保证销售、数量、折扣和利润可计算",
        "未产生转换失败或新缺失值",
    )

    row_ids = pd.to_numeric(orders["Row ID"], errors="coerce")
    if row_ids.isna().any() or not (row_ids % 1 == 0).all():
        raise ValueError("Row ID 存在缺失或非整数值。")
    orders["Row ID"] = row_ids.astype("int64")
    for column in IDENTIFIER_COLUMNS:
        orders[column] = orders[column].astype("string")
        if orders[column].isna().any():
            raise ValueError(f"标识符字段 {column} 存在缺失值。")
    add_log(
        cleaning_log,
        "标识符类型规范",
        "Row ID, " + ", ".join(IDENTIFIER_COLUMNS),
        len(orders) * 4,
        len(orders) * 4,
        "Row ID 保持整数；订单、客户和产品 ID 转为字符串",
        "标识符不应作为连续数值变量",
        "标识符完整，业务值未改变",
    )

    postal_missing_before = int(orders["Postal Code"].isna().sum())
    postal_non_missing_before = int(orders["Postal Code"].notna().sum())
    orders["Postal Code"] = orders["Postal Code"].map(normalize_postal_code).astype("string")
    postal_missing_after = int(orders["Postal Code"].isna().sum())
    invalid_postal = orders["Postal Code"].dropna().str.fullmatch(r"\d{5}").eq(False)
    if postal_missing_after != postal_missing_before:
        raise RuntimeError("Postal Code 规范化前后缺失数量发生变化。")
    if invalid_postal.any():
        raise RuntimeError("Postal Code 规范化后仍存在非五位数字格式。")
    leading_zero_postal = int(orders["Postal Code"].dropna().str.startswith("0").sum())
    add_log(
        cleaning_log,
        "Postal Code 格式规范",
        "Postal Code",
        postal_non_missing_before,
        postal_non_missing_before,
        "非缺失值转为五位字符串并保留前导 0",
        "邮编是地理标识符，不是连续数值",
        f"全部非缺失邮编为五位字符串；其中 {leading_zero_postal} 条含前导 0",
    )
    add_log(
        cleaning_log,
        "Postal Code 缺失",
        "Postal Code",
        postal_missing_before,
        0,
        "保留缺失，不插补、不删除记录",
        "邮编不是核心字段，State、City、Region 完整",
        f"仍有 {postal_missing_after} 条缺失，未产生新缺失",
    )

    full_duplicates = int(orders.duplicated(keep=False).sum())
    suspected_duplicates = find_suspected_duplicates(orders)
    suspected_row_ids = set(suspected_duplicates["Row ID"].tolist())
    if not {3406, 3407}.issubset(suspected_row_ids):
        raise RuntimeError("人工确认保留的 Row ID 3406、3407 未出现在疑似重复记录中。")
    add_log(
        cleaning_log,
        "完全重复记录",
        "全部原始字段（包含 Row ID）",
        full_duplicates,
        0,
        "仅复核，不调用 drop_duplicates",
        "没有证据支持删除",
        f"完全重复记录仍为 {full_duplicates} 条",
    )
    add_log(
        cleaning_log,
        "疑似重复记录",
        "除 Row ID 外的全部原始字段",
        len(suspected_duplicates),
        0,
        "保留 Row ID 3406、3407，并继续标记为疑似重复交易明细",
        "其他业务字段一致不足以证明其中一条为错误记录",
        f"{len(suspected_duplicates)} 条全部保留，Orders 行数未减少",
    )

    for column in NUMERIC_COLUMNS:
        q1 = orders[column].quantile(0.25)
        q3 = orders[column].quantile(0.75)
        iqr = q3 - q1
        outlier_count = int(
            ((orders[column] < q1 - 1.5 * iqr) | (orders[column] > q3 + 1.5 * iqr)).sum()
        )
        add_log(
            cleaning_log,
            f"IQR范围外{column}",
            column,
            outlier_count,
            0,
            "仅记录，不删除、不缩尾",
            "统计异常不等于错误数据",
            f"{outlier_count} 条全部保留",
        )
    negative_profit_count = int((orders["Profit"] < 0).sum())
    add_log(
        cleaning_log,
        "负 Profit",
        "Profit",
        negative_profit_count,
        0,
        "全部保留",
        "亏损交易是后续经营分析的重要信息",
        f"{negative_profit_count} 条负利润明细全部保留",
    )

    # Returns 仅用于构造唯一订单集合，禁止与 Orders 普通 merge。
    returns_order_ids = returns["Order ID"].astype("string")
    if returns_order_ids.isna().any():
        raise ValueError("Returns 的 Order ID 存在缺失，未经人工确认不能自动处理。")
    return_counts = returns_order_ids.value_counts()
    duplicate_return_ids = int((return_counts > 1).sum())
    duplicate_return_rows = int(return_counts[return_counts > 1].sum())
    unique_returned_ids = set(returns_order_ids.unique())
    unknown_return_ids = unique_returned_ids - set(orders["Order ID"].unique())
    if unknown_return_ids:
        raise ValueError(f"Returns 中出现 Orders 不存在的 Order ID：{sorted(unknown_return_ids)}")
    add_log(
        cleaning_log,
        "Returns 重复 Order ID",
        "Returns.Order ID",
        duplicate_return_rows,
        len(returns) - len(unique_returned_ids),
        "构造唯一退货 Order ID 集合；不修改原始 Returns",
        "避免与 Orders 直接连接造成一对多或多对多膨胀",
        f"由 {len(returns)} 行得到 {len(unique_returned_ids)} 个唯一退货订单",
    )

    row_count_before_returned = len(orders)
    orders["Returned"] = orders["Order ID"].isin(unique_returned_ids).map({True: "Yes", False: "No"})
    if len(orders) != row_count_before_returned:
        raise RuntimeError("构造 Returned 后 Orders 行数发生变化。")
    returned_detail_yes = int((orders["Returned"] == "Yes").sum())
    returned_detail_no = int((orders["Returned"] == "No").sum())
    add_log(
        cleaning_log,
        "退货状态字段构造",
        "Returned",
        len(unique_returned_ids),
        len(orders),
        "使用 Orders['Order ID'].isin(唯一退货Order ID集合) 生成 Yes/No",
        "在不连接、不增加行数的前提下提供退货分析字段",
        f"Yes 明细 {returned_detail_yes} 条，No 明细 {returned_detail_no} 条；总行数 {len(orders)}",
    )

    orders["Order Year"] = orders["Order Date"].dt.year.astype("int64")
    orders["Order Quarter"] = "Q" + orders["Order Date"].dt.quarter.astype(str)
    orders["Order Month"] = orders["Order Date"].dt.month.astype("int64")
    orders["Order Year-Month"] = orders["Order Date"].dt.to_period("M").dt.to_timestamp()
    if orders[NEW_COLUMNS].isna().any().any():
        missing_new_fields = orders[NEW_COLUMNS].isna().sum()
        missing_new_fields = missing_new_fields[missing_new_fields > 0].to_dict()
        raise RuntimeError(f"新增字段出现缺失值：{missing_new_fields}")
    add_log(
        cleaning_log,
        "时间分析字段构造",
        ", ".join(NEW_COLUMNS[1:]),
        len(orders),
        len(orders),
        "从 Order Date 构造年、季度、月和月份首日",
        "提供可正确排序的基础时间维度",
        "四个时间字段均无缺失，Order Year-Month 为真实日期",
    )

    if original_columns != list(orders.columns[: len(original_columns)]):
        raise RuntimeError("原始字段的名称或顺序发生变化。")
    if list(orders.columns[len(original_columns) :]) != NEW_COLUMNS:
        raise RuntimeError("新增字段的名称或顺序不符合阶段 2 设计。")
    if "Row Profit Ratio" in orders.columns:
        raise RuntimeError("本阶段不应创建 Row Profit Ratio。")

    cleaned_missing = orders[original_columns].isna().sum()
    if not original_missing.equals(cleaned_missing):
        differences = pd.DataFrame({"清洗前": original_missing, "清洗后": cleaned_missing})
        differences = differences[differences["清洗前"] != differences["清洗后"]]
        raise RuntimeError(f"原始字段缺失数量发生未经解释的变化：\n{differences}")

    after_metrics = calculate_metrics(orders)
    for metric in before_metrics:
        if not metric_equal(metric, before_metrics[metric], after_metrics[metric]):
            raise RuntimeError(f"核心指标 {metric} 在保存前发生变化。")

    # UTF-8 BOM 便于 Excel/Tableau 识别中文；日期统一保存为 ISO 格式。
    orders.to_csv(CLEAN_FILE, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")

    csv_dtypes = {
        "Order ID": "string",
        "Customer ID": "string",
        "Product ID": "string",
        "Postal Code": "string",
        "Returned": "string",
        "Order Quarter": "string",
    }
    reloaded = pd.read_csv(
        CLEAN_FILE,
        encoding="utf-8-sig",
        dtype=csv_dtypes,
        parse_dates=["Order Date", "Ship Date", "Order Year-Month"],
    )
    reloaded_metrics = calculate_metrics(reloaded)
    comparison = comparison_table(before_metrics, after_metrics, reloaded_metrics)
    if (comparison["是否一致"] != "是").any():
        raise RuntimeError(f"CSV 重新读取后核心指标不一致：\n{comparison}")
    if len(reloaded) != 9994 or len(reloaded.columns) != 26:
        raise RuntimeError(
            f"CSV 重读规模异常：{len(reloaded)} 行 × {len(reloaded.columns)} 列。"
        )
    if not orders["Postal Code"].fillna("<NA>").equals(
        reloaded["Postal Code"].fillna("<NA>")
    ):
        raise RuntimeError("CSV 重读后 Postal Code 字符串或前导 0 发生变化。")
    if int(reloaded["Postal Code"].isna().sum()) != postal_missing_before:
        raise RuntimeError("CSV 重读后 Postal Code 缺失数量发生变化。")

    cleaning_log_frame = pd.DataFrame(cleaning_log)
    cleaning_log_frame.to_csv(CLEANING_LOG_FILE, index=False, encoding="utf-8-sig")
    comparison.to_csv(COMPARISON_FILE, index=False, encoding="utf-8-sig")

    dtype_rows = pd.DataFrame(
        [{"字段": column, "CSV重读数据类型": str(dtype)} for column, dtype in reloaded.dtypes.items()]
    )
    report = [
        "# 阶段 2：数据清洗与分析字段构造",
        "",
        "## 1. 环境与原始文件保护",
        "",
        f"- Python：{platform.python_version()}",
        f"- pandas：{pd.__version__}",
        f"- xlrd：{xlrd.__version__}",
        f"- 原始文件：`{RAW_FILE.relative_to(PROJECT_ROOT).as_posix()}`",
        f"- 清洗前 SHA-256：`{before_hash}`",
        "- 原始文件只读：是",
        "- 原始 Excel 只读取，未修改、覆盖或重新保存。",
        "",
        "## 2. 实际执行的清洗操作",
        "",
        markdown_table(cleaning_log_frame),
        "",
        "## 3. 人工确认问题的执行结果",
        "",
        f"- Row ID 3406、3407 均保留。疑似重复交易明细共 {len(suspected_duplicates)} 条，本阶段未删除。",
        f"- Postal Code 的 {postal_missing_after} 条缺失全部保留，未插补、未删除记录。",
        f"- 非缺失 Postal Code 全部规范为五位字符串，其中 {leading_zero_postal} 条包含前导 0。",
        f"- 阶段 1 识别的 Sales、Quantity、Discount、Profit IQR 范围外数据和 {negative_profit_count} 条负利润记录全部保留。",
        "- Country/Region 原始字段完整保留，但不构造国家间比较字段。",
        "",
        "## 4. 新增字段",
        "",
        markdown_table(
            pd.DataFrame(
                [
                    {"字段": "Returned", "类型": "字符串", "定义": "Order ID 是否在唯一退货订单集合中，值为 Yes/No"},
                    {"字段": "Order Year", "类型": "整数", "定义": "Order Date 的年份"},
                    {"字段": "Order Quarter", "类型": "字符串", "定义": "Q1、Q2、Q3、Q4"},
                    {"字段": "Order Month", "类型": "整数", "定义": "1~12 月，支持正确排序"},
                    {"字段": "Order Year-Month", "类型": "日期", "定义": "订单月份的第一天，支持跨年排序"},
                ]
            )
        ),
        "",
        "未创建 `Row Profit Ratio`。后续整体利润率统一使用 `SUM(Profit) / SUM(Sales)`，不能用行级利润率的简单平均代替。未创建 Discount Band、高低销售或高低利润分组。",
        "",
        "## 5. Returns 处理结果",
        "",
        f"- Returns 原始行数：{len(returns):,}",
        f"- 唯一退货订单数：{len(unique_returned_ids):,}",
        f"- 重复 Order ID 种数：{duplicate_return_ids:,}",
        f"- 重复 Order ID 涉及行数：{duplicate_return_rows:,}",
        f"- Returned = Yes 的交易明细数：{returned_detail_yes:,}",
        f"- Returned = No 的交易明细数：{returned_detail_no:,}",
        "- 唯一退货订单数和退货交易明细数属于不同统计层级。",
        "- 未对 Orders 与 Returns 执行普通 merge，构造 Returned 前后 Orders 均为 9,994 行。",
        "",
        "## 6. 清洗前后指标对照",
        "",
        markdown_table(comparison),
        "",
        "## 7. CSV 重新读取验证",
        "",
        f"- 行数：{len(reloaded):,}",
        f"- 字段数：{len(reloaded.columns)}",
        f"- Order Date 范围：{reloaded['Order Date'].min():%Y-%m-%d} 至 {reloaded['Order Date'].max():%Y-%m-%d}",
        f"- Sales 总额：{reloaded['Sales'].sum():.6f}",
        f"- Profit 总额：{reloaded['Profit'].sum():.6f}",
        f"- 唯一订单数：{reloaded['Order ID'].nunique():,}",
        "",
        markdown_table(dtype_rows),
        "",
        "CSV 文件采用 UTF-8 BOM 编码。Python 重读时显式将 Postal Code 和各类 ID 指定为字符串，并将日期字段解析为日期类型。Tableau 导入时也应将 Postal Code 设置为字符串维度。",
        "",
        "## 8. 阶段结论",
        "",
        "- 原始 21 个字段全部保留，新增 5 个基础分析字段。",
        "- 未删除任何交易明细，未填补缺失邮编，未处理统计极端值。",
        "- 清洗前、清洗后内存数据和 CSV 重读数据的核心指标全部一致。",
        "- 本阶段未开展探索性分析，未制作图表或 Tableau Dashboard。",
    ]
    REPORT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

    after_hash = file_sha256(RAW_FILE)
    if before_hash != after_hash:
        raise RuntimeError("原始文件清洗前后哈希不一致。")

    expected_files = [CLEAN_FILE, CLEANING_LOG_FILE, COMPARISON_FILE, REPORT_FILE]
    missing_outputs = [str(path) for path in expected_files if not path.is_file()]
    if missing_outputs:
        raise RuntimeError(f"阶段 2 输出文件缺失：{missing_outputs}")

    print("阶段 2 数据清洗执行成功。")
    print(f"清洗数据：{len(reloaded)} 行 × {len(reloaded.columns)} 列")
    print(f"Returned：Yes={returned_detail_yes}，No={returned_detail_no}")
    print(f"唯一退货订单：{len(unique_returned_ids)}")
    print(f"原始文件 SHA-256 未变化：{before_hash == after_hash}")
    print(f"输出：{CLEAN_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
