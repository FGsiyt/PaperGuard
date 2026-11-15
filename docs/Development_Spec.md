# PaperGuard v1.0 --- Codex 开发任务说明

> **项目名称：** PaperGuard\
> **项目定位：**
> 学术参考文献真实性、元数据准确性、引用完整性与引用合理性核验工具\
> **目标交付：** 一个可在 Windows、Linux、macOS
> 本地运行的完整开源项目，包含本地 Web
> 界面、命令行工具、学术元数据核验、论文 PDF
> 合法获取、首页提取与合并、审查报告和自动化测试。

------------------------------------------------------------------------

## 0. 给 Codex 的总指令

请将本文件作为 PaperGuard
项目的产品需求和开发验收依据，**直接在当前工作区完成项目开发**。

### 开发原则

1.  先检查当前工作区、已有代码、运行环境和依赖，不要未经检查就覆盖或删除现有文件。
2.  如果当前目录已有项目，先理解现有结构，再在合理基础上迭代；如果是空目录，则创建完整项目。
3.  不要只输出设计方案、伪代码或示例页面。需要实际创建代码、配置、测试、文档，并尽可能运行测试。
4.  不要把所有功能写成一个巨型文件。采用清晰、可测试、可扩展的模块化结构。
5.  不要为了"看起来完整"而伪造数据库结果、文献记录、PDF
    下载成功状态或引用核验结论。
6.  学术文献真实性必须由可追溯的学术数据源支持。LLM
    不能凭自身记忆断言某篇论文真实存在。
7.  外部服务不可用、API
    限流、网络失败或文献无法匹配时，应明确报告状态，不能静默忽略，也不能将"未检索到"直接判定为"虚假文献"。
8.  PDF
    下载仅使用合法、公开可访问或用户有权访问的来源。不得绕过出版社付费墙、登录限制、验证码或访问控制。
9.  原始 `.tex`、`.bib`、PDF
    文件不得被自动覆盖。所有修正必须生成新文件或以明确的用户确认操作应用。
10. 先完成可运行的端到端主流程，再完善边缘功能和
    UI。不要长期停留在架构设计阶段。
11. 任何无法在当前环境实现的功能，都要提供真实的降级行为、明确提示和文档说明，不得用假数据冒充已完成。
12. 重要功能必须有自动化测试。完成一个模块后立即运行相关测试，及时修复回归问题。

### 工作方式

请按以下顺序执行：

-   阶段 A：检查环境与工作区，输出简短实施计划。
-   阶段 B：搭建后端、前端、数据模型和配置。
-   阶段 C：完成 LaTeX/BibTeX 解析、文献检索和元数据核验。
-   阶段 D：完成正文引用完整性检测。
-   阶段 E：完成合法 PDF 获取、文献匹配、首页提取和合并。
-   阶段 F：完成引用上下文语义审查（可配置 LLM，无 LLM
    时系统仍可正常运行）。
-   阶段 G：完成 Web UI、CLI、报告导出、缓存和任务恢复。
-   阶段 H：运行测试、修复问题、完善 README、安装说明和 Windows
    启动脚本。

如果上下文或执行时间有限，优先确保主流程真实可用，不要用空实现代替核心功能。每个阶段结束时更新项目
TODO 或开发记录。

------------------------------------------------------------------------

# 1. 产品目标与用户工作流

PaperGuard
帮助科研人员检查论文参考文献是否真实存在、元数据是否准确、正文引用是否完整，以及引用是否真正支持对应论述；同时尽可能合法获取原始论文
PDF，提取每篇论文首页，按参考文献顺序合并为一个 PDF 文档。

## 1.1 主要输入

-   LaTeX 项目目录，包含主 `.tex` 文件及其 `\input`、`\include` 子文件。
-   单独的 `.bib` 文件。
-   用户提供的论文 PDF。
-   用户手动上传的单篇参考文献 PDF。
-   可选的 RIS、BibTeX 等参考文献交换格式。

第一优先级是完整支持 **LaTeX + BibTeX** 工作流。

## 1.2 主要输出

每次任务生成独立输出目录，建议结构如下：

``` text
PaperGuard_Output/
├── Reference_First_Pages.pdf
├── Reference_First_Pages_Indexed.pdf
├── Reference_Verification_Report.html
├── Reference_Metadata.xlsx
├── Corrected_References.bib
├── Verification_Records.json
├── Original_PDFs/
├── First_Pages/
├── Logs/
└── unresolved_references.csv
```

说明：

-   `Reference_First_Pages.pdf`：按原论文参考文献顺序合并的原始论文首页，不额外改写首页内容。
-   `Reference_First_Pages_Indexed.pdf`：可选索引版，可在每篇首页前增加独立目录页或在
    PDF 书签中写入编号和文献标题。不得改变原始首页内容。
-   `Reference_Verification_Report.html`：完整核验报告。
-   `Reference_Metadata.xlsx`：逐条文献的标准元数据、匹配结果、来源和
    PDF 状态。
-   `Corrected_References.bib`：根据已核实数据生成的建议修正版，不覆盖原文件。
-   `Verification_Records.json`：机器可读的完整审查记录。
-   未能获取、未能匹配或需要人工确认的条目必须单独列出。

------------------------------------------------------------------------

# 2. 功能需求

## 2.1 项目导入与解析

### LaTeX 项目解析

必须支持：

-   自动识别或由用户指定主 `.tex` 文件。
-   递归解析 `\input{}`、`\include{}`。
-   识别常见文献引用命令。
-   识别 `\bibliography{}`、`\addbibresource{}`。
-   识别
    `\cite{}`、`\citep{}`、`\citet{}`、`\parencite{}`、`\autocite{}`、`\textcite{}`、`\footcite{}`、`\nocite{}`
    等常见命令。
-   支持一个引用命令中包含多个 citation keys。
-   忽略注释中的伪引用。
-   尽量处理换行、空格、嵌套花括号和常见自定义宏。
-   记录每条引用的源文件、行号、原始文本和所属章节（能够识别时）。

不要仅依赖简单正则表达式处理所有 LaTeX。可以使用 LaTeX
parser，并针对引用命令实现稳健的扫描逻辑。对无法可靠解析的宏，应在报告中说明解析限制。

### BibTeX 解析

支持常见类型：

-   `@article`
-   `@inproceedings`
-   `@conference`
-   `@book`
-   `@inbook`
-   `@incollection`
-   `@phdthesis`
-   `@mastersthesis`
-   `@techreport`
-   `@misc`
-   `@online`

需要保留原始条目文本、key、字段、文件位置及解析错误。对于
`@string`、字符串拼接、宏引用等常见 BibTeX 特性，应尽可能正确解析。

支持多个 `.bib` 文件和 LaTeX 项目中引用的多个 bibliography resource。

## 2.2 学术文献真实性检索

建立独立的数据源适配器，至少实现以下数据源中可用且有文档支持的接口：

1.  Crossref API
2.  OpenAlex API
3.  Semantic Scholar API（遵守其 API key、速率限制及使用条款）
4.  arXiv API
5.  DBLP（适用于其覆盖范围内的计算机领域文献）

可根据实际接口可用性调整实现优先级，但必须保证至少有两个真实可用的数据源适配器，不能只写接口空壳。

### 检索策略

按可靠性分层：

1.  DOI 精确查询。
2.  标题精确或规范化匹配。
3.  标题模糊匹配。
4.  作者、年份、期刊/会议名称辅助匹配。
5.  必要时跨数据源交叉验证。

规范化时需要处理：

-   大小写差异。
-   Unicode 和重音字符。
-   标题标点差异。
-   LaTeX 转义。
-   HTML 实体。
-   连字符、冒号及空白差异。
-   作者姓名缩写与全名。
-   期刊名称缩写与全称。

不得仅因标题相似就自动认定为同一篇论文。匹配算法应结合
DOI、标题、作者、年份和出版物信息，并输出匹配依据。

### 真实性状态

统一定义以下状态：

-   `verified`：找到可靠记录，关键字段匹配。
-   `possible_match`：找到疑似记录，但匹配证据不足或存在字段差异。
-   `metadata_mismatch`：找到对应记录，但一个或多个关键元数据不一致。
-   `not_found`：在已查询的数据源中没有找到足够匹配的记录。
-   `unverified`：由于网络、API、权限、限流或数据源覆盖等原因无法完成验证。
-   `manual_review`：存在多个候选记录或冲突，需要人工确认。

**重要：`not_found` 不等于文献造假。**
报告必须显示实际查询过的数据源和检索时间。

### 数据源证据

每条文献记录必须保存：

-   数据源名称。
-   查询时间。
-   查询方式（DOI、标题或其他）。
-   数据源返回的记录 ID。
-   原始响应或可追溯的关键字段。
-   来源 URL（若有）。
-   匹配分数及匹配依据。
-   最终状态。

遵守各数据源的 API
使用条款、速率限制和署名要求。配置合理的超时、重试、退避和缓存。

## 2.3 元数据准确性核对

对比用户 BibTeX 与候选权威记录，至少核对：

-   title
-   author
-   year
-   journal / booktitle
-   volume
-   number
-   pages / article number
-   publisher
-   DOI
-   URL

每个字段分别记录：

-   原始值。
-   核验值。
-   比较状态。
-   差异说明。
-   数据来源。

字段状态建议：

-   `match`
-   `minor_difference`
-   `mismatch`
-   `missing_in_source`
-   `missing_in_input`
-   `not_comparable`

注意出版年份的特殊情况，例如 Early Access
年份与正式卷期年份可能不同。不要简单地把年份不同全部判为错误，应显示出版阶段和数据源差异。

## 2.4 BibTeX 自动修正

基于已核验的权威元数据生成 `Corrected_References.bib`。

要求：

-   原始 `.bib` 永远保留。
-   只自动修正有明确可靠证据的字段。
-   不确定字段保留原值，并在报告中说明。
-   保留原 citation key，避免破坏正文引用。
-   尽量保留原条目类型和用户自定义字段。
-   对无法匹配的条目不擅自重写。
-   输出修改前后 diff 或字段级修改记录。
-   支持用户在 Web UI 中逐条确认修改。

## 2.5 正文引用完整性

检查：

-   正文引用 key 在 BibTeX 中不存在。
-   BibTeX 中存在但正文没有引用的条目。
-   重复 citation key。
-   重复或疑似重复文献。
-   空引用、格式异常引用。
-   多个 BibTeX 文件之间的 key 冲突。
-   `\nocite{*}` 等特殊情况。
-   引用命令是否被注释。
-   章节、文件和行号。

对于引用编号顺序，不能仅凭源码中的 key
顺序判断最终编号。若需要验证最终编译编号，应将其作为可选增强功能，尝试读取
LaTeX `.aux`、`.bbl` 等编译产物；没有编译产物时明确说明无法确认。

## 2.6 引用内容合理性分析

这是 AI 功能，但必须以可追溯证据为基础。

### 分析流程

1.  从 LaTeX 中提取引用所在句子及前后上下文。
2.  确定被引用的文献记录。
3.  获取该论文的标题、摘要、关键词和可合法访问的全文。
4.  对全文进行解析，定位与引用论述最相关的段落。
5.  将引用论述、论文证据和必要上下文提交给配置的 LLM。
6.  输出带证据的判断。

### 判断标签

-   `supported`：现有证据直接支持该论述。
-   `partially_supported`：只支持论述中的部分内容。
-   `unsupported`：已检查的证据不支持该论述。
-   `contradicted`：证据与论述存在明显冲突。
-   `insufficient_evidence`：当前材料不足以判断。
-   `not_checked`：用户未启用语义检查或 LLM 不可用。

### 输出要求

每条语义审查结果包含：

-   引用位置。
-   正文原句及上下文。
-   论文标题和 DOI（若有）。
-   使用的原论文证据。
-   原文页码或章节（能够获取时）。
-   判断标签。
-   解释。
-   置信度。
-   局限说明。

禁止仅根据摘要缺少某个信息就断言原论文不支持该观点。没有全文或充分证据时，应选择
`insufficient_evidence`。

### LLM 抽象层

支持：

-   OpenAI 兼容 API。
-   Ollama。
-   vLLM。
-   用户自定义兼容服务。

LLM 配置必须可选。没有 API key
或模型服务时，基础文献核验、元数据比对、引用完整性和 PDF
处理仍应正常工作。

不要把 API key
写入代码、日志、前端构建文件或版本控制。使用环境变量或本地配置文件，并提供
`.env.example`。

## 2.7 论文 PDF 合法获取

### 来源优先级

优先从合法开放获取渠道获取：

-   arXiv。
-   OpenAlex 提供的 OA location。
-   Semantic Scholar 的开放获取 PDF 链接。
-   Unpaywall（如配置 email）。
-   其他明确允许公开访问的机构仓储或作者公开版本。
-   用户自行上传的 PDF。

### 合规边界

-   不绕过付费墙。
-   不绕过登录、验证码或访问控制。
-   不伪造浏览器身份规避限制。
-   不从来源不明的网站批量抓取受版权保护的全文。
-   保存 PDF 来源和许可/开放获取信息（数据源提供时）。
-   如果只能获取元数据而无法获取 PDF，应正常完成文献核验，并将 PDF
    状态标记为 `pdf_unavailable`。

### PDF 获取状态

-   `downloaded`
-   `user_uploaded`
-   `not_available`
-   `download_failed`
-   `needs_manual_review`
-   `not_attempted`

每次下载需要：

-   设置连接和读取超时。
-   检查 HTTP 状态。
-   检查 Content-Type，但不能仅依赖它。
-   检查文件头是否为有效 PDF。
-   检查文件大小和页数。
-   计算 SHA-256。
-   防止路径穿越和不安全文件名。
-   采用临时文件下载，验证成功后再原子移动。
-   对重复文件去重。
-   记录来源 URL、获取时间和文件校验值。

不要把 HTML 错误页保存为 PDF。

## 2.8 PDF 与目标文献匹配

下载或上传 PDF 后，必须尽可能核对其是否对应目标参考文献。

优先使用：

1.  PDF 内 DOI。
2.  PDF 首页标题。
3.  PDF 首页作者。
4.  出版物信息。
5.  可获取的 PDF 元数据。

可使用 PyMuPDF 提取文本和元数据，必要时对扫描件提示 OCR 不可用或提供可选
OCR 支持。

匹配结果：

-   `confirmed`
-   `probable`
-   `mismatch`
-   `needs_manual_review`

只有 `confirmed` 或经用户确认的 `probable`
文件才能进入最终首页汇总。`mismatch` 文件必须排除。

## 2.9 首页提取

对每篇已匹配 PDF：

-   提取原始 PDF 的第一页。
-   保留原始页面尺寸、方向、矢量内容和排版。
-   不通过截图重绘页面。
-   不把首页内容转换成重新排版的文本页。
-   每篇论文只提取第一页。
-   保存为独立 PDF。
-   文件名按参考文献序号命名，例如 `001_<safe_key>_first_page.pdf`。
-   记录原始 PDF 路径、页数、DOI、标题和匹配状态。

如果 PDF
为空、损坏、加密且无法处理或没有页面，应记录失败原因，不影响其他条目。

## 2.10 首页合并

生成 `Reference_First_Pages.pdf`：

-   按论文原始参考文献列表顺序排列。
-   每篇论文首页占一页。
-   直接合并原始首页 PDF 页面。
-   保留原始页面尺寸和内容。
-   不把缺失文献的占位页混入无索引原版。
-   生成缺失文献清单。
-   支持任务中断后继续。
-   重跑时复用校验通过的已有 PDF 和首页。
-   生成 PDF 书签（若库支持且不破坏页面）。

可选生成
`Reference_First_Pages_Indexed.pdf`。该版本可以在每篇首页前插入一张独立的索引页，或者添加
PDF 书签；不要在原始论文首页上覆盖编号、标签或水印。

必须在报告中明确： - 总参考文献数。 - 成功获取并核验 PDF 的数量。 -
成功提取首页的数量。 - 最终合并页数。 - 被跳过的文献及原因。

## 2.11 报告与 Excel 导出

### HTML 报告

包含：

-   任务摘要。
-   参考文献总数。
-   各真实性状态数量。
-   元数据不一致统计。
-   正文引用完整性问题。
-   引用合理性审查结果。
-   PDF 获取情况。
-   首页提取与合并情况。
-   每条文献详情。
-   数据来源与检索时间。
-   错误和待人工确认事项。

支持筛选、搜索、状态分类和展开详情。

### Excel 报告

建议工作表：

1.  `Summary`
2.  `References`
3.  `Metadata_Differences`
4.  `Citation_Issues`
5.  `Semantic_Audit`
6.  `PDF_Status`

### JSON

提供稳定、可文档化的 JSON schema，便于未来与其他工具集成。

------------------------------------------------------------------------

# 3. Web UI 与 CLI

## 3.1 本地 Web UI

提供本地 Web 界面，不需要部署云服务。

建议页面：

1.  Dashboard：任务总览和最近任务。
2.  New Audit：选择 LaTeX 项目、BibTeX 或 PDF。
3.  Reference List：逐条文献核验结果。
4.  Reference Detail：原始字段、标准字段、来源证据、PDF 状态和首页预览。
5.  Citation Audit：正文引用完整性与语义审查。
6.  PDF Archive：已下载 PDF、首页和合并文档。
7.  Reports：HTML、Excel、JSON、BibTeX 导出。
8.  Settings：API、LLM、缓存、输出目录和并发配置。

界面要求：

-   简洁、专业、适合科研人员。
-   状态和风险清晰可见。
-   支持长任务进度显示。
-   支持取消任务。
-   支持失败后重试。
-   支持查看每条文献的核验依据。
-   不显示虚构的统计数据。
-   不要求用户先配置 LLM 才能运行基础功能。

本地 Web 服务默认只监听 `127.0.0.1`，不要默认暴露到公网。

## 3.2 CLI

至少提供以下命令（命令名称可根据实际 CLI 设计调整，但功能必须覆盖）：

``` bash
# 初始化配置
paperguard init

# 检查 LaTeX 项目
paperguard audit ./my_paper

# 检查单个 BibTeX 文件
paperguard audit --bib ./references.bib

# 指定主文件
paperguard audit ./my_paper --main main.tex

# 启用引用语义审查
paperguard audit ./my_paper --semantic

# 生成或重新生成首页汇总
paperguard collect-pdf ./my_paper

# 生成报告
paperguard report --task <task_id> --format html

# 启动本地 Web UI
paperguard serve
```

提供合理的 `--help`、错误提示、退出码和日志。

------------------------------------------------------------------------

# 4. 推荐技术栈

根据实际兼容性选择稳定版本，并在 `pyproject.toml` 或前端 package
文件中锁定合理的依赖范围。

## 后端

-   Python 3.11+
-   FastAPI
-   Pydantic
-   SQLAlchemy（或轻量 SQLite 数据层）
-   SQLite
-   Typer
-   httpx
-   tenacity
-   PyMuPDF
-   pypdf
-   pylatexenc
-   bibtexparser
-   RapidFuzz
-   openpyxl
-   Jinja2
-   Pytest

## 前端

-   React
-   TypeScript
-   Vite
-   合适的组件库
-   PDF 预览组件（如使用 PDF.js）

不要为了追求技术栈丰富而引入不必要的微服务、消息队列或复杂基础设施。第一版以本地单机应用为主。

## 部署

-   Windows、Linux、macOS。
-   提供 Windows PowerShell 启动脚本。
-   提供 `.env.example`。
-   提供一键初始化或清晰的安装命令。
-   可选提供 Docker 部署，但不能把 Docker 设为唯一运行方式。

------------------------------------------------------------------------

# 5. 建议项目目录

请根据实际工程需要调整，但应保持职责清晰。

``` text
PaperGuard/
├── backend/
│   ├── paperguard/
│   │   ├── api/
│   │   ├── cli/
│   │   ├── core/
│   │   ├── parsers/
│   │   ├── sources/
│   │   │   ├── crossref.py
│   │   │   ├── openalex.py
│   │   │   ├── semantic_scholar.py
│   │   │   ├── arxiv.py
│   │   │   └── dblp.py
│   │   ├── verification/
│   │   ├── citation/
│   │   ├── llm/
│   │   ├── pdf/
│   │   ├── reporting/
│   │   ├── storage/
│   │   └── config/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── examples/
├── docs/
├── scripts/
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── CODEX_TASKS.md
```

------------------------------------------------------------------------

# 6. 核心数据模型

使用 Pydantic 定义并验证核心数据模型。模型至少包含以下概念。

## 6.1 Reference

建议字段：

-   `id`
-   `citation_key`
-   `entry_type`
-   `raw_bibtex`
-   `input_metadata`
-   `source_file`
-   `source_line`
-   `citation_locations`
-   `verification_status`
-   `metadata_fields`
-   `candidate_matches`
-   `selected_match`
-   `pdf_status`
-   `pdf_path`
-   `first_page_path`
-   `pdf_match_status`
-   `semantic_audit_status`
-   `created_at`
-   `updated_at`

## 6.2 SourceRecord

-   `source_name`
-   `source_record_id`
-   `query_type`
-   `query_value`
-   `source_url`
-   `retrieved_at`
-   `raw_metadata`
-   `normalized_metadata`

## 6.3 FieldComparison

-   `field_name`
-   `input_value`
-   `verified_value`
-   `comparison_status`
-   `difference_explanation`
-   `source_name`

## 6.4 CitationOccurrence

-   `citation_key`
-   `source_file`
-   `line_number`
-   `command`
-   `context_before`
-   `cited_text`
-   `context_after`
-   `section`

## 6.5 Finding

统一问题模型：

-   `id`
-   `rule_id`
-   `category`
-   `severity`
-   `status`
-   `message`
-   `evidence`
-   `source_location`
-   `suggestion`
-   `confidence`
-   `source`
-   `created_at`

## 6.6 AuditTask

-   `task_id`
-   `project_path`
-   `main_tex`
-   `bib_files`
-   `status`
-   `progress`
-   `current_stage`
-   `created_at`
-   `updated_at`
-   `output_path`
-   `error_summary`

所有状态使用枚举或受约束字符串，避免在不同模块中出现拼写不一致。

------------------------------------------------------------------------

# 7. 缓存、并发与恢复

必须考虑大量参考文献的情况。

-   使用 SQLite 缓存数据源查询结果。
-   DOI 和规范化标题可作为缓存检索键。
-   缓存需要记录数据源、检索时间和可配置过期时间。
-   支持对单条失败文献重试。
-   支持任务中断后恢复。
-   网络请求设置合理并发限制。
-   每个数据源单独控制速率。
-   避免同一 DOI 被多个任务重复请求。
-   PDF 下载和首页提取应采用任务队列或受控并发。
-   单条文献失败不能使整个任务失败。
-   任务完成后生成部分成功报告。

不要在 SQLite 中保存大体积 PDF
二进制内容，文件保存在本地目录，数据库只保存路径、校验值和元数据。

------------------------------------------------------------------------

# 8. 安全、隐私与版权要求

1.  默认本地运行，用户论文和文件不应自动上传到第三方。
2.  只有启用 LLM
    语义审查时，才将必要的引用上下文发送给配置的模型服务，并在 UI
    中明确提示。
3.  提供关闭外部 LLM 的选项。
4.  API key 通过环境变量或本地安全配置读取。
5.  不将密钥写入日志。
6.  不允许任意 URL 下载造成 SSRF；对下载
    URL、重定向、协议和目标地址进行安全校验。
7.  防止路径穿越、恶意文件名和压缩炸弹等文件处理风险。
8.  PDF 仅从合法开放获取渠道或用户授权上传来源获取。
9.  保存来源 URL 和可获得的许可信息。
10. 不绕过付费墙、登录、验证码或访问控制。
11. 提供清理任务文件和缓存的能力。
12. README 明确说明用户应遵守数据源条款和论文版权要求。

------------------------------------------------------------------------

# 9. 测试与验收标准

必须建立自动化测试，不允许仅凭手动打开界面判断完成。

## 9.1 测试数据

建立本地 fixture，至少覆盖：

-   正常 BibTeX 条目。
-   不存在的 DOI。
-   DOI 指向另一篇论文。
-   标题拼写错误。
-   作者顺序错误。
-   年份差异。
-   期刊名缩写与全称。
-   重复文献。
-   缺失 citation key。
-   未被引用的 BibTeX 条目。
-   多层 `\input` / `\include`。
-   注释中的伪引用。
-   一个 cite 命令包含多个 key。
-   损坏 PDF。
-   非 PDF 的 HTML 下载响应。
-   多页 PDF 首页提取。
-   页面尺寸不同的 PDF 合并。
-   下载失败后部分成功报告。
-   任务中断和恢复。

测试中不得依赖实时外部 API 才能通过。使用 mock/stub
验证逻辑，并另设可选的在线集成测试。

## 9.2 关键验收

### 文献核验

-   能通过 DOI 精确匹配真实记录。
-   能通过标题、作者、年份找到合理候选。
-   能发现 DOI 与标题不对应。
-   能逐字段展示元数据差异。
-   能区分未找到、未验证和字段不匹配。
-   能展示每条记录的数据来源和查询时间。

### 引用完整性

-   能解析多个 LaTeX 文件。
-   能识别正文引用缺失的 BibTeX key。
-   能识别未被引用的 BibTeX 条目。
-   能正确处理注释和多 key 引用。
-   能定位到文件和行号。

### PDF 归档

-   能从合法来源获取可访问 PDF。
-   能识别下载到的 HTML 错误页。
-   能核对 PDF 与目标文献的匹配情况。
-   能提取原始 PDF 第一页。
-   能按参考文献顺序合并首页。
-   能处理不同页面尺寸。
-   失败文献不影响其他文献。
-   最终报告准确列出缺失和失败项。

### 产品运行

-   Windows 环境可安装和启动。
-   本地 Web UI 可打开并执行完整任务。
-   CLI 可执行核心任务。
-   无 LLM 配置时基础功能仍然可用。
-   任务状态、错误信息和进度真实可靠。
-   所有关键模块有测试。

------------------------------------------------------------------------

# 10. README 与开源发布

完成后提供高质量 README，至少包含：

-   项目介绍。
-   功能清单。
-   系统架构。
-   环境要求。
-   Windows 安装方法。
-   Linux/macOS 安装方法。
-   API 配置。
-   LLM 配置。
-   CLI 使用示例。
-   Web UI 使用示例。
-   输出文件说明。
-   学术数据库来源说明。
-   PDF 获取和版权边界。
-   常见问题。
-   测试方法。
-   贡献指南。
-   License。

建议使用 Apache-2.0 许可证，但请先检查依赖许可证，确保项目分发方式兼容。

不要在 README 中声称尚未实现或未测试的功能已经可用。

------------------------------------------------------------------------

# 11. 最终交付清单

Codex 完成后必须给出以下交付结果：

-   [ ] 完整后端源代码。
-   [ ] 完整前端源代码。
-   [ ] 数据库模型和初始化逻辑。
-   [ ] 至少两个真实可用的学术数据源适配器。
-   [ ] LaTeX/BibTeX 解析与引用完整性检查。
-   [ ] 元数据匹配和差异报告。
-   [ ] BibTeX 修正版导出。
-   [ ] PDF 合法获取与用户上传。
-   [ ] PDF 与文献匹配核验。
-   [ ] 首页提取。
-   [ ] 首页合并 PDF。
-   [ ] HTML、Excel、JSON 报告。
-   [ ] 可选 LLM 语义引用审查。
-   [ ] 本地 Web UI。
-   [ ] CLI。
-   [ ] Windows 启动脚本。
-   [ ] `.env.example`。
-   [ ] 自动化测试。
-   [ ] README 和安装文档。
-   [ ] LICENSE。
-   [ ] 实际运行和测试结果。

最终请向用户报告：

1.  实际完成了哪些功能。
2.  哪些功能经过测试，测试结果如何。
3.  哪些功能受 API、网络、版权或环境限制尚未完成。
4.  如何在 Windows 上安装和启动。
5.  如何导入一篇 LaTeX 论文并生成首页汇总 PDF。
6.  输出文件保存在哪里。
7.  仍需用户配置哪些 API key（如有）。

**最终验收以真实可运行的端到端流程为准：导入 LaTeX/BibTeX → 核验文献 →
检查正文引用 → 获取可合法访问的论文 PDF → 核对 PDF 与文献 → 提取首页 →
按引用顺序合并 → 生成报告。**

不要以生成了项目目录、页面截图或 README 作为开发完成的依据。
