# bluearXiv-ai

自动抓取、分析 arXiv 特定领域论文，并生成日报（HTML + LaTeX）的系统。

这份文档按「从未配置过 GitHub Actions / GitHub Pages」来写，按步骤做即可。

## 1. 这个项目能做什么

- 自动抓取你关注学科在 arXiv 的最新论文。
- 先按关键词规则筛选精选（主关键词 + 附加关键词），再调用 AI 对精选论文做中文总结。
- 生成网页日报（docs 目录）和 LaTeX 文件（latest.tex）。
- 用 GitHub Actions 自动运行，并通过 GitHub Pages 展示网页结果。

## 2. 你最关心的几个问题（先看这个）

### 2.1 需要电脑一直开着吗？

不需要。

工作流在 GitHub 的云服务器运行，只要仓库在线即可。你本地电脑关机也会按计划执行。

### 2.2 怎么触发 GitHub Actions？

有两种方式：

- 定时触发：工作日每天 UTC 04:00 自动运行（北京时间约 12:00）。
- 手动触发：在仓库 Actions 页面点 Run workflow 即可。

### 2.3 怎么配置自己感兴趣的 arXiv 领域？

编辑两个文件：

- config/categories.txt：写学科代码（每行一个），如 math.AG。
- config/keywords.txt：写主关键词和附加关键词，用于判断是否精选。

### 2.4 API 在哪里配置？

在 GitHub 仓库 Secrets 配置，不写在代码里。

必配：

- DEEPSEEK_API_KEY

建议也配置（当前流程会传入环境变量，便于后续扩展）：

- MODEL_SCOPE_API_KEY

## 3. 第一次部署（完整步骤）

以下步骤只做一次。

### 3.1 准备仓库

1. 把项目推送到你自己的 GitHub 仓库。
2. 确认默认分支叫 main。
3. 确认仓库里有 .github/workflows/arxiv-daily-pipeline.yml。

如果你的默认分支不是 main，请改成 main，或自行调整工作流里 pull/push 的分支名。

### 3.2 开启 Actions 权限

1. 进入仓库页面。
2. 点击 Settings。
3. 左侧点击 Actions -> General。
4. 在 Actions permissions 中选择 Allow all actions and reusable workflows。
5. 在 Workflow permissions 中选择 Read and write permissions。
6. 勾选 Allow GitHub Actions to create and approve pull requests（可选但推荐）。
7. 点击 Save。

说明：此项目工作流需要提交生成文件回仓库，所以必须给写权限。

### 3.3 配置 API Secrets

1. 打开仓库 Settings。
2. 左侧点击 Secrets and variables -> Actions。
3. 在 Repository secrets 区域点击 New repository secret。
4. 新建以下 secret：
    - Name: DEEPSEEK_API_KEY，Value: 你的 DeepSeek Key。
    - Name: MODEL_SCOPE_API_KEY，Value: 你的 ModelScope Key（可先填占位值，也可填真实值）。
5. 保存。

注意：

- 不要把 API Key 写入代码文件。
- secret 名称必须完全一致，大小写也要一致。

### 3.4 配置你关注的 arXiv 学科

编辑 config/categories.txt，每行一个学科代码，例如：

math.AG
math.RT
math.QA
cs.LG
stat.ML

说明：

- 支持注释行（以 # 开头）和空行。
- 学科代码可在 arXiv 对应学科页面看到。

### 3.5 配置关键词（影响 AI 精选）

编辑 config/keywords.txt，使用“主关键词 + 附加关键词”格式，例如：

primary: agent
secondary: reliability
secondary: LLM
secondary: checkpoint

精选规则（当前代码行为）：

- 必须命中主关键词（primary）。
- 且至少命中一个附加关键词（secondary）。
- 只有同时满足上面两条，论文才会被标记为精选。

兼容说明：

- 旧格式仍可用：如果不写前缀，第一行会被视为主关键词，其余行视为附加关键词。
- 支持注释行（以 # 开头）和空行。

### 3.6 开启 GitHub Pages（发布网页）

1. 进入仓库 Settings。
2. 左侧点击 Pages。
3. 在 Build and deployment 里设置：
    - Source: Deploy from a branch
    - Branch: main
    - Folder: /docs
4. 点击 Save。
5. 等待 1 到 5 分钟，GitHub 会生成站点链接。

默认访问地址通常是：

https://你的用户名.github.io/你的仓库名/

例如仓库名是 bluearXiv-ai，则通常是：

https://你的用户名.github.io/bluearXiv-ai/

### 3.7 手动跑一次流程（首次验证）

1. 打开仓库的 Actions 页面。
2. 左侧选择 arXiv Daily Paper Pipeline (TeX + HTML)。
3. 点击 Run workflow。
4. 可选输入参数：
    - skip_fetch：false（首次建议 false）。
    - test_mode：false（首次建议 false）。
    - ai_model_name：deepseek-chat（默认）。
    - date：留空表示今天；也可填 YYYY-MM-DD 生成指定日期。
5. 点击绿色 Run workflow 按钮。

### 3.8 查看运行结果

运行成功后会发生：

- 仓库被自动更新：
  - latest.tex
  - docs/index.html
  - docs/daily_YYYY-MM-DD.html
  - data/raw 下的若干 JSON
- GitHub Pages 网页刷新可见新日报。

你可以在 Actions 单次运行页面看到：

- 每一步日志
- 工作流 summary 摘要
- 上传的 artifact 文件

## 4. 之后如何使用（每天自动跑）

你只需维护两件事：

1. categories.txt：你想追踪哪些学科。
2. keywords.txt：你认为什么方向更重要。

工作流会在工作日自动运行，无需人工值守。

如果要临时重跑某天数据：

1. Actions -> Run workflow。
2. date 填目标日期（YYYY-MM-DD）。
3. 点击运行。

## 5. 常见问题排查

### 5.1 Actions 运行失败，提示权限问题

检查：

- Settings -> Actions -> General -> Workflow permissions 是否为 Read and write。

### 5.2 提示缺少 API Key

检查：

- Settings -> Secrets and variables -> Actions 中是否存在 DEEPSEEK_API_KEY。
- 名称是否拼写完全一致。

### 5.3 Pages 打开 404

检查：

- Settings -> Pages 是否设置为 main 分支 + /docs 文件夹。
- docs/index.html 是否已生成并提交。
- 仓库名变化后，访问地址是否改为新仓库名。

### 5.4 手动运行没有新文件提交

可能原因：

- 当天抓取结果与已有结果一致。
- 某一步失败但工作流继续执行（该流程设置了 continue-on-error）。

建议：

- 打开 Actions 日志，逐步检查 fetch_paper_ids.py / ai_feedback.py / generate_html.py 输出。

## 6. 本地运行（可选，不影响云端自动化）

如果你想在本机先测试：

1. 安装 Python 3.10+。
2. 安装依赖：pip install -r requirements.txt。
3. 设置环境变量：
    - DEEPSEEK_API_KEY
    - MODEL_SCOPE_API_KEY
4. 依次执行：
    - python scripts/fetch_paper_ids.py
    - python scripts/ai_feedback.py
    - python scripts/category_filter.py
    - python scripts/generate_tex.py
    - python scripts/generate_html.py

本地运行仅用于测试。真正的“自动每天跑”依赖 GitHub Actions，不依赖你电脑开机。

## 7. 当前工作流行为说明（与代码一致）

- 定时规则：工作日 UTC 04:00。
- 手动参数：skip_fetch、test_mode、ai_model_name、date。
- 运行后会尝试把生成结果提交并推送到 main。
- Pages 展示内容来自 docs 目录。

如果你只按本文档配置一次，之后基本就是“改配置文件 + 看网页结果”的使用方式。
