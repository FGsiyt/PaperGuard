# 实际验收记录

最新发布前复测为后端 61 项、前端 3 项通过；全新源码安装和在线流程均已通过，详见 [RELEASE_CHECK.md](RELEASE_CHECK.md)。以下为首次开发验收记录。

验收日期：2026-11-11，Windows / Python 3.12.8 / Node 24.19.0。

- 自动化离线测试：57 passed，1 条第三方 Starlette TestClient 弃用提示；JUnit 结果在 test-results.xml。包括错误 DOI、标题差异、作者顺序、出版年份阶段、缺失 key、重复 key、递归文件、注释、宏、损坏/伪 PDF、SSRF/ZIP 校验、混合页面尺寸、取消/恢复、API、语义证据归属校验及原始文件保留。
- 前端：TypeScript 检查与 Vite 生产构建成功；npm install 审计返回 0 vulnerabilities。
- 真实联网：Crossref DOI 查询、OpenAlex DOI 查询、arXiv DOI 与标题查询均成功，原始查询时间和记录 ID 保存在任务 JSON 中。
- 端到端真实文献：Deep Residual Learning for Image Recognition，DOI 10.1109/CVPR.2016.90；verified，公开 PDF downloaded / confirmed，原始首页 1 页，合并 1 页，任务 completed。任务 ID：7add8ca997c54a9d。其源码顺序尚无编译产物确认，在报告明确提示。
- 原始 PDF 首页与汇总页：页面尺寸相同，内容流字节相同；Poppler 渲染的 PNG 字节和 SHA-256 相同。预览保存在 qa 目录。
- 本地服务：Windows Start.ps1 启动脚本已实际启动成功，首页和任务 API 均返回 HTTP 200，页面会话令牌已注入；写入 API 令牌、Origin 与 Host 防护由自动化测试验证。
- 界面可视点击验收未完成：Computer Use 因无法可靠识别 Windows 浏览器当前网址而自动停止。未绕过此限制，不能声称已完成浏览器交互实测。
- LLM：完成兼容服务调用、禁用/缺证据降级、引文和片段 ID 归属校验的 mock 测试；未配置真实 LLM，不声称已进行真实模型语义准确性验收。
- Linux/macOS：提供安装方式，未进行实机验证。RIS、OCR、投稿 PDF 自动重建参考文献、复杂自定义宏/分区文献编号均未实现。

所有核验数据为真实在线检索或明确隔离的合成测试 fixture；界面中保留一个真实示例任务，未填充虚构任务与统计数据。项目源码、文档、环境和示例结果保存在桌面 PaperGuard 文件夹，原 UAV 论文文件未修改。
