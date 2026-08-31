# 智能体（Agent）功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为律策智枢 LawPilot实现任务编排式多智能体（合同审查 / 时效查询专用管线）与工具调用式智能体（检索法条 / 查询时效 2 个工具，循环上限 3 轮），形成「可信智能体」答辩叙事。

**Architecture:** 新增 `src/agents/` 智能体层——任务调度器在现有意图路由之上细分任务类型（法律问答 / 合同审查 / 时效查询，回退安全）；工具调用引擎（ReAct 简化版）挂在法律问答管线上，模型自主决定是否调用工具；所有法律类最终回答仍走引用核验 + 六维评分闭环。SSE 新增 `agent_status` 事件类型（向后兼容），前端展示生成中状态与工具轨迹。

**Tech Stack:** Python 3（FastAPI + pydantic）、Vue 3 + TypeScript（Naive UI + Tailwind）、OpenAI 兼容 API（阿里云百炼 function calling）、pytest。

## Global Constraints

- Python 解释器：conda 环境 `LawTrust`，路径 `C:\Users\75806\.conda\envs\LawTrust\python.exe`（所有 `python` 命令用它，勿用系统 Python）。
- 测试：pytest（`tests/` 目录，`tests/conftest.py` 已把项目根加入 sys.path）；运行 `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/ -q`，全绿为准。
- 前端构建：在 `web/frontend` 下 `npm run build`，vue-tsc 零类型错误；dist 产物被服务端 StaticFiles 实时读盘（前端改动无需重启后端，后端代码改动需重启）。
- 后端启动：`python scripts/run_server.py`（端口 6006，测试账号 root/123456）；真实 LLM 验证走百炼 API（根目录 `.env` 需有 `DASHSCOPE_API_KEY`）。
- 新增代码保持现有风格：中文注释、模块职责单一；新增配置一律进 `src/config.py`。
- 不新增第三方依赖（工具调用用现有 `openai` SDK 的 tools 参数）。
- 每次改动完成后在 `docs/修改日志.txt` 追加记录（格式见 CLAUDE.md）；`docs/项目介绍` / `CLAUDE.md` 的目录与进度表需同步。
- 设计文档：`docs/superpowers/specs/2026-08-10-agent-features-design.md`（本计划的唯一权威依据；如与计划冲突，以设计文档为准并回查）。

---

### Task 1: 配置项 + 模型层工具契约（数据类与抽象方法）

**Files:**
- Modify: `src/config.py`（Config 类末尾追加智能体配置段）
- Modify: `src/llm/base.py`（ToolCall / ToolDecision 数据类 + 三个抽象方法）
- Test: `tests/test_model_tool_contract.py`（新增）

**Interfaces:**
- Consumes: 无（本任务定义契约本身）。
- Produces:
  - `Config.AGENT_ENABLE_TOOLS: bool = True`
  - `Config.AGENT_MAX_TOOL_ROUNDS: int = 3`
  - `Config.AGENT_DECISION_MAX_TOKENS: int = 512`
  - `Config.AGENT_TOOL_ARG_MAX_LEN: int = 100`
  - `src.llm.base.ToolCall(id: str, name: str, arguments: Dict[str, Any])`，含 `to_dict()`
  - `src.llm.base.ToolDecision(text: str, tool_calls: List[ToolCall] = field(default_factory=list))`
  - `BaseLLMModel.complete_with_tools(messages, tools, model_id=None, max_tokens=512) -> ToolDecision`（抽象；本地引擎抛 `NotImplementedError`）
  - `BaseLLMModel.complete_stream_with_tools(messages, tools, model_id=None, max_tokens=512) -> Generator[Tuple[str, Any], None, None]`（yield `("text", str)` 文本块；若流内含工具调用，结束前再 yield `("tool_calls", List[ToolCall])`；本地引擎抛 `NotImplementedError`）
  - `BaseLLMModel.generate_stream_messages(messages, model_id=None, temperature=None, max_new_tokens=None) -> Generator[str, None, None]`（按原始 messages 流式生成）

- [ ] **Step 1: 写失败测试**

`tests/test_model_tool_contract.py`：

```python
"""模型层工具契约单测：ToolCall / ToolDecision 数据类行为。"""
from src.llm.base import ToolCall, ToolDecision


def test_tool_call_to_dict():
    tc = ToolCall(id="call_1", name="search_articles", arguments={"query": "工伤认定"})
    assert tc.to_dict() == {
        "id": "call_1",
        "name": "search_articles",
        "arguments": {"query": "工伤认定"},
    }


def test_tool_decision_default_no_calls():
    d = ToolDecision(text="回答")
    assert d.text == "回答"
    assert d.tool_calls == []


def test_tool_decision_with_calls():
    d = ToolDecision(text="", tool_calls=[ToolCall("c1", "search_articles", {})])
    assert len(d.tool_calls) == 1
    assert d.tool_calls[0].name == "search_articles"
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_model_tool_contract.py -q`
Expected: 失败（ModuleNotFoundError / ImportError：`src.llm.base` 无 ToolCall）。

- [ ] **Step 3: 实现配置与数据类**

`src/config.py`，在 `# Self-consistency settings` 段之后追加：

```python
    # ---- 智能体（Agent）----
    AGENT_ENABLE_TOOLS = True            # 法律问答管线的工具调用开关（仅 API 引擎生效）
    AGENT_MAX_TOOL_ROUNDS = 3            # 单次回答最大工具调用轮次（防死循环）
    AGENT_DECISION_MAX_TOKENS = 512      # 每轮工具决策的最大生成 token
    AGENT_TOOL_ARG_MAX_LEN = 100         # 工具参数长度上限（清洗）
```

`src/llm/base.py`，改头部 import 并追加数据类：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple


@dataclass
class ToolCall:
    """模型决定调用的一次工具调用（参数已解析为 Python 对象）。"""

    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class ToolDecision:
    """一次工具决策的结果：要么给出文本（无工具调用），要么给出工具调用列表。"""

    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
```

`BaseLLMModel` 类体内（`generate_stream` 之后）追加三个抽象方法：

```python
    @abstractmethod
    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> ToolDecision:
        """非流式工具决策：模型返回文本（无工具调用）或工具调用列表。

        本地引擎不支持函数调用 → 抛 NotImplementedError（调用方降级为普通生成）。
        """

    @abstractmethod
    def complete_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> Generator[Tuple[str, Any], None, None]:
        """流式工具决策：yield ("text", str) 文本块；流结束若带工具调用，
        则作为本轮 ("tool_calls", List[ToolCall]) 事件（在文本块之后 yield）。
        本地引擎不支持函数调用 → 抛 NotImplementedError。
        """

    @abstractmethod
    def generate_stream_messages(
        self,
        messages: List[Dict[str, str]],
        model_id: Optional[str] = None,
        temperature: float = None,
        max_new_tokens: int = None,
    ) -> Generator[str, None, None]:
        """按原始消息列表流式生成（工具对话历史已在 messages 中），逐段 yield 文本。"""
```

- [ ] **Step 4: 运行确认通过**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_model_tool_contract.py -q`
Expected: 3 passed。

- [ ] **Step 5: 提交**

```bash
git add src/config.py src/llm/base.py tests/test_model_tool_contract.py
git commit -m "feat: 智能体配置项与模型层工具契约（ToolCall/ToolDecision + 三个抽象方法）"
```

---

### Task 2: 任务调度器（task_scheduler.py）

**Files:**
- Create: `src/agents/__init__.py`、`src/agents/task_scheduler.py`
- Test: `tests/test_task_scheduler.py`（新增）

**Interfaces:**
- Consumes: `src.pipeline.intent_router.IntentResult`、`Config.LAW_REGISTRY_PATH`。
- Produces:
  - `src.agents.task_scheduler.TaskDecision(task_type: str, confidence: float, reason: str, law_name: Optional[str] = None)`，含 `to_dict()`
  - `classify_task(query: str, intent: IntentResult, user_documents: Optional[List[Dict]] = None, registry_path: Optional[str] = None) -> TaskDecision`
    - `task_type` 取值：`legal_qa`（默认兜底）| `contract_review` | `validity_check`

- [ ] **Step 1: 写失败测试**

`tests/test_task_scheduler.py`：

```python
"""任务调度器单测：时效查询 / 合同审查 / 兜底回退。"""
import json
import tempfile
from pathlib import Path

from src.pipeline.intent_router import IntentResult, classify_intent
from src.agents.task_scheduler import classify_task

_DOCS = [
    {"filename": "劳动合同.txt", "text": "甲方乙方试用期约定条款……", "format": "txt", "char_count": 20}
]


def _legal_intent(q: str) -> IntentResult:
    return classify_intent(q)


def test_validity_repealed_law_query():
    assert classify_task("婚姻法现在还有效吗？", _legal_intent("婚姻法现在还有效吗？")).task_type == "validity_check"


def test_validity_repeal_wording():
    assert classify_task("合同法废止了吗？", _legal_intent("合同法废止了吗？")).task_type == "validity_check"


def test_validity_not_detected_without_time_wording():
    """提及废止法律但无时效措辞 → 不判时效查询（如咨询具体规定）"""
    assert classify_task("婚姻法对离婚财产分割怎么规定？", _legal_intent("婚姻法对离婚财产分割怎么规定？")).task_type == "legal_qa"


def test_contract_review_with_documents():
    t = classify_task("这份合同有什么风险条款？", _legal_intent("这份合同有什么风险条款？"), _DOCS)
    assert t.task_type == "contract_review"


def test_contract_review_guidance_without_documents():
    t = classify_task("帮我审一下这份合同", _legal_intent("帮我审一下这份合同"), None)
    assert t.task_type == "contract_review"
    assert t.confidence >= 0.8


def test_contract_keyword_fallback_without_docs():
    """「合同到期不续签怎么办」含合同但无审查信号 → 默认法律问答"""
    assert classify_task("合同到期不续签怎么办？", _legal_intent("合同到期不续签怎么办？")).task_type == "legal_qa"


def test_registry_driven_law_names():
    """时效法律名动态取自注册表：把临时注册表写入「专利法」验证不硬编码。"""
    with tempfile.TemporaryDirectory() as d:
        reg = Path(d) / "law_registry.json"
        reg.write_text(json.dumps({"专利法": {"status": "repealed", "repeal_date": "2009-10-01", "superseded_by": "专利法(2008修订)"}}, ensure_ascii=False), encoding="utf-8")
        t = classify_task("专利法还有效吗？", _legal_intent("专利法还有效吗？"), None, registry_path=str(reg))
        assert t.task_type == "validity_check"
        assert t.law_name == "专利法"


def test_default_fallback():
    assert classify_task("劳动仲裁怎么申请？", _legal_intent("劳动仲裁怎么申请？")).task_type == "legal_qa"
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_task_scheduler.py -q`
Expected: 失败（ModuleNotFoundError：src.agents.task_scheduler）。

- [ ] **Step 3: 实现调度器**

创建 `src/agents/__init__.py`（空文件），创建 `src/agents/task_scheduler.py`：

```python
"""任务调度器：把 legal_qa 意图细分为任务类型，分派到专业管线（主管-专家）。

设计要点：
- 确定性规则分类（不用大模型）：快、稳、便宜、可解释；
- 回退安全：规则不命中一律落回 legal_qa（最坏情况 = 现状，不退化）；
- 时效查询的法律名动态取自 law_registry.json（不硬编码废止法律清单）。
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Config
from src.pipeline.intent_router import IntentResult

# 合同审查提问信号（与「是否携带文档」组合判断）
_CONTRACT_REVIEW_RE = re.compile(r"审查|风险|条款|把关|漏洞|合规|审一下|帮我审|帮忙审|这份合同|这份协议|(合同|协议).*(风险|审查|条款|问题)")
# 无文档时的强个人审查意图（此时输出引导上传）
_CONTRACT_REVIEW_NO_DOC_RE = re.compile(r"帮我审|审一下|帮忙审|看看.*(合同|协议)|(合同|协议).*(审查|风险|条款)")
# 时效查询提问信号
_VALIDITY_QUERY_RE = re.compile(r"还有效|有效吗|是否有效|废止|作废|失效|还有没有效|现在.*适用|替代|新法|生效")


@dataclass
class TaskDecision:
    task_type: str   # legal_qa | contract_review | validity_check
    confidence: float
    reason: str
    law_name: Optional[str] = None  # validity_check 命中的注册表法律名

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "confidence": self.confidence,
            "reason": self.reason,
            "law_name": self.law_name,
        }


def _load_registry_names(registry_path: str) -> List[str]:
    """读取注册表键（废止/修订法律名）；文件缺失或损坏返回空表（调度器照常工作）。"""
    p = Path(registry_path)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")).keys())
    except Exception:
        return []


def classify_task(
    query: str,
    intent: IntentResult,
    user_documents: Optional[List[Dict]] = None,
    registry_path: Optional[str] = None,
) -> TaskDecision:
    """任务分类：仅在 intent == legal_qa 时细化；其他意图不会被调用。"""
    text = (query or "").strip()
    docs = user_documents or []

    # 时效查询：问题点名废止法律 + 时效措辞
    names = _load_registry_names(registry_path or str(Config.LAW_REGISTRY_PATH))
    if names and _VALIDITY_QUERY_RE.search(text):
        mentioned = [n for n in names if n in text]
        if mentioned:
            return TaskDecision(
                "validity_check", 0.9,
                f"时效查询：提及废止法律《{mentioned[0]}》",
                law_name=mentioned[0],
            )

    # 合同审查：携带文档 + 审查信号
    if docs and _CONTRACT_REVIEW_RE.search(text):
        return TaskDecision("contract_review", 0.85, "携带文档且提问含合同审查信号")

    # 合同审查（无文档）：强个人审查意图 → 输出引导上传
    if _CONTRACT_REVIEW_NO_DOC_RE.search(text):
        return TaskDecision("contract_review", 0.8, "合同审查意图（无文档，输出引导）")

    return TaskDecision("legal_qa", 0.6, "默认法律问答")
```

- [ ] **Step 4: 运行确认通过**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_task_scheduler.py -q`
Expected: 8 passed（注意 `test_validity_repealed_law_query` 依赖真实 `data/law_registry.json` 含「婚姻法」——该文件已存在）。

- [ ] **Step 5: 提交**

```bash
git add src/agents/ tests/test_task_scheduler.py
git commit -m "feat: 任务调度器（时效查询/合同审查/兜底回退，注册表驱动法律名）"
```

---

### Task 3: 时效查询管线（确定性证据 + 专用提示词 + 流水线分支）

**Files:**
- Modify: `src/knowledge_base/law_validity.py`（追加 `build_validity_evidence` 函数）
- Modify: `src/llm/qwen_model.py`（`_SYSTEM_PROMPT_VALIDITY` + `get_system_prompt` 分支）
- Modify: `src/pipeline/answer_pipeline.py`（`PipelineContext` 新字段 + `classify_task` 接入 + `_run_validity`）
- Test: `tests/test_validity_evidence.py`（新增）、`tests/test_qwen_prompts.py`（追加用例）

**Interfaces:**
- Consumes: `classify_task`（Task 2）、`LawValidityService`（已有）。
- Produces:
  - `src.knowledge_base.law_validity.build_validity_evidence(law_name: str, validity: LawValidityService) -> Dict`（键：law_name / effective / status / repeal_date / superseded_by / text）
  - `get_system_prompt("validity_check")` 返回时效专用提示词
  - `PipelineContext` 新增字段：`task: Optional[TaskDecision] = None`、`validity_evidence: Optional[Dict] = None`（dataclass 默认值追加，向后兼容）

- [ ] **Step 1: 写失败测试**

`tests/test_validity_evidence.py`：

```python
"""时效证据构造单测：确定性结论来自注册表。"""
import json
import tempfile
from pathlib import Path

from src.knowledge_base.law_validity import LawValidityService, build_validity_evidence


def _service_with(registry: dict) -> LawValidityService:
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "law_registry.json"
    p.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return LawValidityService(registry_path=str(p))


def test_repealed_evidence():
    svc = _service_with({
        "婚姻法": {"status": "repealed", "repeal_date": "2021-01-01", "superseded_by": "民法典"},
    })
    ev = build_validity_evidence("婚姻法", svc)
    assert ev["effective"] is False
    assert ev["repeal_date"] == "2021-01-01"
    assert ev["superseded_by"] == "民法典"
    assert "2021-01-01" in ev["text"] and "民法典" in ev["text"]


def test_effective_evidence():
    svc = _service_with({})
    ev = build_validity_evidence("劳动合同法", svc)
    assert ev["effective"] is True
    assert "现行有效" in ev["text"]
```

`tests/test_qwen_prompts.py` 追加（文件末尾）：

```python
def test_validity_prompt():
    """时效查询提示词：以注册表为准、不套三段式"""
    p = get_system_prompt("validity_check")
    assert "注册表" in p and _MANDATORY_TEMPLATE not in p
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_validity_evidence.py tests/test_qwen_prompts.py -q`
Expected: 新用例失败（AttributeError / ImportError）。

- [ ] **Step 3: 实现证据构造与提示词**

`src/knowledge_base/law_validity.py` 文件末尾追加：

```python
def build_validity_evidence(law_name: str, validity: "LawValidityService") -> Dict:
    """构造时效查询的确定性证据块（供模型润色 + 前端溯源展示）。

    核心事实（废止日期、替代法律）只来自注册表，模型不得编造。
    """
    result = validity.check_citation(law_name, "")
    if result.effective:
        return {
            "law_name": law_name,
            "effective": True,
            "status": "effective",
            "text": f"《{law_name}》现行有效。",
        }
    msg = f"《{law_name}》已废止"
    if result.repeal_date:
        msg += f"（{result.repeal_date}）"
    if result.superseded_by:
        msg += f"，替代法律：《{result.superseded_by}》"
    return {
        "law_name": law_name,
        "effective": False,
        "status": result.status,
        "repeal_date": result.repeal_date,
        "superseded_by": result.superseded_by,
        "text": msg,
    }
```

`src/llm/qwen_model.py`：在 `_SYSTEM_PROMPT_DOC_ANALYSIS` 之后追加：

```python
_SYSTEM_PROMPT_VALIDITY = """你是律策智枢 LawPilot智能助手。用户询问某部法律的时效状态（是否有效/已废止）。

回答要求：
- 核心结论必须以「法律时效注册表」提供的事实为准（废止日期、替代法律），
  不得编造、不得推测废止时间；
- 用自然语言组织结论（如：《婚姻法》已于2021年1月1日废止，相关内容由《中华人民共和国民法典》吸收），
  并补充一句实务提示（如相关事项现按民法典相应编章处理）；
- 不引用法条原文，不使用【结论】【法律分析】【依据法条】三段式结构；
- 若注册表未收录该法律，如实说明。"""
```

`get_system_prompt` 函数体内追加分支（`document_mode` 判断之后）：

```python
    if intent == "validity_check":
        return _SYSTEM_PROMPT_VALIDITY
```

- [ ] **Step 4: 接入流水线（prepare_context + run + run_fast）**

`src/pipeline/answer_pipeline.py`：

1) 顶部 import 追加：

```python
from src.agents.task_scheduler import TaskDecision, classify_task
from src.knowledge_base.law_validity import LawValidityService, build_validity_evidence
```

2) `PipelineContext` dataclass 追加两个字段（末尾）：

```python
    # 任务调度结果（合同审查 / 时效查询 / 默认法律问答）
    task: Optional[TaskDecision] = None
    # 时效查询的确定性证据（任务类型为 validity_check 时非空）
    validity_evidence: Optional[Dict] = None
```

3) `prepare_context`：在 greeting/general 两个分支之后（legal 分支开头）插入任务分类与时效快路径：

```python
        task = classify_task(query, intent, user_documents)

        # 时效查询快路径：直查注册表 → 确定性证据 + 模型润色（不检索、不核验）
        if task.task_type == "validity_check":
            validity = self.verifier.validity if self.verifier else LawValidityService()
            evidence = build_validity_evidence(task.law_name, validity)
            return PipelineContext(
                query=query,
                intent=intent,
                task=task,
                history=history,
                use_rag=False,
                system_prompt=get_system_prompt("validity_check"),
                generation_query=query,
                context_docs=[evidence["text"]],
                validity_evidence=evidence,
                user_documents=user_documents,
                model_id=model_id,
            )
```

4) legal 分支的 `return PipelineContext(...)` 中补 `task=task`，并把 system_prompt 改为按任务选择：

```python
        return PipelineContext(
            query=query,
            intent=intent,
            task=task,
            ...
            system_prompt=get_system_prompt(
                "contract_review" if task.task_type == "contract_review" else "legal_qa"
            ),
            ...
        )
```

5) `run_fast` 的 meta 字典追加：

```python
        meta = {
            ...
            "task": ctx.task.to_dict() if ctx.task else None,
            "validity_evidence": ctx.validity_evidence,
        }
```

6) `run()`：在 intent 非法律分支之后、rewrite 之前插入任务分类与时效快路径：

```python
        task = classify_task(query, intent, user_documents)

        if task.task_type == "validity_check":
            return self._run_validity(query, intent, task, history, model_id)
```

7) 新增 `_run_validity` 方法（`_run_non_legal` 之后）：

```python
    def _run_validity(
        self,
        query: str,
        intent: IntentResult,
        task: TaskDecision,
        history: Optional[List[Dict[str, str]]] = None,
        model_id: Optional[str] = None,
    ) -> Dict:
        validity = self.verifier.validity if self.verifier else LawValidityService()
        evidence = build_validity_evidence(task.law_name, validity)
        response = self.model.generate(
            query,
            system_prompt=get_system_prompt("validity_check"),
            context_docs=[evidence["text"]],
            history=history,
            model_id=model_id,
        )
        return {
            "query": query,
            "answer": response,
            "use_rag": False,
            "retrieved_articles": [],
            "citation_verification": dict(_EMPTY_VERIFICATION),
            "consistency": None,
            "trust": None,
            "regeneration_attempts": 0,
            "intent": intent.to_dict(),
            "query_rewrite": None,
            "rag_used": False,
            "task": task.to_dict(),
            "validity_evidence": evidence,
        }
```

8) legal 分支的 `system_prompt = get_system_prompt("legal_qa")` 行改为按任务选择（供后续 Task 4/8 复用）：

```python
        system_prompt = get_system_prompt(
            "contract_review" if task.task_type == "contract_review" else "legal_qa"
        )
```

- [ ] **Step 5: 运行测试**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/ -q`
Expected: 全部通过（原有用例 + 新用例；`task`/`validity_evidence` 为可选字段，不影响旧路径）。

- [ ] **Step 6: 集成验证（真实 API）**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe scripts/run_server.py`（后台启动），然后：

```bash
curl -s -X POST http://localhost:6006/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"婚姻法现在还有效吗？","history":[],"user_documents":[],"use_rag":true,"enable_consistency":false,"enable_nli":true,"n_consistency_samples":2,"privacy_confirmed":true}'
```

Expected: `task.task_type == "validity_check"`、`validity_evidence.effective == false`、回答包含「废止」且不出现三段式结构、`trust` 为 null。验证后停掉服务。

- [ ] **Step 7: 提交**

```bash
git add src/knowledge_base/law_validity.py src/llm/qwen_model.py src/pipeline/answer_pipeline.py tests/
git commit -m "feat: 时效查询管线（注册表确定性证据 + 专用提示词 + 快路径）"
```

---

### Task 4: 合同审查管线与文档引文核验

**Files:**
- Create: `src/citation_verifier/document_quotes.py`
- Modify: `src/citation_verifier/citation_verifier.py`（`verify` 增加 `user_documents` 参数）
- Modify: `src/llm/qwen_model.py`（`_SYSTEM_PROMPT_CONTRACT` + `get_system_prompt` 分支）
- Modify: `src/pipeline/answer_pipeline.py`（run_verification 与 run() 的 verify 调用传 `user_documents`）
- Test: `tests/test_document_quotes.py`（新增）、`tests/test_qwen_prompts.py`（追加用例）

**Interfaces:**
- Consumes: Task 2 的 `task.task_type == "contract_review"` 分支（Task 3 已接入 system_prompt 选择）。
- Produces:
  - `src.citation_verifier.document_quotes.DocumentQuoteVerifier.verify(response: str, user_documents: List[Dict]) -> Dict`（返回 `{"document_quote_checks": [...]}`，每项 `{text, found, verdict: "verified" | "document_mismatch", in_document}`）
  - `CitationVerifier.verify(llm_response, retrieved_docs=None, user_documents=None)` → 报告新增 `document_quote_checks`（None 或列表）
  - `get_system_prompt("contract_review")` 返回合同风险清单专用提示词

- [ ] **Step 1: 写失败测试**

`tests/test_document_quotes.py`：

```python
"""文档引文核验单测：回答引用的文档原文必须与上传文档逐字一致。"""
from src.citation_verifier.document_quotes import DocumentQuoteVerifier

_DOC = [{"filename": "劳动合同.txt", "text": "第一条 试用期三个月。甲方应按时支付工资。"}]


def test_quote_found_in_document():
    checks = DocumentQuoteVerifier().verify(
        "合同约定「试用期三个月」，甲方应按时支付工资。", _DOC
    )["document_quote_checks"]
    assert checks and checks[0]["verdict"] == "verified"
    assert checks[0]["found"] is True


def test_quote_not_found_in_document():
    """模型编造条款（「试用期六个月」不在文档中）→ 标 document_mismatch"""
    checks = DocumentQuoteVerifier().verify(
        "合同约定「试用期六个月」明显违法。", _DOC
    )["document_quote_checks"]
    assert checks and checks[0]["verdict"] == "document_mismatch"
    assert checks[0]["found"] is False


def test_law_name_quote_not_treated_as_doc_clause():
    """《劳动合同法》等法条引用不含文档条款信号词 → 不进入文档引文检查"""
    checks = DocumentQuoteVerifier().verify(
        "依据《劳动合同法》第十九条，试用期不得超过六个月。", _DOC
    )["document_quote_checks"]
    assert checks == []


def test_no_documents_returns_empty():
    assert DocumentQuoteVerifier().verify("任何回答", [])["document_quote_checks"] == []
```

`tests/test_qwen_prompts.py` 追加：

```python
def test_contract_prompt():
    """合同审查提示词：风险清单结构、引用文档原文须一致"""
    p = get_system_prompt("contract_review")
    assert "合同风险清单" in p and "修改建议" in p
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_document_quotes.py tests/test_qwen_prompts.py -q`
Expected: 新用例失败（ImportError / 断言失败）。

- [ ] **Step 3: 实现文档引文核验器**

创建 `src/citation_verifier/document_quotes.py`：

```python
"""文档引文核验：回答中引用用户上传文档的句子，与文档原文逐字比对。

场景：合同审查管线。模型可能编造合同条款（引号内内容并非文档原文），
本模块检测并标记，防止「模型说出来的条款」被误当文档事实。
纯字符串逻辑、无外部依赖，可独立单测。
"""
import re
from typing import Dict, List

# 引号样式：中文直角引号与书名号（文档名引用也可能是《合同名》）
_QUOTE_PATTERNS = [
    re.compile(r"「([^」]{2,120})」"),
    re.compile(r"《([^》]{2,120})》"),
]
# 疑似文档条款内容的信号词（非此信号不判定为文档引文，避免把法条名误报）
_DOC_CLAUSE_HINTS = (
    "甲方", "乙方", "丙方", "条款", "本合同", "本协议",
    "第.{1,4}条", "签字", "盖章", "试用期", "工资", "违约金", "期限", "报酬",
)


def _looks_like_doc_clause(text: str) -> bool:
    return any(re.search(p, text) for p in _DOC_CLAUSE_HINTS)


class DocumentQuoteVerifier:
    """对回答做文档引文检查（返回 document_quote_checks 列表）。"""

    def verify(self, response: str, user_documents: List[Dict]) -> Dict:
        doc_texts = [d.get("text") or "" for d in (user_documents or [])]
        all_text = "\n".join(doc_texts)
        checks = []
        for pattern in _QUOTE_PATTERNS:
            for quote in pattern.findall(response or ""):
                if not _looks_like_doc_clause(quote):
                    continue
                checks.append({
                    "text": quote,
                    "found": quote in all_text,
                    "verdict": "verified" if quote in all_text else "document_mismatch",
                    "in_document": quote in all_text,
                })
        return {"document_quote_checks": checks}
```

- [ ] **Step 4: 接入 CitationVerifier 与合同提示词**

`src/citation_verifier/citation_verifier.py`：

1) 顶部 import 追加：

```python
from src.citation_verifier.document_quotes import DocumentQuoteVerifier
```

2) `verify` 签名改为：

```python
    def verify(
        self,
        llm_response: str,
        retrieved_docs: Optional[List[Document]] = None,
        user_documents: Optional[List[Dict]] = None,
    ) -> Dict:
```

3) 函数体末尾（implicit 核验之后、return 之前）追加：

```python
        document_quote_checks = None
        if user_documents:
            document_quote_checks = DocumentQuoteVerifier().verify(
                llm_response, user_documents
            )["document_quote_checks"]

        return {
            "extracted_citations": citation_results,
            "implicit_claims": implicit_results,
            "overall_citation_score": overall_score,
            "summary": summary,
            "validity_warnings": validity_warnings,
            "document_quote_checks": document_quote_checks,
        }
```

（注：把现有 `return {...}` 语句整体替换为上面的结构，保留原有键与变量名不动，仅新增 `document_quote_checks` 键。）

`src/llm/qwen_model.py`：在 `_SYSTEM_PROMPT_VALIDITY` 之前追加：

```python
_SYSTEM_PROMPT_CONTRACT = """你是律策智枢 LawPilot智能助手，专业合同审查员。用户上传了合同/协议并请求审查。

请输出结构化风险清单，格式如下（小节标题必须保留）：

【合同风险清单】
1. ⚠️ 条款类型：<条款主题，如试用期约定>
   风险点：<该条款存在的问题或法律风险>
   法律依据：<相关法条全名与条号，仅引用「参考法条」中已有的条文>
   修改建议：<具体可操作的修改方案>

……（逐条列出；确无风险则写「未发现明显风险条款」）

【总体评价】
用 2～4 句话概括合同整体风险水平（低/中/高）与最需要关注的问题。

要求：
- 引用合同条款时须与「用户上传文档」原文一致（引号内逐字复述，不得改写）；
- 引用法条时仅引用「参考法条」，条号与法律名称须一致；
- 不编造合同中不存在的条款；不确定处如实说明。"""
```

`get_system_prompt` 追加：

```python
    if intent == "contract_review":
        return _SYSTEM_PROMPT_CONTRACT
```

- [ ] **Step 5: 流水线核验传递 user_documents**

`src/pipeline/answer_pipeline.py` 中所有 `self.verifier.verify(response, retrieved_docs=...)` 调用（run() 内两处：初次核验与重生成核验、以及 `run_verification` 内一处）统一改为：

```python
            self.verifier.verify(
                response,
                retrieved_docs=retrieved_docs,
                user_documents=user_documents,
            )
```

`run_verification` 内对应改为：

```python
        verification = (
            self.verifier.verify(
                response,
                retrieved_docs=ctx.retrieved_docs,
                user_documents=ctx.user_documents,
            )
            if ctx.rag_used
            else dict(_EMPTY_VERIFICATION)
        )
```

（run() 内 `retrieved_docs` 为局部变量名；`run_verification` 内为 `ctx.retrieved_docs`，注意区分。）

- [ ] **Step 6: 运行测试**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/ -q`
Expected: 全部通过。

- [ ] **Step 7: 集成验证（真实 API + 上传文档）**

启动服务后：

```bash
# 先提取文档文本
curl -s -X POST http://localhost:6006/api/documents/extract -F "file=@<一份含试用期/工资条款的合同txt>" | head -c 400
# 再用提取到的 text 走 /api/chat（user_documents 带 filename/text）
curl -s -X POST http://localhost:6006/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"这份合同有什么风险条款？","history":[],"user_documents":[{"filename":"合同.txt","text":"<上一步提取的文本>","format":"txt","char_count":<长度>}],"use_rag":true,"enable_consistency":false,"enable_nli":true,"n_consistency_samples":2,"privacy_confirmed":true}'
```

Expected: `task.task_type == "contract_review"`、回答含「【合同风险清单】」结构；回答若引用了文档原文，「引用核验」报告含 `document_quote_checks`。验证后停服务。

- [ ] **Step 8: 提交**

```bash
git add src/citation_verifier/ src/llm/qwen_model.py src/pipeline/answer_pipeline.py tests/
git commit -m "feat: 合同审查管线（风险清单提示词 + 文档引文核验）"
```

---

### Task 5: 工具定义与执行器（tools.py）

**Files:**
- Create: `src/agents/tools.py`
- Test: `tests/test_tools.py`（新增）

**Interfaces:**
- Consumes: `Config.AGENT_TOOL_ARG_MAX_LEN`、`Config.TOP_K_RETRIEVAL`、`Config.RETRIEVAL_MIN_RELEVANCE`、`LawValidityService`、`format_article_record`、`is_retrieval_relevant`（`src.pipeline.query_rewriter`）。
- Produces:
  - `src.agents.tools.TOOLS: List[Dict]`（两个 function calling 工具 schema）
  - `src.agents.tools.execute_tool(name: str, args: Dict[str, Any], store=None, validity=None) -> Dict`
    - `search_articles` 返回 `{"articles": [format_article_record 列表], "count": n, "note": ""}`
    - `check_law_validity` 返回 `{"effective": bool, "status": str, "repeal_date": str, "superseded_by": str, "warning_message": str, "note": ""}`
    - 未知工具返回 `{"error": "未知工具：..."}`（不抛异常）

- [ ] **Step 1: 写失败测试**

`tests/test_tools.py`：

```python
"""工具执行器单测：检索法条 / 查询时效（用假 store 与临时注册表）。"""
import json
import tempfile
from pathlib import Path

from langchain_core.documents import Document

from src.agents.tools import TOOLS, execute_tool
from src.knowledge_base.law_validity import LawValidityService


class FakeStore:
    """只实现相似度检索的假 store（距离：0=最近，1=最远）。"""

    def __init__(self, results):
        self._results = results

    def similarity_search_unique(self, query, k=None):
        return self._results


def _doc(law: str, num: str, text: str) -> Document:
    return Document(page_content=text, metadata={"law_name": law, "article_num": num, "status": "effective"})


def test_tools_contain_two_functions():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"search_articles", "check_law_validity"}


def test_search_articles_hit():
    store = FakeStore([
        (_doc("工伤保险条例", "第十七条", "职工发生事故伤害，所在单位应当自事故伤害发生之日起30日内提出工伤认定申请。"), 0.2),
        (_doc("工伤保险条例", "第十八条", "提出工伤认定申请应当提交下列材料。"), 0.9),  # 低于阈值 0.35，应被过滤
    ])
    out = execute_tool("search_articles", {"query": "工伤认定时效", "law_name": "工伤保险条例"}, store=store)
    assert out["count"] == 1
    assert out["articles"][0]["law_name"] == "工伤保险条例"
    assert out["articles"][0]["article_num"] == "第十七条"


def test_search_articles_empty_query():
    out = execute_tool("search_articles", {"query": "   "}, store=FakeStore([]))
    assert out["count"] == 0 and out["note"]


def test_check_validity():
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "law_registry.json"
    p.write_text(json.dumps({
        "婚姻法": {"status": "repealed", "repeal_date": "2021-01-01", "superseded_by": "民法典"},
    }, ensure_ascii=False), encoding="utf-8")
    svc = LawValidityService(registry_path=str(p))
    out = execute_tool("check_law_validity", {"law_name": "婚姻法"}, validity=svc)
    assert out["effective"] is False
    assert out["superseded_by"] == "民法典"
    out2 = execute_tool("check_law_validity", {"law_name": "劳动合同法"}, validity=svc)
    assert out2["effective"] is True


def test_unknown_tool_returns_error():
    out = execute_tool("no_such_tool", {})
    assert "error" in out


def test_arg_sanitized():
    out = execute_tool("search_articles", {"query": "a" * 500}, store=FakeStore([]))
    assert out["count"] == 0  # 超长参数被截断后检索不到，不抛异常
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_tools.py -q`
Expected: 失败（ModuleNotFoundError：src.agents.tools）。

- [ ] **Step 3: 实现工具注册表与执行器**

创建 `src/agents/tools.py`：

```python
"""法律工具注册表：工具的「说明书」（模型用）与「执行者」（代码用）。

首期 2 个确定性工具：检索法条、查询法律时效。
工具执行只触碰本地向量库与本地注册表，无任何外部调用；
未知工具/参数异常返回错误结果（不抛出——结果进入轨迹，模型可自行纠正）。
"""
import re
from typing import Any, Dict, List, Optional

from src.config import Config
from src.knowledge_base.law_validity import LawValidityService
from src.knowledge_base.retrieval_utils import format_article_record
from src.pipeline.query_rewriter import is_retrieval_relevant


SEARCH_ARTICLES_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_articles",
        "description": "在法律知识库中检索相关法条。当现有参考法条可能未覆盖问题的全部关键条文"
                       "（如问题涉及多部法律、多个条款）时调用；指定法律名称可提高精度。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词，描述要查找的法律问题，如：工伤认定时效"},
                "law_name": {"type": "string", "description": "可选，指定法律名称，如：工伤保险条例"},
            },
            "required": ["query"],
        },
    },
}

CHECK_VALIDITY_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "check_law_validity",
        "description": "查询某部法律是否现行有效（含废止日期与替代法律）。"
                       "当回答涉及特定法律的时效状态、或引用的法律可能已废止时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "law_name": {"type": "string", "description": "法律名称，如：婚姻法"},
            },
            "required": ["law_name"],
        },
    },
}

TOOLS: List[Dict[str, Any]] = [SEARCH_ARTICLES_TOOL, CHECK_VALIDITY_TOOL]


def _clean_arg(value: Any) -> str:
    """参数清洗：去首尾空白、剔除控制字符、截断超长。"""
    text = str(value or "").strip()
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return text[: Config.AGENT_TOOL_ARG_MAX_LEN]


def _execute_search_articles(args: Dict[str, Any], store) -> Dict:
    """向量检索执行者。store 只需提供 similarity_search_unique（测试可注入假 store）。"""
    query = _clean_arg(args.get("query"))
    if not query:
        return {"articles": [], "count": 0, "note": "检索词为空"}
    raw = store.similarity_search_unique(query, k=Config.TOP_K_RETRIEVAL)
    hits = []
    for doc, distance in raw:
        if not is_retrieval_relevant(distance, Config.RETRIEVAL_MIN_RELEVANCE):
            continue
        hits.append(format_article_record(doc, distance))
    return {"articles": hits, "count": len(hits), "note": ""}


def _execute_check_law_validity(args: Dict[str, Any], validity: LawValidityService) -> Dict:
    law_name = _clean_arg(args.get("law_name"))
    if not law_name:
        return {"effective": True, "status": "effective", "note": "法律名称为空"}
    result = validity.check_citation(law_name, "")
    return {**result.to_dict(), "note": ""}


def execute_tool(
    name: str,
    args: Dict[str, Any],
    store=None,
    validity: Optional[LawValidityService] = None,
) -> Dict:
    """统一分发入口：未知工具返回错误结果（不抛出，进入轨迹）。"""
    if name == "search_articles":
        return _execute_search_articles(args or {}, store)
    if name == "check_law_validity":
        return _execute_check_law_validity(args or {}, validity or LawValidityService())
    return {"error": f"未知工具：{name}"}
```

- [ ] **Step 4: 运行确认通过**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_tools.py -q`
Expected: 6 passed。

- [ ] **Step 5: 提交**

```bash
git add src/agents/tools.py tests/test_tools.py
git commit -m "feat: 工具注册表与执行器（检索法条 / 查询时效，参数清洗）"
```

---

### Task 6: 模型层工具调用实现（api_client + qwen_model）

**Files:**
- Modify: `src/llm/api_client.py`（`import json` + 两个方法）
- Modify: `src/llm/qwen_model.py`（`build_messages` 公开包装 + `supports_tools` + 三个方法实现）
- Test: `tests/test_model_tools.py`（新增）

**Interfaces:**
- Consumes: Task 1 的 `ToolCall` / `ToolDecision` 契约。
- Produces:
  - `APIClient.complete_with_tools(messages, tools, model_id, temperature=0.0, max_tokens=512) -> ToolDecision`
  - `APIClient.complete_stream_with_tools(messages, tools, model_id, temperature=0.0, max_tokens=512) -> Generator[Tuple[str, Any]]`（重试语义与 `complete_stream` 一致）
  - `QwenModel.build_messages(query, system_prompt, context_docs=None, history=None, intent_hint=None) -> List[Dict]`（公开，内部复用 `_build_messages`）
  - `QwenModel.supports_tools(model_id=None) -> bool`
  - `QwenModel.complete_with_tools / complete_stream_with_tools`（本地引擎抛 `NotImplementedError`）
  - `QwenModel.generate_stream_messages(messages, model_id=None, temperature=None, max_new_tokens=None) -> Generator[str]`

- [ ] **Step 1: 写失败测试**

`tests/test_model_tools.py`：

```python
"""QwenModel 工具接口单测：用假 APIClient 验证消息传递与降级行为。"""
import pytest

from src.llm.base import ToolCall, ToolDecision
from src.llm.qwen_model import QwenModel
from src.agents.tools import TOOLS


class FakeAPIClient:
    """记录调用参数的假客户端（不真正访问网络）。"""

    def __init__(self, decisions=None):
        self.decisions = list(decisions or [])
        self.calls = []

    def complete_with_tools(self, messages, tools, model_id, temperature=0.0, max_tokens=512):
        self.calls.append(("complete_with_tools", messages, tools, model_id, max_tokens))
        return self.decisions.pop(0)

    def complete_stream_with_tools(self, messages, tools, model_id, temperature=0.0, max_tokens=512):
        self.calls.append(("complete_stream_with_tools", messages, tools, model_id, max_tokens))
        yield from self.decisions.pop(0)

    def complete_stream(self, messages, model_id, temperature=0.4, max_tokens=1024):
        self.calls.append(("complete_stream", messages, model_id))
        yield "流式文本"


def _make_model(decisions):
    m = QwenModel(provider="api", api_client=FakeAPIClient(decisions))
    fake = m._api
    m._get_api_client = lambda spec: fake  # 绕过 base_url 客户端缓存，注入假客户端
    return m


def test_complete_with_tools_passes_messages_and_tools():
    m = _make_model([ToolDecision(text="", tool_calls=[ToolCall("c1", "search_articles", {"query": "x"})])])
    msgs = [{"role": "user", "content": "问题"}]
    dec = m.complete_with_tools(msgs, TOOLS, model_id="qwen-turbo")
    assert dec.tool_calls[0].name == "search_articles"
    assert m._api.calls[0][1] == msgs and m._api.calls[0][2] == TOOLS
    assert m._api.calls[0][3] == "qwen-turbo"


def test_complete_with_tools_text_result():
    m = _make_model([ToolDecision(text="直接回答", tool_calls=[])])
    dec = m.complete_with_tools([{"role": "user", "content": "q"}], TOOLS, model_id="qwen-turbo")
    assert dec.text == "直接回答" and dec.tool_calls == []


def test_stream_with_tools_yields_text_then_calls():
    def gen():
        yield ("text", "分析中")
        yield ("tool_calls", [ToolCall("c1", "search_articles", {"query": "x"})])
    m = _make_model([gen()])
    out = list(m.complete_stream_with_tools([{"role": "user", "content": "q"}], TOOLS, model_id="qwen-turbo"))
    assert out[0] == ("text", "分析中")
    assert out[1][0] == "tool_calls" and out[1][1][0].name == "search_articles"


def test_generate_stream_messages_delegates():
    m = _make_model([])
    m._get_api_client = lambda spec: m._api
    chunks = list(m.generate_stream_messages([{"role": "user", "content": "q"}], model_id="qwen-turbo"))
    assert chunks == ["流式文本"]
    assert m._api.calls[0][0] == "complete_stream"


def test_local_engine_raises_not_implemented():
    m = QwenModel(provider="local")
    assert m.supports_tools("qwen-turbo") is True
    assert m.supports_tools("local") is False  # "local" 不在注册表 → 视为不支持
    with pytest.raises(NotImplementedError):
        m.complete_with_tools([{"role": "user", "content": "q"}], TOOLS)
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_model_tools.py -q`
Expected: 失败（AttributeError：complete_with_tools 不存在）。

- [ ] **Step 3: 实现 APIClient 工具方法**

`src/llm/api_client.py`：顶部 `import os` 之后追加 `import json`；`complete_stream` 方法之后追加两个方法：

```python
    # ------------------------------------------------------------------
    # 工具调用（function calling）
    # ------------------------------------------------------------------

    def complete_with_tools(
        self,
        messages,
        tools,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> "ToolDecision":
        """非流式工具决策。temperature 固定 0.0：决策要稳定可复现。"""
        from src.llm.base import ToolCall, ToolDecision

        kwargs = self._request_kwargs(model_id, messages, temperature, max_tokens, stream=False)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
        resp = self._get_client().chat.completions.create(**kwargs)
        self._log_usage(model_id, resp)
        msg = resp.choices[0].message
        if not getattr(msg, "tool_calls", None):
            return ToolDecision(text=msg.content or "", tool_calls=[])
        calls = []
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(
                id=tc.id or "",
                name=tc.function.name or "",
                arguments=args if isinstance(args, dict) else {},
            ))
        return ToolDecision(text="", tool_calls=calls)

    def complete_stream_with_tools(
        self,
        messages,
        tools,
        model_id: str,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ):
        """流式工具决策：yield ("text", str)；流内含工具调用时结束前再 yield ("tool_calls", [...]).

        重试语义与 complete_stream 一致：首个产出前的失败才重试；
        已产出内容后异常立即上抛。
        """
        from src.llm.base import ToolCall

        kwargs = self._request_kwargs(model_id, messages, temperature, max_tokens, stream=True)
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
        produced = False
        last_exc = None
        attempts = 0

        while True:
            attempts += 1
            try:
                stream = self._get_client().chat.completions.create(**kwargs)
                acc: dict = {}
                has_tool_calls = False
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta is None:
                        continue
                    if getattr(delta, "reasoning_content", None):
                        continue  # 思考链不属于回答内容，跳过
                    if delta.content:
                        produced = True
                        yield ("text", delta.content)
                    if delta.tool_calls:
                        has_tool_calls = True
                        for tc in delta.tool_calls:
                            idx = tc.index
                            entry = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                            if tc.id:
                                entry["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    entry["name"] += tc.function.name
                                if tc.function.arguments:
                                    entry["arguments"] += tc.function.arguments
                if has_tool_calls:
                    calls = []
                    for idx in sorted(acc):
                        entry = acc[idx]
                        try:
                            args = json.loads(entry["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        calls.append(ToolCall(
                            id=entry["id"],
                            name=entry["name"],
                            arguments=args if isinstance(args, dict) else {},
                        ))
                    yield ("tool_calls", calls)
                return
            except Exception as exc:  # noqa: BLE001 - 统一分类，与 complete_stream 一致
                last_exc = exc
                retryable = self._handle_call_exception(exc, model_id)
                if produced or attempts > Config.API_MAX_RETRIES or not retryable:
                    raise RuntimeError(
                        f"{self.provider_label} API 流式工具调用失败"
                        f"{'（已产出部分内容，停止重试）' if produced else f'（已重试 {Config.API_MAX_RETRIES} 次）'}"
                        f"：{self._friendly_error(model_id, exc)}"
                    )
                print(f"{self.provider_label} API 流式工具调用失败（{type(exc).__name__}），准备重试…")
                self._sleep_backoff(attempts - 1)
```

- [ ] **Step 4: 实现 QwenModel 方法**

`src/llm/qwen_model.py`：

1) `_build_messages` 定义之后追加公开包装：

```python
    def build_messages(
        self,
        query: str,
        system_prompt: str,
        context_docs: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        intent_hint: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """公开版消息构建（generate / agent_loop 共用）。"""
        return self._build_messages(query, system_prompt, context_docs, history, intent_hint)
```

2) `generate_stream` 方法之后追加：

```python
    # ------------------------------------------------------------------
    # 工具调用（function calling；仅 API 引擎，本地 7B 不支持）
    # ------------------------------------------------------------------

    def supports_tools(self, model_id: Optional[str] = None) -> bool:
        """当前模型是否支持函数调用（API 引擎支持；本地 7B 不支持）。"""
        try:
            return self._resolve_model(model_id).provider != "local"
        except ValueError:
            return False

    def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ) -> "ToolDecision":
        spec = self._resolve_model(model_id)
        if spec.provider == "local":
            raise NotImplementedError("本地引擎不支持函数调用（agent_loop 会自动降级为普通生成）")
        return self._get_api_client(spec).complete_with_tools(
            messages, tools, model_id=spec.id, max_tokens=max_tokens
        )

    def complete_stream_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        model_id: Optional[str] = None,
        max_tokens: int = 512,
    ):
        spec = self._resolve_model(model_id)
        if spec.provider == "local":
            raise NotImplementedError("本地引擎不支持函数调用（agent_loop 会自动降级为普通生成）")
        yield from self._get_api_client(spec).complete_stream_with_tools(
            messages, tools, model_id=spec.id, max_tokens=max_tokens
        )

    def generate_stream_messages(
        self,
        messages: List[Dict[str, str]],
        model_id: Optional[str] = None,
        temperature: float = None,
        max_new_tokens: int = None,
    ) -> Generator[str, None, None]:
        """按原始消息列表流式生成（工具对话历史已在 messages 中）。"""
        self._load()
        temperature = temperature if temperature is not None else Config.LLM_TEMPERATURE
        max_new_tokens = max_new_tokens or Config.LLM_MAX_NEW_TOKENS
        spec = self._resolve_model(model_id)

        if spec.provider != "local":
            yield from self._get_api_client(spec).complete_stream(
                messages, model_id=spec.id, temperature=temperature, max_tokens=max_new_tokens
            )
            return

        # 本地分支：直接对 messages 做 chat template 流式
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs = dict(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id,
            streamer=streamer,
        )
        thread = threading.Thread(target=self.model.generate, kwargs=gen_kwargs)
        thread.start()
        for chunk in streamer:
            if chunk:
                yield chunk
        thread.join()
```

- [ ] **Step 5: 运行测试**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_model_tools.py tests/test_qwen_prompts.py -q`
Expected: 全部通过（FakeAPIClient 的 `complete_stream` 签名与真实调用一致：`complete_stream(messages, model_id=..., temperature=..., max_tokens=...)`）。

- [ ] **Step 6: 提交**

```bash
git add src/llm/api_client.py src/llm/qwen_model.py tests/test_model_tools.py
git commit -m "feat: 模型层工具调用实现（complete_with_tools / 流式决策 / 本地降级）"
```

---

### Task 7: 工具循环引擎（trace.py + agent_loop.py）

**Files:**
- Create: `src/agents/trace.py`、`src/agents/agent_loop.py`
- Test: `tests/test_agent_loop.py`（新增）

**Interfaces:**
- Consumes: Task 1 契约、Task 5 的 `TOOLS` / `execute_tool`、`PipelineContext`（Task 3 已加 `task` 字段）、`Config.AGENT_MAX_TOOL_ROUNDS` / `AGENT_DECISION_MAX_TOKENS` / `DOC_MAX_CONTEXT_CHARS`。
- Produces:
  - `src.agents.trace.ToolTraceStep(step, tool_name, arguments, result_summary, success=True, cost_ms=0)`，含 `to_dict()`
  - `src.agents.trace.AgentStatusEvent(step, tool_name="", status="running", detail="", result_summary="")`，含 `to_dict()`；`status` ∈ running | done | error | generating
  - `src.agents.trace.AgentEvent = Union[AgentStatusEvent, str]`
  - `src.agents.agent_loop.AgentToolLoop(model, store, validity=None, max_rounds=None)`
    - 属性：`answer: str`、`trace: List[ToolTraceStep]`、`found_docs: List[Document]`（工具检索到的法条，供核验合并）
    - `stream(ctx: PipelineContext, model_id=None) -> Generator[AgentEvent, None, None]`
    - `run(ctx: PipelineContext, model_id=None) -> Tuple[str, List[ToolTraceStep]]`（非流式版）

- [ ] **Step 1: 写失败测试**

`tests/test_agent_loop.py`：

```python
"""工具循环引擎单测：无工具 / 调工具 / 轮次耗尽 / 出错降级。"""
from langchain_core.documents import Document

from src.agents.agent_loop import AgentToolLoop
from src.agents.trace import AgentStatusEvent
from src.llm.base import ToolCall
from src.pipeline.answer_pipeline import PipelineContext
from src.pipeline.intent_router import IntentResult


class FakeModel:
    """脚本化的假模型：按 scripted 序列依次产出决策/文本。"""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.built_messages = None

    def build_messages(self, query, system_prompt, context_docs=None, history=None, intent_hint=None):
        self.built_messages = [{"role": "user", "content": query}]
        return list(self.built_messages)

    def complete_stream_with_tools(self, messages, tools, model_id=None, max_tokens=512):
        item = self.scripted.pop(0)
        if item["kind"] == "text":
            yield ("text", item["text"])
            return
        yield ("tool_calls", item["calls"])

    def generate_stream_messages(self, messages, model_id=None, temperature=None, max_new_tokens=None):
        yield "轮次耗尽兜底回答"

    def generate(self, query, system_prompt=None, temperature=None, max_new_tokens=None,
                 context_docs=None, history=None, intent_hint=None, model_id=None):
        return "兜底回答"


class FakeStore:
    def __init__(self, docs):
        self._docs = docs

    def similarity_search_unique(self, query, k=None):
        return self._docs


def _doc(law, num, text):
    return Document(page_content=text, metadata={"law_name": law, "article_num": num, "status": "effective"})


def _ctx(task_type="legal_qa"):
    intent = IntentResult("legal_qa", 0.9, "test")
    return PipelineContext(
        query="工伤认定和劳动仲裁时效分别是多久？",
        intent=intent,
        generation_query="工伤认定和劳动仲裁时效分别是多久？",
        system_prompt="system",
        context_docs=["参考法条：…"],
        model_id="qwen-turbo",
    )


def test_no_tool_call_streams_answer():
    model = FakeModel([{"kind": "text", "text": "直接回答"}])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert events == ["直接回答"]
    assert loop.answer == "直接回答"
    assert loop.trace == []
    assert loop.found_docs == []


def test_tool_call_then_final_answer():
    store = FakeStore([(_doc("工伤保险条例", "第十七条", "30日内提出工伤认定申请"), 0.2)])
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "工伤认定时效", "law_name": "工伤保险条例"})]},
        {"kind": "text", "text": "最终回答"},
    ])
    loop = AgentToolLoop(model, store, max_rounds=3)
    events = list(loop.stream(_ctx()))
    kinds = [type(e) for e in events]
    assert AgentStatusEvent in kinds and str in kinds
    assert loop.answer == "最终回答"
    assert len(loop.trace) == 1
    assert loop.trace[0].tool_name == "search_articles"
    assert loop.trace[0].success is True
    assert loop.found_docs  # 工具检索到的法条被收集


def test_round_exhaustion_falls_back():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "x"})]},
        {"kind": "calls", "calls": [ToolCall("c2", "search_articles", {"query": "y"})]},
        {"kind": "calls", "calls": [ToolCall("c3", "search_articles", {"query": "z"})]},
        {"kind": "calls", "calls": [ToolCall("c4", "search_articles", {"query": "w"})]},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert loop.answer == "轮次耗尽兜底回答"
    assert len(loop.trace) == 3
    assert any(isinstance(e, AgentStatusEvent) and e.status == "generating" for e in events)


def test_unknown_tool_records_failure_and_continues():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "no_such_tool", {})]},
        {"kind": "text", "text": "继续回答"},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert loop.trace[0].success is False
    assert "未知工具" in loop.trace[0].result_summary
    assert loop.answer == "继续回答"


def test_not_implemented_degrades_to_plain_generation():
    class NoToolsModel(FakeModel):
        def complete_stream_with_tools(self, messages, tools, model_id=None, max_tokens=512):
            raise NotImplementedError("本地引擎不支持函数调用")

    loop = AgentToolLoop(NoToolsModel([]), FakeStore([]), max_rounds=3)
    events = list(loop.stream(_ctx()))
    assert "".join(e for e in events if isinstance(e, str)) == "轮次耗尽兜底回答"


def test_run_non_streaming():
    model = FakeModel([
        {"kind": "calls", "calls": [ToolCall("c1", "search_articles", {"query": "x"})]},
        {"kind": "text", "text": "非流式最终回答"},
    ])
    loop = AgentToolLoop(model, FakeStore([]), max_rounds=3)
    answer, trace = loop.run(_ctx())
    assert answer == "非流式最终回答"
    assert len(trace) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_agent_loop.py -q`
Expected: 失败（ModuleNotFoundError：src.agents.agent_loop）。

- [ ] **Step 3: 实现 trace.py**

创建 `src/agents/trace.py`：

```python
"""工具调用轨迹与智能体状态事件的数据模型。"""
from dataclasses import dataclass
from typing import Any, Dict, List, Union


@dataclass
class ToolTraceStep:
    """轨迹中一步工具调用的完整记录（随 done 事件返回，详情面板展示）。"""

    step: int
    tool_name: str
    arguments: Dict[str, Any]
    result_summary: str
    success: bool = True
    cost_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_summary": self.result_summary,
            "success": self.success,
            "cost_ms": self.cost_ms,
        }


@dataclass
class AgentStatusEvent:
    """SSE agent_status 事件的负载（前端生成中状态行）。"""

    step: int
    tool_name: str = ""
    status: str = "running"   # running | done | error | generating
    detail: str = ""
    result_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "tool_name": self.tool_name,
            "status": self.status,
            "detail": self.detail,
            "result_summary": self.result_summary,
        }


# 智能体流式事件：状态事件或文本块
AgentEvent = Union[AgentStatusEvent, str]
```

- [ ] **Step 4: 实现 agent_loop.py**

创建 `src/agents/agent_loop.py`：

```python
"""工具调用循环引擎（ReAct 简化版）：生成 → 调用工具 → 再看 → 再生成。

- 上限轮次防死循环；每轮工具决策 token 上限防费用爆炸；
- 工具结果只作模型参考；最终回答照常由外层引用核验闭环检查；
- 本地引擎（NotImplementedError）自动降级为普通生成（等于现状）；
- 工具执行失败记录进轨迹并继续（不中断循环）。
"""
import json
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

from langchain_core.documents import Document

from src.agents.tools import TOOLS, execute_tool
from src.agents.trace import AgentEvent, AgentStatusEvent, ToolTraceStep
from src.config import Config
from src.llm.base import ToolCall
from src.pipeline.answer_pipeline import PipelineContext


def _tool_result_payload(result: Dict) -> str:
    """工具结果转模型可见文本（截断防止上下文爆炸）。"""
    text = json.dumps(result, ensure_ascii=False)
    return text[: Config.DOC_MAX_CONTEXT_CHARS]


class AgentToolLoop:
    """一次问答的工具循环。stream()/run() 执行后，answer / trace / found_docs 即为结果。"""

    def __init__(self, model, store, validity=None, max_rounds: int = None):
        self.model = model
        self.store = store
        self.validity = validity
        self.max_rounds = max_rounds or Config.AGENT_MAX_TOOL_ROUNDS
        self.answer: str = ""
        self.trace: List[ToolTraceStep] = []
        self.found_docs: List[Document] = []

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    def _execute_with_payload(self, step_no: int, call: ToolCall) -> Tuple[ToolTraceStep, str]:
        t0 = time.time()
        try:
            result = execute_tool(
                call.name, call.arguments,
                store=self.store, validity=self.validity,
            )
            cost_ms = int((time.time() - t0) * 1000)
            step = ToolTraceStep(
                step_no, call.name, call.arguments,
                self._summarize_result(result), True, cost_ms,
            )
            if call.name == "search_articles":
                self.found_docs.extend(self._docs_from_payload(result))
            return step, _tool_result_payload(result)
        except Exception as e:  # noqa: BLE001 - 工具失败不中断循环
            cost_ms = int((time.time() - t0) * 1000)
            err = f"工具执行失败：{e}"
            step = ToolTraceStep(step_no, call.name, call.arguments, err, False, cost_ms)
            return step, json.dumps({"error": err}, ensure_ascii=False)

    @staticmethod
    def _summarize_result(result: Dict) -> str:
        if result.get("count") is not None:
            return f"命中 {result['count']} 条法条"
        if result.get("effective") is not None:
            if result["effective"]:
                return "现行有效"
            parts = ["已废止"]
            if result.get("repeal_date"):
                parts.append(f"（{result['repeal_date']}）")
            if result.get("superseded_by"):
                parts.append(f"，替代《{result['superseded_by']}》")
            return "".join(parts)
        return f"共 {len(result)} 个字段"

    @staticmethod
    def _docs_from_payload(payload: Dict) -> List[Document]:
        """把检索结果的 payload 还原为 Document（供引用核验合并上下文）。"""
        docs = []
        for a in payload.get("articles", []):
            meta = {k: a.get(k, "") for k in (
                "law_name", "article_num", "status", "effective_date", "repeal_date", "superseded_by"
            )}
            docs.append(Document(
                page_content=a.get("full_text") or a.get("content") or "",
                metadata=meta,
            ))
        return docs

    @staticmethod
    def _running_detail(call: ToolCall) -> str:
        if call.name == "search_articles":
            q = call.arguments.get("query", "")
            law = call.arguments.get("law_name", "")
            return f"正在检索法条：{q}" + (f"（《{law}》）" if law else "")
        if call.name == "check_law_validity":
            return f"正在核查《{call.arguments.get('law_name', '')}》的时效状态"
        return f"正在调用工具 {call.name}"

    # ------------------------------------------------------------------
    # 循环主体
    # ------------------------------------------------------------------

    def _build_messages(self, ctx: PipelineContext) -> List[Dict[str, str]]:
        return self.model.build_messages(
            ctx.generation_query,
            ctx.system_prompt,
            ctx.context_docs,
            ctx.history,
            ctx.intent_hint,
        )

    def _append_tool_round(self, messages: List[Dict[str, str]], call: ToolCall, result_text: str) -> None:
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }],
        })
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result_text,
        })

    def stream(self, ctx: PipelineContext, model_id: Optional[str] = None) -> Generator[AgentEvent, None, None]:
        """流式执行：yield AgentStatusEvent（状态）或 str（最终回答文本块）。

        结束条件：模型不再调用工具（直接输出文本）或轮次耗尽。
        """
        messages = self._build_messages(ctx)
        used = 0
        for rnd in range(1, self.max_rounds + 1):
            used = rnd
            tool_calls: List[ToolCall] = []
            try:
                for kind, payload in self.model.complete_stream_with_tools(
                    messages, TOOLS, model_id=model_id,
                    max_tokens=Config.AGENT_DECISION_MAX_TOKENS,
                ):
                    if kind == "text":
                        self.answer += payload
                        yield payload
                    else:
                        tool_calls = payload
            except NotImplementedError:
                # 本地引擎不支持函数调用：退回普通生成（等于现状）
                yield from self.model.generate_stream_messages(messages, model_id=model_id)
                return

            if not tool_calls:
                return  # 模型直接给出最终回答（文本已流式输出）

            for call in tool_calls:
                yield AgentStatusEvent(
                    step=rnd, tool_name=call.name, status="running",
                    detail=self._running_detail(call),
                )
                step, result_text = self._execute_with_payload(rnd, call)
                self.trace.append(step)
                self._append_tool_round(messages, call, result_text)
                yield AgentStatusEvent(
                    step=rnd, tool_name=call.name,
                    status="error" if not step.success else "done",
                    result_summary=step.result_summary,
                )

        # 轮次耗尽兜底：不带工具再问一次，流式输出最终回答
        yield AgentStatusEvent(
            step=used, status="generating",
            detail=f"已到达工具调用轮次上限（{self.max_rounds} 轮），综合生成最终回答…",
        )
        for chunk in self.model.generate_stream_messages(messages, model_id=model_id):
            self.answer += chunk
            yield chunk

    def run(self, ctx: PipelineContext, model_id: Optional[str] = None) -> Tuple[str, List[ToolTraceStep]]:
        """非流式版（/api/chat 同步路径）：返回 (最终回答, 轨迹)。"""
        messages = self._build_messages(ctx)
        for rnd in range(1, self.max_rounds + 1):
            try:
                decision = self.model.complete_with_tools(
                    messages, TOOLS, model_id=model_id,
                    max_tokens=Config.AGENT_DECISION_MAX_TOKENS,
                )
            except NotImplementedError:
                return self.model.generate(
                    ctx.generation_query,
                    system_prompt=ctx.system_prompt,
                    context_docs=ctx.context_docs,
                    history=ctx.history,
                    intent_hint=ctx.intent_hint,
                    model_id=model_id,
                ), self.trace
            if not decision.tool_calls:
                return decision.text, self.trace
            for call in decision.tool_calls:
                step, result_text = self._execute_with_payload(rnd, call)
                self.trace.append(step)
                self._append_tool_round(messages, call, result_text)
        # 轮次耗尽兜底：基于原始上下文普通生成
        return self.model.generate(
            ctx.generation_query,
            system_prompt=ctx.system_prompt,
            context_docs=ctx.context_docs,
            history=ctx.history,
            intent_hint=ctx.intent_hint,
            model_id=model_id,
        ), self.trace
```

- [ ] **Step 5: 运行确认通过**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_agent_loop.py -q`
Expected: 7 passed。

- [ ] **Step 6: 提交**

```bash
git add src/agents/trace.py src/agents/agent_loop.py tests/test_agent_loop.py
git commit -m "feat: 工具循环引擎（AgentToolLoop：流式/非流式 + 轨迹 + 降级）"
```

---

### Task 8: 流水线与 SSE 集成（answer_pipeline + main.py + schemas）

**Files:**
- Modify: `src/pipeline/answer_pipeline.py`（agent 循环接入 run()）
- Modify: `src/knowledge_base/retrieval_utils.py`（追加 `merge_unique_docs`）
- Modify: `web/backend/main.py`（SSE 智能体分支）
- Modify: `web/backend/schemas.py`（ChatResponse 新增可选字段）
- Test: `tests/test_retrieval_merge.py`（追加用例）

**Interfaces:**
- Consumes: Task 3 的 task 分支、Task 7 的 `AgentToolLoop`。
- Produces:
  - `src.knowledge_base.retrieval_utils.merge_unique_docs(existing: List[Document], found: List[Document]) -> List[Document]`（按 article_key 去重合并）
  - `AnswerPipeline.run(..., agent_tools: bool = False)`（新参数；为 True 且模型支持工具且任务为 legal_qa 时启用工具循环）
  - run() 返回字典新增键：`task`、`tool_trace`、`validity_evidence`
  - SSE 新增 `agent_status` 事件；done 事件新增 `tool_trace` / `task` / `validity_evidence`；meta 事件含 `task` / `validity_evidence`
  - `ChatResponse` 新增可选字段 `task` / `tool_trace` / `validity_evidence`

- [ ] **Step 1: 写失败测试**

`tests/test_retrieval_merge.py` 追加（文件末尾）：

```python
def test_merge_unique_docs():
    """工具检索结果与初始检索结果按（法律名, 条号）去重合并"""
    from src.knowledge_base.retrieval_utils import merge_unique_docs

    def d(law, num):
        return Document(page_content=f"{law}{num}内容", metadata={"law_name": law, "article_num": num})

    merged = merge_unique_docs([d("劳动合同法", "第38条")], [d("劳动合同法", "第38条"), d("工伤保险条例", "第17条")])
    assert len(merged) == 2
    assert merged[1].metadata["law_name"] == "工伤保险条例"
```

（`langchain_core.documents.Document` 已在文件头部 import。）

- [ ] **Step 2: 运行确认失败**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/test_retrieval_merge.py -q`
Expected: 失败（ImportError：merge_unique_docs）。

- [ ] **Step 3: 实现 merge_unique_docs**

`src/knowledge_base/retrieval_utils.py` 末尾追加：

```python
def merge_unique_docs(
    existing: List[Document],
    found: List[Document],
) -> List[Document]:
    """按（法律名, 条号）去重合并两组检索结果（工具检索结果并入初始结果）。"""
    seen = set()
    out: List[Document] = []
    for doc in existing:
        key = article_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    for doc in found:
        key = article_key(doc)
        if key in seen:
            continue
        seen.add(key)
        out.append(doc)
    return out
```

- [ ] **Step 4: 流水线接入 agent 循环（run()）**

`src/pipeline/answer_pipeline.py`：

1) 顶部 import 追加：

```python
from src.agents.agent_loop import AgentToolLoop
from src.knowledge_base.retrieval_utils import article_key, format_article_record, merge_unique_docs
```

2) `run()` 签名追加参数：

```python
    def run(
        self,
        query: str,
        use_rag: bool = True,
        enable_consistency: bool = False,
        n_consistency_samples: int = 2,
        enable_nli: bool = True,
        max_regeneration: int = None,
        history: Optional[List[Dict[str, str]]] = None,
        user_documents: Optional[List[Dict]] = None,
        model_id: Optional[str] = None,
        agent_tools: bool = False,
    ) -> Dict:
```

3) `run()` 内替换初始生成调用（`response = self.model.generate(...)` 之前需先算出 `task`；把 Task 3 第 6 步加的时效分支保留）：

```python
        use_tools = (
            agent_tools
            and Config.AGENT_ENABLE_TOOLS
            and self.model.supports_tools(model_id)
            and (task is None or task.task_type == "legal_qa")
        )
        tool_trace = []
        if use_tools:
            loop = AgentToolLoop(
                self.model, self.store,
                validity=(self.verifier.validity if self.verifier else None),
            )
            temp_ctx = PipelineContext(
                query=query, intent=intent, task=task,
                generation_query=generation_query,
                intent_hint=intent_hint,
                context_docs=context_docs,
                system_prompt=system_prompt,
                history=history,
                user_documents=user_documents,
                model_id=model_id,
            )
            response, trace_steps = loop.run(temp_ctx, model_id=model_id)
            tool_trace = [s.to_dict() for s in trace_steps]
            if loop.found_docs:
                retrieved_docs = merge_unique_docs(retrieved_docs, loop.found_docs)
                rag_used = True
        else:
            response = self.model.generate(
                generation_query,
                system_prompt=system_prompt,
                context_docs=context_docs,
                history=history,
                intent_hint=intent_hint,
                model_id=model_id,
            )
```

4) `run()` 末尾 return 字典追加三键：

```python
        return {
            ...
            "rag_used": rag_used,
            "task": task.to_dict() if task else None,
            "tool_trace": tool_trace,
        }
```

（`validity_evidence` 已由 `_run_validity` 分支返回；legal 路径不需要。）

- [ ] **Step 5: SSE 端点接入 agent 分支（main.py）**

`web/backend/main.py`：

1) `event_generator()` 中 meta 事件之后、非法律分支之后，把现有「parts = [] for chunk in generate_answer_stream…」段替换为：

```python
            # ---- 智能体工具模式：法律问答 + 工具可用（API 引擎） ----
            use_agent = (
                Config.AGENT_ENABLE_TOOLS
                and ctx.task is not None
                and ctx.task.task_type == "legal_qa"
                and _pipeline.model.supports_tools(spec.id)
            )
            if use_agent:
                from src.agents.agent_loop import AgentToolLoop
                from src.knowledge_base.retrieval_utils import merge_unique_docs

                loop = AgentToolLoop(
                    _pipeline.model, _pipeline.store,
                    validity=(_pipeline.verifier.validity if _pipeline.verifier else None),
                )
                parts = []
                for ev in loop.stream(ctx, model_id=spec.id):
                    if isinstance(ev, str):
                        parts.append(ev)
                        yield _sse_event("token", {"content": ev})
                    else:
                        yield _sse_event("agent_status", ev.to_dict())
                answer = "".join(parts)
                tool_trace = [s.to_dict() for s in loop.trace]
                if loop.found_docs:
                    ctx.retrieved_docs = merge_unique_docs(ctx.retrieved_docs, loop.found_docs)
                    ctx.rag_used = True
            else:
                parts = []
                for chunk in _pipeline.generate_answer_stream(ctx):
                    parts.append(chunk)
                    yield _sse_event("token", {"content": chunk})
                answer = "".join(parts)
                tool_trace = []
```

2) 该段之后的 done 事件（法律类）追加字段：

```python
            yield _sse_event(
                "done",
                {
                    "answer": answer,
                    "message_id": message_id,
                    "trust": partial_trust,
                    "model_id": spec.id,
                    "model_name": spec.display_name,
                    "task": ctx.task.to_dict() if ctx.task else None,
                    "validity_evidence": ctx.validity_evidence,
                    "tool_trace": tool_trace,
                },
            )
```

3) meta 事件已由 run_fast 的 meta 携带 `task` / `validity_evidence`（Task 3 第 5 步已加）。

- [ ] **Step 6: ChatResponse schema 追加可选字段**

`web/backend/schemas.py`，`ChatResponse` 末尾追加：

```python
    # 智能体：任务类型 / 工具调用轨迹 / 时效证据（同步降级路径返回）
    task: Optional[Dict[str, Any]] = None
    tool_trace: Optional[List[Dict[str, Any]]] = None
    validity_evidence: Optional[Dict[str, Any]] = None
```

- [ ] **Step 7: 运行测试**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/ -q`
Expected: 全部通过（新用例 + 旧用例无回归）。

- [ ] **Step 8: 集成验证（真实 API，分三场景）**

启动服务后：

1) **多法条问题触发工具**：`curl` 走 `/api/chat/stream`（或直接浏览器提问）「工伤认定申请时效和劳动仲裁时效分别是多少？」——Expected：SSE 出现 `agent_status` 事件（检索法条），done 事件 `tool_trace` 非空；回答为完整三段式。
2) **普通问题零回归**：「劳动合同解除需要提前多少天通知？」——Expected：无 agent_status、`tool_trace` 为空数组，回答与改造前一致。
3) **时效问题快路径**：「婚姻法现在还有效吗？」——Expected：meta 事件 `task.task_type == "validity_check"`，回答不套三段式。
4) **同步路径**：`/api/chat`（非流式）多法条问题——Expected：响应含 `tool_trace` 数组与 `task`。
验证后停服务。

- [ ] **Step 9: 提交**

```bash
git add src/pipeline/answer_pipeline.py src/knowledge_base/retrieval_utils.py web/backend/main.py web/backend/schemas.py tests/test_retrieval_merge.py
git commit -m "feat: 流水线与 SSE 集成智能体（agent_status 事件 + 工具轨迹返回）"
```

---

### Task 9: 前端 SSE agent_status 与生成中状态行

**Files:**
- Modify: `web/frontend/src/api/types.ts`
- Modify: `web/frontend/src/composables/useChatStream.ts`
- Modify: `web/frontend/src/views/ChatView.vue`
- Modify: `web/frontend/src/components/chat/ChatMessage.vue`

**Interfaces:**
- Consumes: 后端 SSE 事件（Task 8）：`agent_status` 事件、done 的 `tool_trace` / `task` / `validity_evidence`、meta 的 `task` / `validity_evidence`。
- Produces:
  - `types.ts`：`AgentStatusEvent`、`ToolTraceStep` 接口；`MessageMeta` 追加 `task_type` / `tool_trace` / `validity_evidence` / `agent_status`（瞬态）；`DoneEvent` 追加 `task_type` / `validity_evidence` / `tool_trace`；`SSEEventMap` 追加 `agent_status`
  - `useChatStream.ts`：`StreamCallbacks.onAgentStatus` 回调 + 事件分发
  - `ChatView.vue`：onAgentStatus 写入消息 meta；onMeta/onDone 落 task_type/tool_trace/validity_evidence；onDone 清理 agent_status
  - `ChatMessage.vue`：`message.meta.agent_status` 存在时渲染状态行

- [ ] **Step 1: 扩展类型定义**

`web/frontend/src/api/types.ts`：

1) `MessageMeta` 内 `model_name?: string` 之后追加：

```ts
  /** 任务类型（legal_qa / contract_review / validity_check） */
  task_type?: string
  /** 工具调用轨迹（智能体模式） */
  tool_trace?: ToolTraceStep[]
  /** 时效查询的确定性证据（validity_check 时存在） */
  validity_evidence?: Record<string, unknown> | null
  /** 瞬态：流式中的智能体状态（done 后清除） */
  agent_status?: AgentStatusEvent
```

2) `DoneEvent` 内 `model_name?: string` 之后追加：

```ts
  task_type?: string
  validity_evidence?: Record<string, unknown> | null
  tool_trace?: ToolTraceStep[]
```

3) `SSEEventMap` 内 `token: { content: string }` 之后追加：

```ts
  agent_status: AgentStatusEvent
```

4) 文件末尾（`VerificationError` 之后）追加两个接口：

```ts
export interface AgentStatusEvent {
  step: number
  tool_name?: string
  /** running | done | error | generating */
  status: string
  detail?: string
  result_summary?: string
}

export interface ToolTraceStep {
  step: number
  tool_name: string
  arguments: Record<string, unknown>
  result_summary: string
  success: boolean
  cost_ms: number
}
```

- [ ] **Step 2: useChatStream 分发 agent_status**

`web/frontend/src/composables/useChatStream.ts`：

1) import 追加：`import type { ..., AgentStatusEvent } from '@/api/types'`（在现有 `DoneEvent, MetaEvent` 后补 `AgentStatusEvent`）。

2) `StreamCallbacks` 接口追加：

```ts
  /** 智能体工具调用状态事件（running/done/error/generating） */
  onAgentStatus?: (s: AgentStatusEvent) => void
```

3) `runStream` 内事件分发追加（`token` 分支之后）：

```ts
      else if (event === 'agent_status') cb.onAgentStatus?.(data as AgentStatusEvent)
```

- [ ] **Step 3: ChatView 接线**

`web/frontend/src/views/ChatView.vue`：

1) `onMeta` 回调内 `meta` 对象追加：

```ts
              task_type: meta.task_type,
              validity_evidence: meta.validity_evidence,
```

（`MetaEvent` 类型需补 `task_type?: string` / `validity_evidence?` 字段——在 `types.ts` 的 `MetaEvent` 接口末尾追加与 DoneEvent 相同的两个可选字段。）

2) `onMeta` 之后新增回调：

```ts
        onAgentStatus: (s) => {
          const m = sessions.currentSession?.messages.find((x) => x.id === assistantMsgId)
          if (m) m.meta = { ...(m.meta || {}), agent_status: s }
        },
```

3) `onDone` 的每个分支（non_legal / trust / else）构造 `patch.meta` 时统一追加清空与落盘：

```ts
              agent_status: undefined,
              task_type: done.task_type,
              validity_evidence: done.validity_evidence,
              tool_trace: done.tool_trace,
```

（三个分支的 `patch.meta` 对象各加这四行。）

4) `onFallback`（同步降级路径）中 patch meta 的位置同样追加：

```ts
              agent_status: undefined,
              task_type: data.task_type,
              validity_evidence: data.validity_evidence,
              tool_trace: data.tool_trace,
```

（`data` 为 `Record<string, unknown>`，直接取值；同步路径字段已由 Task 8 的 ChatResponse 提供。）

- [ ] **Step 4: ChatMessage 渲染状态行**

`web/frontend/src/components/chat/ChatMessage.vue`，在回答内容（AnswerContent / ThinkingBubble）上方、模板中合适位置插入：

```vue
    <!-- 智能体工具调用状态（流式期间实时更新，done 后消失） -->
    <div
      v-if="message.meta?.agent_status"
      class="mb-2 flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-[12px] text-muted"
    >
      <span class="text-brand-500">
        {{ message.meta.agent_status.status === 'running' ? '●' : '✓' }}
      </span>
      <span v-if="message.meta.agent_status.status === 'running'">
        {{ message.meta.agent_status.detail || '智能体思考中…' }}
      </span>
      <span v-else-if="message.meta.agent_status.status === 'generating'">
        {{ message.meta.agent_status.detail || '综合生成最终回答…' }}
      </span>
      <span v-else :class="message.meta.agent_status.status === 'error' ? 'text-danger' : 'text-success'">
        {{ message.meta.agent_status.result_summary || '工具调用完成' }}
      </span>
    </div>

    <!-- 时效查询来源标注（确定性结论来自注册表） -->
    <div
      v-if="message.meta?.validity_evidence"
      class="mb-2 inline-flex items-center gap-1 rounded border border-line bg-page px-2 py-0.5 text-[11px] text-muted"
      title="结论事实来自法律时效注册表，非模型生成"
    >
      <span class="text-brand-500">◈</span>
      <span>来源：法律时效注册表</span>
    </div>
```

（若该组件模板结构是 `v-for` 渲染整条消息，直接加在气泡内容容器内即可；`text-success` / `text-danger` / `text-brand-500` / `border-line` / `bg-surface` 均为项目已有 token。）

- [ ] **Step 5: 构建验证**

Run（在 `web/frontend` 目录）：`npm run build`
Expected: vue-tsc 零类型错误，新产物 dist 生成（服务端静态目录实时读盘，无需重启后端）。

- [ ] **Step 6: 手工验证**

浏览器 `http://localhost:6006`（后端已启动），提问「工伤认定申请时效和劳动仲裁时效分别是多少？」：
Expected: 回答流式出现前，气泡上方短暂显示「● 正在检索法条：…（《…》）」→「✓ 命中 N 条法条」；回答完成后状态行消失。提问「你好」：不出现状态行。提问「婚姻法现在还有效吗？」：回答上方出现「◈ 来源：法律时效注册表」小标注（hover 显示说明）。

- [ ] **Step 7: 提交**

```bash
git add web/frontend/src/api/types.ts web/frontend/src/composables/useChatStream.ts web/frontend/src/views/ChatView.vue web/frontend/src/components/chat/ChatMessage.vue web/frontend/dist
git commit -m "feat: 前端 agent_status 事件与工具调用状态行"
```

---

### Task 10: 工具轨迹面板与合同核验展示

**Files:**
- Create: `web/frontend/src/components/detail/ToolTracePanel.vue`
- Modify: `web/frontend/src/components/detail/DetailBody.vue`
- Modify: `web/frontend/src/components/detail/CitationVerificationPanel.vue`

**Interfaces:**
- Consumes: `MessageMeta.tool_trace` / `MessageMeta.task_type`（Task 9）、`citation_verification.document_quote_checks`（Task 4）。
- Produces: 详情面板「工具轨迹」tab；引用核验面板的文档引文核验结果区。

- [ ] **Step 1: 新建 ToolTracePanel.vue**

`web/frontend/src/components/detail/ToolTracePanel.vue`：

```vue
<script setup lang="ts">
import type { ToolTraceStep } from '@/api/types'

defineProps<{ steps: ToolTraceStep[] }>()
</script>

<template>
  <div class="space-y-3">
    <div v-if="!steps.length" class="px-1 pt-10 text-center text-[12px] text-muted">
      本次回答未调用工具
    </div>
    <div
      v-for="s in steps"
      :key="`${s.step}-${s.tool_name}`"
      class="rounded-xl border border-line bg-surface p-3"
    >
      <div class="flex items-center gap-2 text-[12px]">
        <span class="font-medium text-ink">第 {{ s.step }} 轮</span>
        <span class="rounded bg-page px-1.5 py-0.5 font-medium text-brand-500">{{ s.tool_name }}</span>
        <span :class="s.success ? 'text-success' : 'text-danger'">
          {{ s.success ? '✓ 成功' : '✗ 失败' }}
        </span>
        <span class="ml-auto text-muted">{{ s.cost_ms }} ms</span>
      </div>
      <div v-if="Object.keys(s.arguments).length" class="mt-2 break-all text-[11px] text-muted">
        参数：{{ JSON.stringify(s.arguments) }}
      </div>
      <div class="mt-1 text-[12px] text-muted">{{ s.result_summary }}</div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: DetailBody 接入「工具轨迹」tab**

`web/frontend/src/components/detail/DetailBody.vue`：

1) import 追加：`import ToolTracePanel from './ToolTracePanel.vue'`
2) tabs 区（`<n-tab-pane name="verification" tab="引用核验" />` 之后）追加：

```vue
      <n-tab-pane v-if="meta.tool_trace?.length" name="trace" tab="工具轨迹" />
```

3) 内容区（`CitationVerificationPanel` 的 `v-else` 之后、`</div>` 前）追加：

```vue
      <ToolTracePanel
        v-else-if="detail.activeTab === 'trace'"
        :steps="meta.tool_trace || []"
      />
```

（注意顺序：现有 `v-if trust / v-else-if articles / v-else verification`，改为 `v-if trust / v-else-if articles / v-else-if trace / v-else verification`，保证 verification 仍是兜底。）

- [ ] **Step 3: 引用核验面板展示文档引文核验结果**

`web/frontend/src/components/detail/CitationVerificationPanel.vue`：

1) script 区追加 computed：

```ts
const docQuotes = computed(() => props.verification?.document_quote_checks || [])
```

（`CitationVerification` 接口在 `types.ts` 中追加 `document_quote_checks?: { text: string; found: boolean; verdict: string; in_document: boolean }[]`。）

2) 模板中「无数据」判断改为同时考虑 docQuotes，并在显式引用卡片列表之后追加区块：

```vue
  <!-- 文档引文核验（合同审查） -->
  <div v-if="docQuotes.length" class="space-y-2">
    <div class="text-[12px] font-semibold text-ink">文档引文核验</div>
    <div
      v-for="(q, i) in docQuotes" :key="`dq-${i}`"
      class="rounded-xl border bg-surface p-3"
      :class="q.verdict === 'verified' ? 'border-line' : 'border-warning/40'"
    >
      <div class="text-[12px] text-ink">{{ q.text }}</div>
      <div class="mt-1 text-[11px] font-semibold" :class="q.verdict === 'verified' ? 'text-success' : 'text-warning'">
        {{ q.verdict === 'verified' ? '✓ 与上传文档原文一致' : '⚠ 上传文档中未找到此内容' }}
      </div>
    </div>
  </div>
```

- [ ] **Step 4: 构建验证**

Run（在 `web/frontend` 目录）：`npm run build`
Expected: vue-tsc 零类型错误。

- [ ] **Step 5: 手工验证**

浏览器回归：
1) 提问多法条问题（触发工具）→ 回答完成后右侧详情面板出现「工具轨迹」tab，展开可见每轮工具名/参数/结果摘要/耗时。
2) 上传合同 + 「这份合同有什么风险条款？」→ 回答完成后「引用核验」tab 出现「文档引文核验」区块；若模型引用了文档原文显示「✓ 与上传文档原文一致」。
3) 普通问题 → 无「工具轨迹」tab（v-if 隐藏）。

- [ ] **Step 6: 提交**

```bash
git add web/frontend/src/components/detail/ web/frontend/dist
git commit -m "feat: 工具轨迹面板与文档引文核验展示"
```

---

### Task 11: 效果对比评测（benchmark 数据集 + 脚本扩展）

**Files:**
- Create: `data/benchmark/agent_compare.json`
- Modify: `scripts/run_legal_trust_benchmark.py`

**Interfaces:**
- Consumes: `AnswerPipeline.run(agent_tools=...)`（Task 8）。
- Produces: 对比数据集（10 题）+ 脚本 `--mode agent`（完整流水线 + 工具调用）；输出行含 `tool_call_count` / `elapsed_ms`，summary 含 `avg_tool_calls`。

- [ ] **Step 1: 创建对比数据集**

`data/benchmark/agent_compare.json`：

```json
[
  {"id": "ac01", "prompt": "工伤认定的申请时效是多久？", "gold_law": "工伤保险条例", "gold_article": "第十七条", "answer": "30日内提出工伤认定申请"},
  {"id": "ac02", "prompt": "劳动仲裁时效与普通诉讼时效有什么区别？", "gold_law": "劳动争议调解仲裁法", "gold_article": "第二十七条", "answer": "仲裁时效一年"},
  {"id": "ac03", "prompt": "婚姻法现在还有效吗？", "gold_law": "", "gold_article": "", "answer": "已废止，由民法典吸收"},
  {"id": "ac04", "prompt": "合同法废止后相关合同纠纷看什么法律？", "gold_law": "", "gold_article": "", "answer": "民法典合同编"},
  {"id": "ac05", "prompt": "试用期工资不得低于多少？", "gold_law": "劳动合同法", "gold_article": "第二十条", "answer": "不得低于约定工资的百分之八十"},
  {"id": "ac06", "prompt": "用人单位单方解除劳动合同需要提前多久通知？", "gold_law": "劳动合同法", "gold_article": "第四十条", "answer": "提前三十日书面通知"},
  {"id": "ac07", "prompt": "担保法还有效吗？民间借贷的担保适用什么规定？", "gold_law": "", "gold_article": "", "answer": "担保法已废止，适用民法典"},
  {"id": "ac08", "prompt": "交通事故赔偿与工伤赔偿能同时主张吗？", "gold_law": "", "gold_article": "", "answer": "可以，分别按侵权与工伤主张"},
  {"id": "ac09", "prompt": "民间借贷利率的合法上限是多少？", "gold_law": "民法典", "gold_article": "第六百八十条", "answer": "不得超过合同成立时一年期贷款市场报价利率四倍"},
  {"id": "ac10", "prompt": "连续工作满十年可以要求签订无固定期限劳动合同吗？", "gold_law": "劳动合同法", "gold_article": "第十四条", "answer": "可以"}
]
```

- [ ] **Step 2: 扩展脚本**

`scripts/run_legal_trust_benchmark.py`：

1) `p.add_argument("--mode", choices=["full", "rag", "no_rag", "agent"], ...)`（choices 追加 `"agent"`）。

2) `run()` 中：

```python
    use_tools = args.mode == "agent"
```
并在非 mock 分支的 `pipeline.run(...)` 调用追加参数 `agent_tools=use_tools`；用 `time.perf_counter()` 包住 `pipeline.run` 计时：

```python
        else:
            use_rag = args.mode != "no_rag"
            t0 = time.perf_counter()
            out = pipeline.run(
                prompt,
                use_rag=use_rag,
                enable_consistency=False,
                max_regeneration=0 if args.mode == "rag" else Config.MAX_REGENERATION_ATTEMPTS,
                agent_tools=use_tools,
            )
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
            response = out["answer"]
            verification = out["citation_verification"]
            trust = out["trust"]
```

3) rows 追加（两个分支都加）：

```python
        rows.append({
            ...
            "tool_call_count": len(out.get("tool_trace") or []) if not args.mock else 0,
            "elapsed_ms": elapsed_ms if not args.mock else 0,
        })
```

（mock 分支定义 `elapsed_ms = 0`。）

4) trust 判空保护（validity_check 题目的 `trust` 为 None——不评分不核验，必须跳过，否则 `trust["dimensions"]` 崩溃）：

rows 追加处改为：

```python
        trust_scores.append((trust or {}).get("overall_score"))
        rows.append({
            "id": item.get("id"),
            "prompt": prompt,
            "response": response[:500],
            "trust_overall": (trust or {}).get("overall_score"),
            "trust_dimensions": (trust or {}).get("dimensions"),
            "citation_score": verification.get("overall_citation_score"),
            "tool_call_count": len(out.get("tool_trace") or []) if not args.mock else 0,
            "elapsed_ms": elapsed_ms if not args.mock else 0,
        })
```

（原 `"trust_overall": trust["overall_score"]` / `"trust_dimensions": trust["dimensions"]` 两行按上替换；mock 分支在 `if args.mock:` 内先定义 `elapsed_ms = 0` 与 `out = {}`。）

summary 的 avg_trust_score 与 `_avg_radar` 改为过滤 None：

```python
    valid_scores = [s for s in trust_scores if s is not None]
    summary = {
        "mode": args.mode,
        "dataset": args.dataset,
        "mock": args.mock,
        "count": n,
        "avg_trust_score": round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0,
        "avg_radar": _avg_radar(rows),
    }
```

`_avg_radar` 函数体改为：

```python
def _avg_radar(rows: list) -> dict:
    dims = [r.get("trust_dimensions") for r in rows if r.get("trust_dimensions")]
    if not dims:
        return {}
    keys = dims[0].keys()
    out = {}
    for k in keys:
        vals = [d[k] for d in dims if k in d]
        out[k] = round(sum(vals) / len(vals), 2) if vals else 0
    return out
```

5) summary 追加（agent 模式的工具调用统计）：

```python
    if args.mode == "agent":
        summary["avg_tool_calls"] = round(sum(r["tool_call_count"] for r in rows) / n, 2) if n else 0
```

（顶部 `import argparse` 之后追加 `import time`。）

- [ ] **Step 3: mock 模式冒烟**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe scripts/run_legal_trust_benchmark.py --mode agent --dataset agent_compare --mock --output data/benchmark/mock_agent_report.json`
Expected: 脚本跑通，输出 summary（avg_tool_calls = 0，mock 不跑工具），报告文件生成。

- [ ] **Step 4: 真实模式对比跑（API）**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe scripts/run_legal_trust_benchmark.py --mode full --dataset agent_compare --output data/benchmark/report_full.json`
然后：`... --mode agent --dataset agent_compare --output data/benchmark/report_agent.json`
Expected: 两份报告生成；agent 版含 `avg_tool_calls > 0`（多法条题触发工具）；对比 full vs agent 的 avg_trust_score / gold_citation_recall（答辩数据素材）。

- [ ] **Step 5: 提交**

```bash
git add data/benchmark/agent_compare.json scripts/run_legal_trust_benchmark.py data/benchmark/report_full.json data/benchmark/report_agent.json
git commit -m "feat: 智能体效果对比评测（agent_compare 数据集 + --mode agent）"
```

---

### Task 12: 文档收尾（指南 / 架构说明 / 进度表 / 修改日志）

**Files:**
- Modify: `docs/项目改进指南.txt`（8.4 / 8.5 / 8.7 / 8.8 章节按设计定稿）
- Create: `docs/智能体架构说明.txt`
- Modify: `CLAUDE.md`（阶段八进度表）
- Modify: `docs/修改日志.txt`（追加本次记录）
- Modify: `docs/律策智枢_LawPilot_项目介绍.txt`（若其中列出了 docs 文件清单，同步追加）

- [ ] **Step 1: 更新指南 8.4 / 8.5**

`docs/项目改进指南.txt`：
- 8.4 章节替换为「任务调度器」设计（3 类任务 + 触发规则 + 回退安全；合同审查 / 时效查询管线描述；复杂推理并入工具调用，不单设管线）。
- 8.5 章节替换为「务实版工具调用」设计（2 个工具：检索法条 / 查询时效；循环上限 3 轮；SSE agent_status 事件；本地 7B 降级；工具结果并入核验视野）。
- 8.7 验收标准追加本实现的验收项（agent_status 事件、tool_trace 返回、合同风险清单结构、时效快路径、工具轨迹面板）。
- 8.8 实施顺序更新为「主线已完成 → 编排与工具调用已完成」。

（具体文本按 `docs/superpowers/specs/2026-08-10-agent-features-design.md` 第 4/5/6/7 节改写，保持指南的「文字化描述」风格，不含大段代码。）

- [ ] **Step 2: 新增架构说明文档**

创建 `docs/智能体架构说明.txt`，包含：
1. 一句话定位：「可信智能体——AI 可自主调用工具，但每一步都被核验」。
2. 任务分派流程图（ASCII，同设计文档第 3 节）。
3. 设计决策 6 条（每条「为什么」）：确定性规则分类 / 回退安全 / 工具集收敛 2 个 / 循环上限 3 轮 / 本地 7B 不启用函数调用 / 不做模型自动路由。
4. 答辩 Q&A 8 问（示例：「为什么不用大模型做任务分类？」→ 快、稳、便宜、可解释、可回退；「工具结果如何保证可信？」→ 工具只跑本地、结果只作参考、最终引用仍过核验闭环；「工具循环会不会死循环/烧钱？」→ 3 轮上限 + 每轮 token 上限；等）。
5. 评测结论区（占位表格，引用 Task 11 的对比数据）。

- [ ] **Step 3: 更新 CLAUDE.md 进度表**

`CLAUDE.md` 阶段八行更新为：

```
| 八 | 架构升级（LLM 抽象层 + 多模型注册表 + 用户可控选择） | 主线已完成（7 模型切换/Auto/离线置灰）；8.4 任务编排（合同审查/时效查询管线）与 8.5 工具调用（2 工具+轨迹）已完成；8.6 统计暂缓 |
```

- [ ] **Step 4: 追加修改日志**

`docs/修改日志.txt` 顶部追加：

```
===== 2026-08-10 =====
类型：新增功能
内容：智能体（Agent）能力落地——任务调度器（合同审查管线输出结构化风险清单 + 文档引文核验；时效查询管线直查注册表出确定性结论）；工具调用引擎（检索法条 / 查询时效 2 个工具，循环上限 3 轮，SSE agent_status 状态事件，前端工具轨迹面板）；effect 对比评测（--mode agent）
涉及文件：src/agents/（task_scheduler/tools/agent_loop/trace）、src/llm/（base/api_client/qwen_model）、src/pipeline/answer_pipeline.py、src/citation_verifier/（document_quotes + verify 扩展）、web/backend/（main.py/schemas.py）、web/frontend/（types/useChatStream/ChatView/ChatMessage/ToolTracePanel/DetailBody/CitationVerificationPanel）、scripts/run_legal_trust_benchmark.py、data/benchmark/agent_compare.json
验证：pytest 全绿；npm run build 零类型错误；三类问题（多法条/合同/时效）真实 API 集成验证通过；对比报告产出
```

- [ ] **Step 5: 同步项目介绍**

检查 `docs/律策智枢_LawPilot_项目介绍.txt` 是否列出 docs 文件清单（如「文档（项目介绍 / 竞赛改进方案 / 修改日志）」的列举形式），若有则把 `智能体架构说明.txt` 加入清单；README.md 若有同样列举同步处理。

- [ ] **Step 6: 全量回归与提交**

Run: `C:\Users\75806\.conda\envs\LawTrust\python.exe -m pytest tests/ -q` → 全绿
Run（web/frontend）: `npm run build` → 零类型错误
Run: 启动服务后浏览器快速回归（寒暄 / 普通法律问答 / 合同审查 / 时效查询 / 多法条工具问题 5 场景）

```bash
git add docs/ CLAUDE.md
git commit -m "docs: 智能体功能文档收尾（指南 8.4/8.5 定稿、架构说明、进度表、修改日志）"
```

---

## Self-Review 记录（写完后自查，发现问题当场修正）

1. **Spec 覆盖**：设计文档第 4 节（调度器）→ Task 2；第 4.2 ②③（合同/时效管线）→ Task 3/4；第 5 节（工具引擎）→ Task 5/6/7；第 5.4（SSE）→ Task 8；第 6 节（前端）→ Task 9/10；第 7 节（核验闭环与安全）→ Task 4（文档引文核验）+ Task 8（found_docs 并入核验）+ 循环上限/降级（Task 7）；第 8 节（文档答辩支撑）→ Task 11/12。
2. **占位符**：无 TBD/TODO；所有代码块为可直接落盘的实现。
3. **类型一致性**：`ToolDecision.text` / `.tool_calls`、`ToolTraceStep` / `AgentStatusEvent.to_dict()` 键名在 Task 1/7/8/9 间一致；`classify_task` 返回值字段 `task_type`/`law_name` 在 Task 2/3 一致；`pipeline.run(agent_tools=...)` 在 Task 8 定义、Task 11 使用。
