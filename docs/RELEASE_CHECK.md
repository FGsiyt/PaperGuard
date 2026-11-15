# GitHub 发布前检查

日期：2026-11-11。结论：可以作为初版源码项目上传 GitHub；本次只准备本地文件，没有创建远程仓库或执行 push。

## 实际测试

| 项目 | 结果 |
| --- | --- |
| 后端自动化测试 | 61 passed；1 条第三方 TestClient 弃用提示 |
| 前端 React 交互测试 | 3 passed；覆盖空工作区、离线导入提交、弹窗内失败提示 |
| TypeScript 与生产构建 | 通过 |
| Python 锁定依赖 pip-audit | 32 项依赖，未发现已知漏洞 |
| npm audit（含新增测试依赖） | 0 known vulnerabilities |
| pip check | 无依赖冲突 |
| Git 发布文件与常见密钥/私人绝对路径扫描 | 通过 |
| 纯源码 ZIP 全新目录安装 | Windows Setup.ps1 成功，重新建立虚拟环境、npm ci、前端构建与本地配置 |
| 全新安装后的后端/前端测试 | 61 + 3 再次通过 |
| 全新安装后的真实在线流程 | Crossref/OpenAlex/arXiv 查询均成功；ResNet 记录 verified，PDF downloaded/confirmed，合并首页 1 页，任务 completed |
| 全新安装后的 Start.ps1 | 本地首页与任务 API 返回 HTTP 200，会话令牌正确注入 |

## 本次修复

- 修正跨来源判断：一个来源缺少 DOI 但标题、作者和年份一致时，不再误报冲突；相同 DOI 对应的来源标题明显冲突时要求人工复核。
- 修正不存在文献 ID 的重试/确认请求，明确返回 HTTP 404。
- 导入失败原因现在在仍打开的导入弹窗内部可见。
- 从 Git 排除本地论文首页预览、用户配置、任务数据库、依赖、构建产物和发布压缩包。
- 修改 README 的首次安装流程，增加约束版本安装、Node 版本提示、NOTICE、CONTRIBUTING、SECURITY、源码发布检查脚本与 GitHub Actions CI。

## 发布范围

仓库只包含源代码、测试、通用文献 BibTeX 示例、依赖锁文件、许可证和文档。不包含 .env、.venv、node_modules、data、任何论文 PDF 或提取的页面图片。`scripts/check_release.py` 检查 Git 将提交的文件；也支持在无 .git 的源码 ZIP 中检查。

已初始化 main 分支，并准备源码发布包 `release/PaperGuard-source.zip`。上传 GitHub 时应提交解压后的源码文件，或从当前本地 Git 仓库推送源码；仅把 ZIP 放入空仓库不会展示源码，也不会触发根目录中的 CI。

## 仍需保留的说明

- GitHub Actions 工作流已经配置 Windows/Linux/macOS 与 Python 3.11/3.12 后端矩阵，以及 Node 24 前端测试，但远程 CI 尚未执行；上传后以实际 Actions 结果为准。本机实测为 Windows / Python 3.12 / Node 24。
- 没有真实 LLM 服务配置，语义审查只完成禁用/缺证据降级和 mock 调用及证据归属验证；未作真实模型准确性验收。
- Windows 浏览器自动化此前因无法可靠识别当前网址而停止；本轮新增的前端交互测试使用 jsdom，不能替代完整的真实浏览器端到端测试。
- 当前不支持 OCR、RIS、投稿 PDF 自动重建参考文献、复杂自定义宏与分区文献编号。
- 支持从源码安装；单独的后端 wheel 不包含完整 React 应用，尚不是推荐的桌面分发方式。
- 漏洞审计是本次数据库查询结果，不是未来持续安全或不存在未知漏洞的保证。

以上限制已写入文档，不影响将当前初版源码放入 GitHub 供使用和继续开发。
