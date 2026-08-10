# 法信通 LawTrust

可信法律智能问答与多维可信评估平台

## 架构

- **RAG**：LLM（本地 Qwen2.5-7B-Instruct / 阿里云百炼 qwen3.7-plus API 双模式）+ bge-base-zh-v1.5 + ChromaDB
- **法域核验**：三级引用核验 + 核验-重生成闭环
- **可信评估**：TrustLLM 六维框架本地化（`LegalTrustScorer`）
- **Web**：FastAPI + Vue3 + ECharts

## 快速开始

```bash
pip install -r requirements.txt

# 数据与向量库
python scripts/convert_md_to_json.py
python scripts/build_knowledge_base.py          # 完整库（只需 bge 嵌入模型，无需 GPU）
# python scripts/build_demo_knowledge_base.py   # 11 部法律，不含民法典
# python scripts/build_minimal_kb.py            # 最小测试库

# 命令行 Demo
python scripts/demo.py --query "劳动合同解除需要提前多少天通知？"

# Web 服务
python scripts/run_server.py
# 浏览器打开 http://localhost:6006/ （自动跳转演示页）
# 在输入框填写问题，可点击「上传文档」附加 txt/Word/PDF/图片；Ctrl+Enter 提交

# 一键启动（Windows，免敲命令）：双击 start_server.bat
# 一键内网穿透（让测试人员通过公网 URL 访问）：双击 start_tunnel.bat
# 测试人员零安装：只需浏览器 + 公网 URL + 账号 root/123456（详见 docs/测试人员运行指南.txt）

# 离线评测
python scripts/run_legal_trust_benchmark.py --mode full --mock
```

### 切换云端 API 模式（默认启用，无需 GPU）

LLM 默认走阿里云百炼 API（qwen3.7-plus，新模型各赠送 100 万 token 免费额度 / 90 天）：

1. 安装依赖后，复制 `.env.example` 为项目根目录 `.env`，填入你的 API Key：
   ```
   DASHSCOPE_API_KEY=sk-你的Key
   ```
   （Key 在阿里云百炼控制台 → API-KEY 管理获取；`.env` 已被 `.gitignore` 排除，不会入库。）
2. 完成。无需下载 Qwen2.5-7B 权重、无需 GPU（仅 bge 嵌入与 NLI 小模型，CPU 可跑）。
3. 切回本地推理（需 GPU + `models/Qwen2.5-7B-Instruct` 权重）：
   ```bash
   LLM_PROVIDER=local python scripts/demo.py --query "劳动合同解除需要提前多少天通知？"
   ```

## 目录

```
src/
  pipeline/answer_pipeline.py    # 统一问答流水线
  trust_eval/                    # 六维可信评分
  citation_verifier/             # 三级引用核验
  knowledge_base/                # 向量检索
  document_processing/           # 用户文档解析（txt/docx/pdf/OCR）
  llm/                           # Qwen 模型
web/
  backend/main.py                # FastAPI（auth/register/chat/user 数据接口）
  backend/user_store.py          # 用户注册表（哈希密码 + 每用户 API Key）
  backend/session_manager.py     # 服务端会话（Token TTL + JSON 持久化）
  backend/user_data.py           # 每用户数据（会话/收藏/资料）JSON 读写
  frontend/src/                  # Vite + Vue3 + TS 单页前端
data/
  raw/                           # 12 部法律 Markdown
  benchmark/                     # LegalTrustBench
  users/                         # 多用户数据（注册表/Token/会话收藏，不入库）
docs/competition/                # 竞赛材料
TrustLLM/                        # TrustLLM 参考实现（独立子项目）
```

## 竞赛材料

见 [docs/competition/README.md](docs/competition/README.md)
