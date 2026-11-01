# 部署与发布

## GitHub 仓库

本项目的 GitHub 仓库只保存源代码、分析结果和文档，不提交 `.venv/`、缓存文件或本地密钥。

## Streamlit Community Cloud

Streamlit 页面需要 Python 服务器运行，因此不能直接部署到 GitHub Pages。推荐使用 Streamlit Community Cloud 获得可分享的在线 Demo。

1. 将项目推送到 GitHub 仓库。
2. 打开 <https://share.streamlit.io/> 并使用 GitHub 账号登录。
3. 点击 `Create app`。
4. 选择本项目的 GitHub 仓库和 `main` 分支。
5. 将 Main file path 设置为：`dashboard/app.py`。
6. 使用仓库根目录的 `requirements.txt` 安装依赖。
7. 点击 Deploy。

本项目不需要额外的 API Key、数据库或 Streamlit Secrets，数据文件已包含在仓库中。

## 推荐仓库信息

- Repository name: `superstore-sales-dashboard`
- Description: `Interactive Superstore sales and profit analytics dashboard built with Python, Plotly and Streamlit.`
- Topics: `data-analysis`, `data-visualization`, `python`, `plotly`, `streamlit`, `pandas`, `portfolio-project`

## 发布后检查

- GitHub 仓库首页能正确显示 README 和 Dashboard 截图。
- Streamlit 在线页面能加载 4 个 KPI 和全部图表。
- 把在线 Demo 链接补充到 README 顶部。
- 检查仓库没有提交 `.venv/`、`.streamlit/secrets.toml` 或个人信息。
