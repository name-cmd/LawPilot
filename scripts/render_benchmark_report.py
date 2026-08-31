#!/usr/bin/env python3
"""汇总 docs/competition/ 下的评测报告，渲染 PNG 图表到 docs/figure/（matplotlib）。

产出（对照 docs/技术效果对比与数据处理改进方案.txt 1.5 节）：
  fig0_指标总览表.png        消融模式 × 核心指标（默认模型 qwen3.7-plus）
  fig1_六维可信雷达.png      六维可信雷达（四模式重叠，30 题平均，与 Web 端同一打分器）
  fig2_系统消融对比.png      消融对比柱状图（no_rag / rag / full / agent）
  fig3_成本效果对比.png      成本-效果双面板横向条形图（7 模型，按信任分排序）
  fig4_模型指标热力图.png    模型×指标热力图（含行/列名与数值标注）
  fig5_检索命中率.png        检索命中率分组柱状图（Hit@1/3/5 + retrieval_gold 基线）

数据口径说明：
  - 消融类图表（fig0/2/5）仅取默认模型（Config.DEFAULT_API_MODEL）的四个模式报告，
    避免多模型 full 报告混入导致"完整流水线"重复（旧版 HTML 报告的 bug）。
  - retrieval_gold 基线去重后仅显示一次。

用法：
    python scripts/render_benchmark_report.py                 # 自动选最新一轮报告
    python scripts/render_benchmark_report.py --date 20260825 # 指定日期前缀
    python scripts/render_benchmark_report.py --out-dir docs/figure
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import Config

COMP_DIR = Config.BASE_DIR / "docs" / "competition"
FIG_DIR = Config.BASE_DIR / "docs" / "figure"

MODES = ["no_rag", "rag", "full", "agent"]
MODE_LABEL = {"no_rag": "无RAG基线", "rag": "仅RAG", "full": "完整流水线", "agent": "Agent工具"}
DIM_LABEL = {
    "truthfulness": "真实性",
    "safety": "安全性",
    "fairness": "公平性",
    "robustness": "鲁棒性",
    "privacy": "隐私保护",
    "ethics": "伦理合规",
}
HEAT_METRICS = [
    ("answer_match_rate", "答案匹配率"),
    ("gold_citation_recall", "引用召回率"),
    ("avg_faithfulness", "忠实度"),
    ("hit_at_5", "Hit@5"),
    ("mrr", "MRR"),
    ("avg_trust_score", "信任分(÷100)"),
]

MODE_COLORS = {"no_rag": "#94a3b8", "rag": "#60a5fa", "full": "#2563eb", "agent": "#7c3aed"}

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------- 数据加载
def load_reports(date: str = None) -> list:
    """加载竞赛目录下的报告；默认取每个 (model, mode, dataset) 组合最新的一份。"""
    files = sorted(COMP_DIR.glob("benchmark_*.json"))
    if date:
        files = [f for f in files if f.name.startswith(f"benchmark_{date}")]
    groups = {}
    for f in files:
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        s = rep.get("summary", {})
        if s.get("mock"):
            continue
        key = (s.get("model"), s.get("mode"), s.get("dataset"))
        groups[key] = (f.name, rep)  # sorted 顺序保证同名后者（较新）覆盖
    return [{"file": fn, **rep} for fn, rep in groups.values()]


def pick(reports, mode=None, dataset="legal_qa_gold", model=None):
    out = []
    for r in reports:
        s = r["summary"]
        if dataset and s.get("dataset") != dataset:
            continue
        if mode and s.get("mode") != mode:
            continue
        if model and s.get("model") != model:
            continue
        out.append(r)
    return out


def select_ablation(reports, model: str) -> list:
    """消融序列：仅默认模型的四个模式，每模式至多一份。"""
    out = []
    for m in MODES:
        out.extend(pick(reports, mode=m, model=model)[:1])
    return out


def _save(fig, name: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  saved: {path}")
    return path


def _title(fig, main: str, sub: str, main_y: float = 0.98, sub_y: float = 0.925):
    fig.suptitle(main, fontsize=15, fontweight="bold", y=main_y)
    fig.text(0.5, sub_y, sub, ha="center", fontsize=9.5, color="#555555")


# ---------------------------------------------------------------- fig0 总览表
def fig0_overview(ablation, model: str, out_dir: Path):
    cols = ["模式", "答案匹配率", "引用召回", "忠实度",
            "信任分", "平均耗时(ms)", "估算成本(元)", "重生成率"]
    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"
    num = lambda v: "—" if v is None else v
    rows = []
    for r in ablation:
        s = r["summary"]
        rows.append([
            MODE_LABEL.get(s["mode"], s["mode"]),
            pct(s.get("answer_match_rate")), pct(s.get("gold_citation_recall")),
            pct(s.get("avg_faithfulness")),
            num(s.get("avg_trust_score")), num(s.get("avg_elapsed_ms")),
            num(s.get("est_cost_yuan")), pct(s.get("regeneration_rate")),
        ])
    fig, ax = plt.subplots(figsize=(12, 2.2 + 0.5 * len(rows)))
    ax.axis("off")
    ax.set_position([0.01, 0.02, 0.98, 0.72])  # 顶部留出标题/副标题空间
    table = ax.table(cellText=rows, colLabels=cols, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10.5)
    table.scale(1, 1.7)
    for j in range(len(cols)):
        table[0, j].set_facecolor("#1e3c72")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows) + 1):
        for j in range(len(cols)):
            table[i, j].set_facecolor("#f5f8ff" if i % 2 else "white")
    _title(fig, "指标总览：消融模式 × 核心指标",
           f"模型：{model} · 30 道法律问答 gold 题 · 对比四种流水线模式，"
           f"说明每一环节（检索 / 引用核验 / Agent 工具）的增量价值",
           main_y=0.97, sub_y=0.845)
    return _save(fig, "fig0_指标总览表.png", out_dir)


# ---------------------------------------------------------------- fig1 雷达（多模型对比）
def fig1_radar(models, out_dir: Path):
    with_radar = [r for r in models
                  if r["summary"].get("avg_radar") and len(r["summary"]["avg_radar"]) > 0]
    if not with_radar:
        print("  fig1: 无雷达数据，跳过")
        return None
    dims = list(with_radar[0]["summary"]["avg_radar"].keys())
    labels = [DIM_LABEL.get(d, d) for d in dims]
    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    angles += angles[:1]

    cmap = plt.get_cmap("tab10")
    fig, ax = plt.subplots(figsize=(7.5, 7.2), subplot_kw={"polar": True})
    for i, r in enumerate(with_radar):
        s = r["summary"]
        vals = [s["avg_radar"][d] for d in dims]
        vals += vals[:1]
        color = cmap(i % 10)
        ax.plot(angles, vals, linewidth=2, label=s["model"], color=color)
        ax.fill(angles, vals, alpha=0.05, color=color)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="#888")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=4, fontsize=9.5)
    _title(fig, "六维可信雷达（多模型对比）",
           f"完整流水线模式 · 30 题平均 · 与 Web 端同一 LegalTrustScorer 打分器 · "
           f"真实性 = 引用核验准确率(60%)+自一致性(40%)，其余五维为规则检测"
           f"（多模型间差异集中于真实性维度）")
    return _save(fig, "fig1_六维可信雷达.png", out_dir)


# ---------------------------------------------------------------- fig2 消融柱状
def fig2_ablation(ablation, model: str, out_dir: Path):
    if not ablation:
        print("  fig2: 无消融数据，跳过")
        return None
    labels = [MODE_LABEL.get(r["summary"]["mode"], r["summary"]["mode"]) for r in ablation]
    metrics = [
        ("答案匹配率", "answer_match_rate", 1),
        ("引用召回率", "gold_citation_recall", 1),
        ("忠实度", "avg_faithfulness", 1),
        ("信任分÷100", "avg_trust_score", 100),
    ]
    x = np.arange(len(labels))
    width = 0.2
    colors = ["#2563eb", "#16a34a", "#d97706", "#7c3aed"]
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for i, ((name, key, div), c) in enumerate(zip(metrics, colors)):
        vals = []
        for r in ablation:
            v = r["summary"].get(key)
            vals.append(None if v is None else v / div)
        pos = x + (i - 1.5) * width
        bars = ax.bar(pos, [v if v is not None else 0 for v in vals],
                      width, label=name, color=c)
        for b, v in zip(bars, vals):
            if v is not None:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015,
                        f"{v:.2f}", ha="center", fontsize=8, color="#333")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("得分（0~1）")
    ax.legend(fontsize=9.5, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.0))
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    _title(fig, "系统消融对比：每一环的增量价值",
           f"模型：{model} · 对比 无RAG → 仅RAG → 完整流水线(引用核验+重生成) → Agent工具，"
           f"说明检索与核验闭环对答案质量与可信度的贡献")
    return _save(fig, "fig2_系统消融对比.png", out_dir)


# ---------------------------------------------------------------- fig3 成本-效果
def fig3_cost_effect(models, out_dir: Path):
    if not models:
        print("  fig3: 无多模型数据，跳过")
        return None
    rows = []
    for r in models:
        s = r["summary"]
        cost_per_q = s["est_cost_yuan"] / s["count"] if s.get("count") else 0
        rows.append((s["model"], cost_per_q, s.get("avg_trust_score") or 0))
    rows.sort(key=lambda t: t[2])  # 信任分升序，画图时从上到下即降序
    names = [t[0] for t in rows]
    costs = [t[1] for t in rows]
    trusts = [t[2] for t in rows]
    y = np.arange(len(names))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 0.75 * len(names) + 1.8),
                                   sharey=True, gridspec_kw={"width_ratios": [1, 1]})
    b1 = ax1.barh(y, costs, color="#d97706", height=0.6)
    ax1.set_xlabel("单题成本（元）")
    ax1.set_yticks(y)
    ax1.set_yticklabels(names, fontsize=10.5)
    for b, v in zip(b1, costs):
        ax1.text(b.get_width() + max(costs) * 0.01, b.get_y() + b.get_height() / 2,
                 f"{v:.4f}", va="center", fontsize=9, color="#333")
    ax1.set_xlim(0, max(costs) * 1.18)

    tmin, tmax = min(trusts), max(trusts)
    pad = max((tmax - tmin) * 0.25, 1.5)
    b2 = ax2.barh(y, trusts, color="#2563eb", height=0.6)
    ax2.set_xlabel("综合信任分（0~100）")
    ax2.set_xlim(tmin - pad, tmax + pad * 1.6)
    ax2.axvline(80, color="#dc2626", linestyle="--", linewidth=1, alpha=0.6)
    ax2.text(80, len(names) - 0.3, " 80 分线", color="#dc2626", fontsize=8.5, va="bottom")
    for b, v in zip(b2, trusts):
        ax2.text(b.get_width() + pad * 0.05, b.get_y() + b.get_height() / 2,
                 f"{v:.2f}", va="center", fontsize=9, color="#333")

    for ax in (ax1, ax2):
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)
    fig.subplots_adjust(wspace=0.06)
    _title(fig, "成本-效果对比：多模型选型",
           "完整流水线模式 · 30 题 · 左：单题估算成本（越低越好） 右：综合信任分（越高越好）"
           " · 按信任分排序，直观读出性价比")
    return _save(fig, "fig3_成本效果对比.png", out_dir)


# ---------------------------------------------------------------- fig4 热力图
def fig4_heatmap(models, out_dir: Path):
    if not models:
        print("  fig4: 无多模型数据，跳过")
        return None
    names = [r["summary"]["model"] for r in models]
    mets = HEAT_METRICS
    data = np.full((len(names), len(mets)), np.nan)
    for i, r in enumerate(models):
        s = r["summary"]
        for j, (key, _) in enumerate(mets):
            v = s.get(key)
            if key == "avg_trust_score" and v is not None:
                v = v / 100
            if v is not None:
                data[i, j] = v

    fig, ax = plt.subplots(figsize=(9.5, 0.7 * len(names) + 2.2))
    im = ax.imshow(data, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(mets)))
    ax.set_xticklabels([m[1] for m in mets], fontsize=10.5)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=10.5)
    ax.xaxis.set_ticks_position("top")
    for i in range(len(names)):
        for j in range(len(mets)):
            v = data[i, j]
            txt = "—" if np.isnan(v) else f"{v:.3f}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=9.5,
                    color="#333333")
    ax.set_xticks(np.arange(-0.5, len(mets)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(names)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.03)
    cbar.set_label("归一化得分（0~1，越绿越好）", fontsize=9)
    _title(fig, "模型 × 指标热力图",
           "完整流水线模式 · 30 题 · 行=模型，列=指标（信任分已 ÷100 归一化）· "
           "横向比较各模型在不同指标上的强弱")
    return _save(fig, "fig4_模型指标热力图.png", out_dir)


# ---------------------------------------------------------------- fig5 检索命中率
def fig5_retrieval_hit(ablation, retrieval_reports, model: str, out_dir: Path):
    cats, h1, h3, h5 = [], [], [], []
    for r in ablation:  # ablation 已是默认模型四模式（每模式一份）
        s = r["summary"]
        if s.get("hit_at_1") is None:
            continue
        cats.append(MODE_LABEL.get(s["mode"], s["mode"]))
        h1.append(s["hit_at_1"]); h3.append(s["hit_at_3"]); h5.append(s["hit_at_5"])
    if retrieval_reports:  # 去重后取第一份
        s = retrieval_reports[0]["summary"]
        cats.append(f"retrieval_gold\n纯检索基线({s.get('count', '')}题)")
        h1.append(s.get("hit_at_1") or 0)
        h3.append(s.get("hit_at_3") or 0)
        h5.append(s.get("hit_at_5") or 0)
    if not cats:
        print("  fig5: 无检索数据，跳过")
        return None

    x = np.arange(len(cats))
    width = 0.25
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for i, (name, vals, c) in enumerate([
            ("Hit@1", h1, "#93c5fd"), ("Hit@3", h3, "#3b82f6"), ("Hit@5", h5, "#1e40af")]):
        bars = ax.bar(x + (i - 1) * width, vals, width, label=name, color=c)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015,
                    f"{v * 100:.0f}%", ha="center", fontsize=8.5, color="#333")
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=10.5)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("命中率")
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    _title(fig, "检索命中率（A 组）",
           f"模型：{model}（检索器与模式相关，与生成模型无关）· "
           f"Hit@k = gold 法条进入前 k 条结果的比例 · 对比三种含检索模式与纯检索基线")
    return _save(fig, "fig5_检索命中率.png", out_dir)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="报告日期前缀，如 20260825；默认全部批次取最新")
    p.add_argument("--out-dir", default=str(FIG_DIR), help="PNG 输出目录")
    args = p.parse_args()

    reports = load_reports(args.date)
    if not reports:
        print(f"未找到评测报告：{COMP_DIR}/benchmark_*.json")
        sys.exit(1)

    model = Config.DEFAULT_API_MODEL
    ablation = select_ablation(reports, model)
    models = pick(reports, mode="full")
    retrieval = pick(reports, dataset="retrieval_gold")
    out_dir = Path(args.out_dir)

    print(f"纳入报告 {len(reports)} 份，消融基线模型：{model}")
    fig0_overview(ablation, model, out_dir)
    fig1_radar(models, out_dir)
    fig2_ablation(ablation, model, out_dir)
    fig3_cost_effect(models, out_dir)
    fig4_heatmap(models, out_dir)
    fig5_retrieval_hit(ablation, retrieval, model, out_dir)
    print("完成。")


if __name__ == "__main__":
    main()
