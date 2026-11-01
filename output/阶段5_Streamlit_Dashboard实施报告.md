# 阶段 5：Streamlit Dashboard 实施报告

## 1. 实施范围

本阶段使用清洗后的 `data/processed/superstore_clean.csv`，从零实现单页交互式 Web Dashboard。Dashboard 不读取原始 Excel，不修改清洗数据，也未改动阶段 1～3 的分析程序。

项目分析主线保持为：整体经营表现 → 时间变化 → 地区差异 → 商品结构 → Sales–Profit 关系 → Discount–盈利关系。Returns 仅作为折叠的辅助分析。

## 2. 技术栈与实际版本

| 组件 | 版本 | 用途 |
|---|---:|---|
| Python | 3.12.14 | 运行环境 |
| pandas | 3.0.1 | 数据读取、筛选与聚合 |
| Plotly | 7.1.0 | 交互式图表与美国州地图 |
| Streamlit | 1.64.0 | 单页 Dashboard、筛选器与交互 |
| matplotlib | 3.10.8 | 保留阶段 3 诊断图依赖 |
| xlrd | 2.0.2 | 保留阶段 1、2 原始 `.xls` 读取依赖 |

未使用数据库、远程 API、外部 GeoJSON、远程地图服务或复杂前端框架。

## 3. 程序结构

- `dashboard/app.py`：页面配置、四个筛选器、KPI、区块布局、动态事实说明、Returns 与口径折叠区。
- `dashboard/data_utils.py`：清洗数据读取、数据基线断言、统一筛选、统一聚合、州名映射和数字格式化。
- `dashboard/charts.py`：七张核心图及 Returns 辅助图的 Plotly 构造函数、颜色与中文 Hover。

三层职责分离，筛选条件只在 `apply_filters()` 中集中实现，各图均使用同一个筛选结果。

## 4. 数据源与保护

- Dashboard 唯一数据源：`data/processed/superstore_clean.csv`。
- 原始文件 SHA-256：`92D65880FB39A8EC1CFB1BCFFC6468FA884C32A42D7D62D2080EAA1329613AF9`。
- 清洗数据 SHA-256：`FF5CE698EF68FBF976B35AE21237A18C9A9B0FC241B816B41851B39AA991AF6F`。
- 阶段 1～3 回归前后两个哈希均保持一致。
- Dashboard 代码中未使用 `dropna()`、`drop_duplicates()` 或异常值删除；负利润、极端值、疑似重复交易明细和 Postal Code 缺失均按既定人工决策保留。

## 5. 统一统计口径

- 交易明细数：记录行数。
- 唯一订单：`Order ID.nunique()`。
- 唯一客户：`Customer ID.nunique()`。
- 商品销量：`SUM(Quantity)`。
- 销售额：`SUM(Sales)`。
- 利润：`SUM(Profit)`。
- 整体利润率：`SUM(Profit) / SUM(Sales)`，不使用行级利润率平均值。
- 平均订单销售额：`SUM(Sales) / COUNTD(Order ID)`。
- 退货订单数：`Returned == "Yes"` 的唯一 `Order ID` 数量。
- 退货订单率：唯一退货订单数 / 全部唯一订单数。
- 所有除法使用安全比率函数，分母为 0 时返回安全缺失值，不产生 Infinity。

## 6. 全局筛选器

页面顶部提供四个 `st.multiselect`：

1. 订单年份（`Order Year`）
2. 地区（`Region`）
3. 商品类别（`Category`）
4. 客户类型（`Segment`）

空选择表示全部。地区、类别和客户类型通过稳定映射显示中文，底层筛选仍使用英文原值。筛选结果为空时页面给出中文提示并停止后续绘图，不显示 NaN、Infinity 或 traceback。

## 7. 四个动态 KPI

KPI 均从当前筛选后的 DataFrame 动态计算，未硬编码显示值。无筛选状态验收结果：

| KPI | 精确验收值 | 页面主显示 |
|---|---:|---:|
| 总销售额 | $2,297,200.8603 | $2.30M |
| 总利润 | $286,397.0217 | $286.40K |
| 唯一订单 | 5,009 | 5,009 |
| 整体利润率 | 12.467217% | 12.47% |

辅助基线同步通过：9,994 条交易明细、793 个客户、1,862 个产品、37,873 件商品、平均订单销售额约 $458.61、296 个唯一退货订单、订单级退货率约 5.91%。

## 8. 七张核心图

1. **月度销售额变化趋势**：按 `Order Year-Month` 汇总，折线与小型标记；Hover 展示年月、销售额、唯一订单数和利润。
2. **月度利润变化趋势**：独立利润纵轴，增加利润为 0 的参考线；Hover 展示利润、销售额和汇总利润率。
3. **各地区销售规模与盈利效率**：横向条形长度表示销售额，颜色表示利润率；Hover 包含利润、订单数和客户数。
4. **各州利润分布与销售表现**：Plotly 原生美国州分级设色地图，颜色表示利润，销售额和利润率放入 Hover。
5. **商品子类别的销售与盈利结构**：完整显示 17 个子类别，按销售额排序，颜色以 0 为中点表示利润正负。
6. **交易明细的销售额与利润分布**：每个点对应一个 `Row ID`，颜色表示折扣，透明度为 0.52，保留全部极端值并增加利润为 0 的参考线。
7. **折扣水平与盈利表现的观察性关系**：按 12 个实际折扣取值汇总，折线加气泡，纵轴为 `SUM(Profit) / SUM(Sales)`，增加利润率为 0 的参考线。

所有核心图采用受控的中文 `hovertemplate`，隐藏无用 trace name，保留缩放、重置和图片保存等必要工具，关闭 Plotly logo。

## 9. 地图实现

地图使用 Plotly `go.Choropleth`，设置：

- `locationmode="USA-states"`
- `scope="usa"`
- `projection.type="albers usa"`

代码内置美国州全名到两位缩写的标准映射，覆盖数据中实际出现的 49 个州；绘图前后均验证无未映射州。地图不请求外部 GeoJSON 或在线地图服务，因此课堂环境离线时仍可稳定显示州边界。

利润使用以 0 为中点的蓝—中性—橙红发散色标，Texas 等负利润州能够被突出；销售额通过 Hover 提供，未强行叠加脆弱的气泡图层。

## 10. Returns 辅助分析

Returns 位于默认折叠的 `st.expander` 中，按 Region 展示订单级退货率。统计采用唯一 `Order ID`：

- 唯一退货订单：296
- 唯一订单：5,009
- 订单级退货率：约 5.91%

页面明确提示该字段不能证明具体商品被退货。

## 11. 运行方式

在项目根目录执行：

```powershell
pip install -r requirements.txt
streamlit run dashboard/app.py
```

使用项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run dashboard\app.py
```

最终默认端口启动验收地址为 `http://localhost:8501`。

## 12. 自动验证结果

- `python -m py_compile dashboard/app.py dashboard/data_utils.py dashboard/charts.py`：通过。
- 数据基线断言：通过；Sales、Profit 浮点误差阈值为 `1e-6`。
- 48 个连续月份、17 个商品子类别、49 个实际州、12 个折扣水平：通过。
- 四类单项筛选逻辑：通过。
  - 2019：3,312 条明细、1,687 个订单、Sales $733,215.2552。
  - West：3,203 条明细、1,611 个订单、Sales $725,457.8245。
  - Furniture：2,121 条明细、1,764 个订单、Sales $741,999.7953。
  - Consumer：5,191 条明细、2,586 个订单、Sales $1,161,401.3450。
- 清除筛选后 KPI 恢复全量基线：通过。
- 八个 Plotly Figure（七张核心图加 Returns）：均成功构造。
- Streamlit 默认端口启动：通过。
- `http://localhost:8501/_stcore/health`：HTTP 200，响应 `ok`。
- `code/01_data_inspection.py`：回归通过。
- `code/02_data_cleaning.py`：回归通过。
- `code/03_exploratory_analysis.py`：回归通过。

## 13. 浏览器视觉验收

使用真实浏览器在 1440×900 与 1920×1080 桌面视口完成检查：

- 中文标题、筛选器、KPI 和动态文字无乱码。
- 四个筛选器和四个 KPI 在桌面宽度下同排显示，无横向溢出。
- 七张核心图均成功渲染；美国州地图正常，17 个商品子类别完整可读。
- 散点图采用透明度控制重叠，未删除极端值；折扣图的 0 参考线与正负色彩清晰。
- 2019 UI 筛选后 KPI 为 `$733.22K / $93.44K / 1,687 / 12.74%`；清除后恢复全量。
- Returns 折叠区可正常展开，显示 296 个唯一退货订单。
- 最终页面的浏览器控制台和 Streamlit 服务日志均无新增 warning/error。

预览截图：

- `output/figures/最终Dashboard预览.png`（1920×1080）
- `output/figures/Dashboard_上半部分.png`（1920×1080）
- `output/figures/Dashboard_下半部分.png`（1920×1080）

## 14. 发现并修复的问题

1. **动态说明中的美元符号被 Markdown 当作公式标记**：改用 HTML 实体 `&#36;`，显示恢复正常，KaTeX 不再产生警告。
2. **Streamlit 1.64 弃用 `use_container_width=True`**：全部图表改为 `width="stretch"`，服务日志不再出现弃用警告。
3. **Streamlit 懒加载导致全页截图下半部为空白**：未伪造全页截图，改为真实的上、下半页 1920×1080 截图。
4. **首次测试时 8501 被本轮旧测试服务占用**：确认进程来源后结束旧测试服务，最终以默认 8501 重新启动并通过验收。

## 15. 已知限制

- 州地图颜色用于利润，销售额仅在 Hover 中呈现；未叠加州中心气泡，以避免额外坐标维护与外部依赖。
- Returns 只有订单级标记，没有商品行级退货证据、退货原因或退货日期，不能分析具体商品退货。
- 动态文字只描述可直接计算的事实，不提供因果解释。
- Streamlit 会根据浏览器宽度自动堆叠列；窄屏可浏览，但本项目主要针对桌面浏览器和课堂投影。
