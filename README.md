# 律策智枢 LawPilot

面向中文法律场景的可信智能问答与多维可信评估平台：RAG 检索 + 多模型 LLM（阿里云百炼 API 7 款可选，可切换本地 Qwen2.5-7B 离线推理）+ 智能体任务编排与工具调用 + 三级引用核验 + TrustLLM 六维可信评分 + 多用户账号体系。FastAPI 后端 + Vue 3 单页 Web 前端。

## 架构

- **大模型引擎**：多模型注册表（`src/llm/model_registry.py`，7 款百炼模型：qwen3.7-plus / qwen-turbo / qwen3.7-max / deepseek-v4-flash-0731 / deepseek-v4-pro / kimi-k2.6 / glm-5.2；新增模型=注册表加一行），API 模式默认、无需 GPU；`LLM_PROVIDER=local` 切本地 Qwen2.5-7B（需 CUDA GPU，仅 CLI demo 支持）
- **RAG**：bge-base-zh-v1.5 + ChromaDB（`law_db/`）
- **智能体 Agent**：任务调度（法律问答 / 合同审查 / 法律时效查询）+ 工具调用循环（检索法条、查询时效，最多 3 轮）+ SSE 状态事件 + 工具轨迹面板 + 文档引文核验
- **法域核验**：三级引用核验（显式 / 内容 / 隐性论断）+ 核验-重生成闭环 + 法律时效注册表（`data/law_registry.json`）
- **可信评估**：TrustLLM 六维框架本地化（`LegalTrustScorer`），前端 ECharts 雷达图
- **多用户**：注册/登录、Token 24h 滑动过期、每用户 API Key 透传、每用户会话/收藏/资料 JSON 持久化（`data/users/`）+ 前端双写同步
- **Web**：FastAPI + Vite/Vue3/TS + Naive UI + Tailwind + ECharts

## 快速开始

```bash
pip install -r requirements.txt

# 配置 API Key（默认 API 模式，无需 GPU）
copy .env.example .env        # 填入 DASHSCOPE_API_KEY（阿里云百炼控制台获取）

# 数据与向量库
python scripts/convert_md_to_json.py
python scripts/build_knowledge_base.py          # 完整库（只需 bge 嵌入模型，无需 GPU）
# python scripts/build_demo_knowledge_base.py   # 演示库
# python scripts/build_minimal_kb.py            # 最小测试库

# 命令行 Demo（API 模式）
python scripts/demo.py --query "劳动合同解除需要提前多少天通知？"
# 本地 7B 推理（需 GPU + models/Qwen2.5-7B-Instruct 权重）
LLM_PROVIDER=local python scripts/demo.py --query "劳动合同解除需要提前多少天通知？"

# Web 服务
python scripts/run_server.py
# 浏览器打开 http://localhost:6006 → 登录（root / 123456；另有 user1/user2 同密码，可注册新账号）

# 一键启动（Windows）：双击 start_server.bat
# 内网穿透（测试人员公网访问）：双击 start_tunnel.bat（详见 docs/测试人员运行指南.txt）

# 离线评测
python scripts/run_legal_trust_benchmark.py --mode full --mock     # mock 离线
python scripts/run_legal_trust_benchmark.py --mode agent           # 智能体模式对比

# 单元测试
pytest tests/ -q
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/律策智枢_LawPilot_项目介绍.txt](docs/律策智枢_LawPilot_项目介绍.txt) | 整体技术架构、产品目标、重要模块、登录使用与环境配置 |
| [docs/律策智枢 LawPilot_Web端功能展示清单.txt](docs/律策智枢 LawPilot_Web端功能展示清单.txt) | Web 端全部功能与操作方法、详细测试用例（含测试数据说明） |
| [docs/测试人员运行指南.txt](docs/测试人员运行指南.txt) | 测试人员零安装访问指南 |
| [docs/修改日志.txt](docs/修改日志.txt) | 功能/修复变更记录 |
| [docs/智能体架构说明.txt](docs/智能体架构说明.txt) | 智能体任务调度与工具调用架构 |

测试用文档与图片（合同案例、借条、OCR 图片等）位于 `docs/测试文件/`。

## 目录

```
src/
  agents/                        # 智能体（任务调度 / 工具注册 / 工具循环 / 轨迹）
  pipeline/answer_pipeline.py    # 统一问答流水线（路由→重写→RAG→生成→核验→评分）
  trust_eval/                    # 六维可信评分
  citation_verifier/             # 三级引用核验 + 文档引文核验
  knowledge_base/                # 向量检索（bge + ChromaDB + 时效性）
  document_processing/           # 用户文档解析（txt/docx/pdf/OCR）
  llm/                           # 多模型注册表 / API 客户端 / 本地引擎门面
  guardrails/                    # 输入守卫（滥用拒答 / 脱敏 / 隐私确认）
web/
  backend/                       # FastAPI（auth/register/user/chat/stream/ws/models）
  frontend/src/                  # Vite + Vue3 + TS 单页前端
data/
  raw/                           # 法律 Markdown 原文
  benchmark/                     # LegalTrustBench（含 agent 对比题）
  users/                         # 多用户数据（注册表/Token/会话收藏，不入库）
tests/                           # pytest 单元测试（66 例）
docs/测试文件/                    # 功能测试用文档与图片
```

## 关键说明

- **账号体系**：种子账号 root/user1/user2（密码均 123456）；登录页可注册新账号；会话/收藏/资料存服务端并按账号隔离，Token 24h 滑动过期、多端共存、重启恢复。
- **每用户 API Key**：设置面板「模型与推理」区可自配百炼 Key（请求带 token 时后端自动透传），未配置回退服务端 `.env` Key（root 默认）。
- **配置中心**：`src/config.py`（检索相关度阈值默认 0.35、可信权重、RAG/自一致性/NLI 开关、智能体开关、TTL 等）；`.env` 的 `DASHSCOPE_API_KEY` / `DEFAULT_API_MODEL` 优先。
- **数据流链路**：`data/raw` → `convert_md_to_json` → `data/processed` → `build_knowledge_base` → `law_db`。
