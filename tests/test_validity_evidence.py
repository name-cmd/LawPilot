"""时效证据构造单测：确定性结论来自注册表。"""
import json
import tempfile
from pathlib import Path

from src.knowledge_base.law_validity import LawValidityService, build_validity_evidence


def _service_with(registry: dict) -> LawValidityService:
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "law_registry.json"
    p.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    svc = LawValidityService(registry_path=str(p))
    # 注册表为懒加载：不先读一次的话，_service_with 返回后局部变量 d（临时目录）
    # 会被 GC 回收并删除目录，导致 svc 读到空注册表（本环境已复现该现象）。
    _ = svc.registry
    return svc


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
