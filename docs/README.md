# PaperGuard 开发与接口说明

代码入口：`backend/paperguard/cli.py`、`api.py`。解析、匹配、PDF、语义审查、报告、SQLite 存储各自独立。React/TypeScript/Vite 前端通过本地 FastAPI API 工作。

## 数据与恢复

SQLite 文件：`data/paperguard.sqlite3`。tasks 表保存 Pydantic AuditTask JSON 快照；cache 表保存查询结果与原始检索时间。每处理完一条文献立即保存。中断后恢复跳过已处理条目；显式“重试此文献”重新处理该条，失败查询不会缓存。成功的查询默认缓存七天，可以清理。输入文件指纹变化后要求创建新任务，防止混用旧结论。已保存 PDF 合并前重新核对 SHA-256。任务串行执行，每个来源独立限速，arXiv 请求至少间隔 3.1 秒；429 和部分 5xx 指数退避，最长自动等待 30 秒，超过则明确记录失败。取消在当前文献处理结束后生效。

同一服务进程的任务串行队列与缓存避免重复请求；同时运行多个独立 CLI/服务进程不提供跨进程请求去重锁。清理缓存可用 Web 设置或 `paperguard clear-cache`；删除任务可用 Web 报告页。

## JSON 合约

`Verification_Records.json` 的 `schema_version` 为 `1.0`，结构为 AuditTask，额外提供 `summary`。模型定义见 `backend/paperguard/models.py`。机器可读 JSON Schema 见 `docs/audit.schema.json`。所有时间为 UTC ISO 8601，Web 转为浏览器本地时间。SourceRecord 具有 raw_metadata、normalized_metadata、source_record_id、retrieved_at、query_type、query_value、score、match_basis；queries 记录失败与缓存命中。原始响应保存于 JSON，可能较大。

真实性：verified / possible_match / metadata_mismatch / not_found / unverified / manual_review。not_found 仅表示已成功查询的来源没有匹配证据；任一必要来源失败且无匹配记录时采用 unverified。

PDF 获取：downloaded / user_uploaded / not_available / download_failed / needs_manual_review / not_attempted。规范中另述的 pdf_unavailable 在本实现统一映射为 not_available。PDF 身份：confirmed / probable / mismatch / needs_manual_review。probable 需要人工确认才能合并；mismatch 永不进入汇总。confirmed 基于首页的 DOI、标题、作者组合，仍需用户对重要结果复核。

## HTTP API

启动后访问 `/docs` 查看自动生成的 OpenAPI。`GET /api/tasks` 列表；`POST /api/tasks` 创建；`POST /api/import` 导入 `.bib` 或 ZIP；`GET /api/tasks/{id}` 详情；`POST .../cancel`、`.../resume`、`.../retry/{reference_id}`；`POST .../pdf/{reference_id}` 上传；`POST .../approve/{reference_id}/{pdf|correction}` 确认；`GET .../files` 和 `.../files/{name}` 导出；`DELETE /api/tasks/{id}` 清理任务。`GET/POST /api/settings` 设置，`DELETE /api/cache` 清缓存。

写入请求必须带启动时生成的 X-PaperGuard-Token；生产构建页面将自动注入。API 不启用 CORS，校验 Host 与 Origin，服务仅监听 loopback。本地应用面向单用户，不能作为带权限隔离的多用户服务器。API 调试请从本地页面的 meta[name=paperguard-token] 获取本次会话令牌；令牌随服务重启更新。

PDF 下载仅接受 OA 来源候选中的 HTTPS URL，逐跳校验公开地址、固定已验证 IP、限制端口、大小、重定向和页数，校验 PDF 魔数及解析结构。下载不会使用浏览器 Cookie 或绕过付费墙。ZIP 导入限制文件数、解压大小和压缩比，拒绝路径穿越和符号链接。

LLM base 是本地用户显式配置的可信服务地址，允许本机 Ollama/vLLM。密钥只通过环境变量读取，不经设置 API 返回。语义审查把引用上下文和检索到的全文片段作为不可信数据提交给模型。模型结果必须包含可验证的原文引文与片段 ID，否则降级 insufficient_evidence。未配置模型为 not_checked；没有匹配全文为 insufficient_evidence。

## 数据源与许可证

- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：DOI 精确查询及 bibliographic 标题查询；标准化出版日期阶段。
- [OpenAlex API](https://help.openalex.org/api/)：DOI/标题查询、开放获取位置、倒排摘要重建；可选 OPENALEX_API_KEY。
- [arXiv API](https://info.arxiv.org/help/api/user-manual.html)：DOI/标题查询，Atom 解析与合法公开 PDF 地址。

目前不含 Semantic Scholar、DBLP 和 Unpaywall 适配器。依赖选择 pypdf（BSD），未引入 PyMuPDF 的 AGPL 依赖。应用自有代码 Apache-2.0；Python 包许可证和前端许可证清单分别保存为 `docs/python-dependencies.json`、`docs/frontend-dependencies.json`，分发第三方依赖时保留其自身许可证。PDF 与来源摘要版权不属于本项目许可证授权范围。

## 贡献与测试

先运行离线测试，新增匹配规则需补充明确身份冲突的回归测试，禁止在测试预期中将无检索结果判成造假。离线 fixtures 均为标注的合成测试数据，不是实际学术检索记录。`scripts/online_smoke.py` 是独立在线验收，会调用真实服务并下载公开 PDF，不参与默认 pytest。

当前不提供云部署、RIS、OCR、从整篇投稿 PDF 自动重建参考文献、任意 TeX 宏执行、复杂 biblatex multicites/refsection 编号解析。`.aux` 只读取数值 bibcite 标签，`.bbl` 支持 bibitem 顺序，不执行 TeX、不自动编译。日期差异保留解释，年份不自动修正；作者缩写和期刊简称只作为辅助比较。扫描 PDF 无文本时需要外部 OCR。跨平台代码与安装步骤已提供，本次执行环境为 Windows，其他系统未实机验证。
