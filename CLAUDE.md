# CLAUDE.md — 法信通 LawTrust

面向中文法律场景的可信智能问答与多维可信评估平台：RAG 检索 + LLM 生成（本地 Qwen2.5-7B / 百炼 qwen3.7-plus API 双模式）+ 三级引用核验 + TrustLLM 六维可信评分 + 输入守卫，FastAPI 后端 + 单页 Web 前端。项目全貌详见 `docs/法信通_LawTrust_项目介绍.txt`。

## 项目结构

**权威来源**：`docs/法信通_LawTrust_项目介绍.txt` 第三节「项目整体结构」。
⚠️ 修改 / 新增 / 删除项目目录时，必须同步更新该文档（及 README.md），保持二者一致。以下为当前实际布局摘要：

```
LawTrust/                        # 项目根目录
├── src/                         # 核心业务代码
│   ├── config.py                # 全局配置（模型路径、阈值、权重、开关）
│   ├── llm/                     # LLM 封装（qwen_model 双模式 / api_client API 客户端 / RAG 上下文格式化）
│   ├── knowledge_base/          # 向量知识库（embedder / vector_store / law_name_resolver / law_validity）
│   ├── data_processing/         # 数据预处理（md→json、法条解析、分块、废止抽取）
│   ├── document_processing/     # 用户文档解析（txt/docx/pdf/图片 OCR）
│   ├── pipeline/                # 问答流水线（answer_pipeline / intent_router / query_rewriter）
│   ├── guardrails/              # 输入守卫、会话自动命名
│   ├── citation_verifier/       # 三级引用核验（显式 / 内容 / 隐性论断）
│   ├── trust_eval/              # 六维可信评估（legal_trust_scorer + dimensions + benchmark）
│   └── uncertainty/             # 不确定性评估（self_consistency；logits_entropy 为实验性模块）
├── web/
│   ├── backend/                 # FastAPI（main.py / verification_worker / ws_manager / task_registry）
│   └── frontend/index.html      # 单页前端（原生 HTML/JS + ECharts）
├── scripts/                     # 运维与演示脚本（run_server / build_knowledge_base / demo 等）
├── data/
│   ├── raw/                     # 法律 Markdown 原文
│   ├── processed/               # 结构化 JSON + law_repeals.json
│   ├── law_registry.json        # 废止法律注册表
│   └── benchmark/               # LegalTrustBench 测试集
├── models/                      # 本地模型权重（Qwen2.5-7B / bge-base-zh-v1.5 / Erlangshen-NLI）
├── law_db/                      # ChromaDB 持久化数据
├── docs/                        # 文档（项目介绍 / 竞赛改进方案 / 修改日志）
└── figure/                      # 图片素材（如签名图）
```

补充说明：根目录 `download.py`、`download_bge.py` 为模型权重下载脚本；`start_server.bat` / `start_tunnel.bat` 为 Windows 一键启动脚本（服务端一键启动 + 内网穿透，让测试人员通过公网 URL 零安装访问，详见 `docs/测试人员运行指南.txt`）。

## 运行环境

当前项目运行在 conda 虚拟环境 `LawTrust` 中，Python 解释器路径为 `C:\Users\75806\.conda\envs\LawTrust\python.exe`。运行项目脚本时，请优先使用该 conda 环境下的 Python，避免误用系统全局 Python 导致依赖缺失或版本不符。

## 常用命令

```bash
pip install -r requirements.txt                     # 安装依赖（API 模式无需 CUDA GPU）
# LLM 默认走百炼 API（qwen3.7-plus）：先把 DASHSCOPE_API_KEY 写入根目录 .env（参考 .env.example）
python scripts/convert_md_to_json.py                # 数据转换
python scripts/build_knowledge_base.py              # 构建完整向量库（另有 demo/minimal 版本；仅需 bge，无需 GPU）
python scripts/run_server.py                        # 启动 Web 服务（端口 6006）
# 一键启动（Windows）：双击 start_server.bat；内网穿透：双击 start_tunnel.bat
python scripts/demo.py --query "劳动合同解除需要提前多少天通知？"   # 命令行问答（API 模式）
LLM_PROVIDER=local python scripts/demo.py --query "…"              # 切回本地 7B 推理（需 GPU + models 权重）
python scripts/run_legal_trust_benchmark.py --mode full --mock   # 离线基准评测
```

浏览器访问 `http://localhost:6006`，测试账号 `root / 123456`（测试阶段固定账号，会话/收藏存于前端 localStorage）。

## 竞赛改进计划

**权威参考**：`docs/项目竞赛改进方案_分阶段实施指南.txt`（v2.0，共 12 个阶段，含代码示例、文件路径与验收标准）。实施改进时按该文档推进，每完成一个阶段更新下方进度表：

| 阶段 | 内容 | 状态 |
|---|---|---|
| 〇 | 基础修复（法律名识别、pyproject 化、sys.path 清理） | 未开始 |
| 一 | 流式输出优化（降级重试、资源释放、打字动画） | 未开始 |
| 二 | 问答缓存层（L1 精确 / L2 语义 / L3 嵌入） | 未开始 |
| 三 | 服务端会话管理（JSON 持久化 + Token TTL） | 未开始 |
| 四 | 效果对比框架（数据证明方案效果） | 未开始 |
| 五 | LangSmith 集成（行为追踪与 Token 统计） | 未开始 |
| 六 | 多用户并发 | 未开始 |
| 七 | 数据工程（RAG 与微调数据） | 未开始 |
| 八 | 架构升级（LLM 抽象层 + 多模型注册表 + 用户可控选择） | 主线已完成（7 模型切换/Auto/离线置灰）；8.4 任务编排（合同审查/时效查询管线）与 8.5 工具调用（2 工具+轨迹）已完成；8.6 统计暂缓 |
| 九 | 一键部署与团队测试（内网穿透） | 未开始 |

核心原则（摘自指南）：不追求全部完成，先保证已做阶段的数据扎实、演示流畅。

## 修改日志规则

**每次修改功能或修复 Bug 后，必须在 `docs/修改日志.txt` 中追加简要记录**，格式：

```
===== 2026-08-04 =====
类型：新增功能 / 修复 / 优化
内容：一句话说明改动
涉及文件：xxx.py, yyy.html
验证：说明验证方式（命令或操作步骤）
```

## 其他约定

- 配置中心：`src/config.py`（检索相关度阈值默认 0.35、可信权重、RAG/自一致性开关、LLM_PROVIDER 双模式切换等），改配置优先改这里。
- 多模型引擎（阶段八）：模型目录统一在 `src/llm/model_registry.py`（7 个模型，全部托管阿里云百炼、共用 `DASHSCOPE_API_KEY`；**新增模型 = 注册表加一行**，前端选择器自动出现）。前端发送框旁模型选择器：离线调用 / API 调用两级，API 下可选 Auto（跟随设置面板的全局默认模型，默认 qwen3.7-plus，`.env` 的 `DEFAULT_API_MODEL` 兜底）或具体模型；离线引擎需 CUDA GPU + 模型文件，未就绪自动置灰。模型选择按请求透传（`model_id` 参数沿 main.py → pipeline → model.generate → api_client 传递，并发不串模型），自一致性核验自动沿用所选模型。LLM 双模式仍保留：`LLM_PROVIDER="api"`（默认）走百炼；`"local"` 走本地 Qwen2.5-7B（fp16 约 14GB 显存，需 CUDA GPU）。API 模式下全项目仅需 bge/NLI 两个小模型，CPU 即可运行，无需 GPU。
- 运行依赖 GPU（仅本地模式）：Qwen2.5-7B 本地推理（fp16 约 14GB 显存），无 CUDA 时请使用 API 模式。
- 数据流链路：`data/raw` → `convert_md_to_json` → `data/processed` → `build_knowledge_base` → `law_db`。
- 代码风格：保持现有 Python + 中文注释、模块职责单一的风格。

## 使用者背景与协作约定

- 使用者为技术初学者：没有前后端开发基础，对大模型仅有初步概念，正在边做边学。
- 解释技术架构、技术原理或代码时，请使用通俗易懂的语言和类比，先讲清「它是什么、为什么需要」，再讲「怎么实现」；避免直接堆砌专业术语，必要处补充名词解释。
- 涉及代码或配置修改时，说明改动的原因与影响范围，帮助使用者逐步建立对项目全貌的理解。
