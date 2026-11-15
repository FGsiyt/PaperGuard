# 开发记录

- [x] A：读取需求，检查现有工作区和 Python/Node 环境；在桌面建立独立目录。
- [x] B：Pydantic 模型、SQLite 快照与缓存、FastAPI、React/TypeScript 配置。
- [x] C：平衡括号扫描、注释与字面环境处理、递归 input/include、BibTeX 宏与拼接；Crossref/OpenAlex/arXiv 真实适配器；身份匹配与字段比较。
- [x] D：缺失 key、未引用条目、重复 key 与文献、空引用、定位及编译顺序降级。
- [x] E：OA 下载、HTTPS/IP 固定与逐跳 SSRF 防护、上传、PDF 身份匹配、原始矢量首页提取与书签合并。
- [x] F：可选兼容 LLM 服务、原文段落检索与页码、结构化判断和可验证引文，不可用时明确降级。
- [x] G：Web 工作台、CLI、HTML/XLSX/JSON/BibTeX、逐条确认、任务恢复、重试/取消、清理。
- [x] H：自动化测试、前端构建、Windows 脚本、文档与依赖许可清单。

验收证据单独维护在 docs/VALIDATION.md。在线 API 与实际 LLM 可用性不能由离线 fixture 替代；外部服务失败须如实记录。RIS、OCR、全文投稿 PDF 自动拆参考文献、多任务并发与复杂 TeX 宏解析作为后续扩展，未宣称已实现。
