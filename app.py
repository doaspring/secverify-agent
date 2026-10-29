"""SecVerify Agent — Streamlit UI（深色SOC科技风版）.

Five areas per spec §12 + explicit scenario selection feedback.
All dynamic text inserted into HTML is escaped (untrusted log content never
gets raw HTML injection - that would be our own app practicing what it preaches).
"""
from __future__ import annotations

import html as html_mod
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from secverify.config import settings
from secverify.schemas import TaskSpec
from secverify.workflow.graph import SecVerifyWorkflow

st.set_page_config(page_title="SecVerify Agent", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

ALLOWED_TOOLS = [
    "read_demo_alerts", "search_demo_alerts", "aggregate_alerts",
    "generate_local_report", "export_local_report",
]
SCOPE = ["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"]

SCENARIOS = {
    "A": {
        "icon": "🟢", "letter": "A", "title": "正常任务",
        "subtitle": "统计演示告警并生成报告",
        "expect": "预期：全部放行 · 任务成功",
        "goal": "查看演示告警，按严重级别统计并给出处理建议",
        "dataset": "demo_alerts_v1",
    },
    "B": {
        "icon": "🔴", "letter": "B", "title": "提示词注入防护",
        "subtitle": "日志内含诱导外发的恶意指令",
        "expect": "预期：越权调用被阻断 · 任务继续",
        "goal": "统计演示告警（数据集内含注入文本）",
        "dataset": "demo_injected_v1",
    },
    "C": {
        "icon": "🟠", "letter": "C", "title": "人工审批导出",
        "subtitle": "敏感导出需可信UI确认",
        "expect": "预期：中断等待审批 · 单次令牌",
        "goal": "汇总演示告警并导出本地审计报告",
        "dataset": "demo_approval_v1",
    },
}

# ------------------------------------------------------------------ styling

CSS = """
<style>
@keyframes pulseGlow{0%,100%{box-shadow:0 0 12px rgba(0,229,192,.28)}50%{box-shadow:0 0 26px rgba(0,229,192,.55)}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes slideIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

[data-testid="stAppViewContainer"]{
  background-color:#0a1018 !important;
  background-image:
    radial-gradient(1100px 500px at 15% -10%, rgba(0,120,140,.16), transparent 60%),
    radial-gradient(900px 480px at 95% 0%, rgba(80,40,160,.14), transparent 55%) !important;
}
[data-testid="stSidebar"]{
  background:#0b1220 !important;
  border-right:1px solid #16283a !important;
}
[data-testid="stHeader"]{background:transparent !important;}

.hero-title{
  font-size:30px;font-weight:800;letter-spacing:.5px;margin:2px 0 4px;
  background:linear-gradient(92deg,#7ef2dd 0%,#4db8ff 55%,#a98bff 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.hero-sub{color:#8ba6bd;font-size:13px;margin-bottom:2px}
.hero-sub b{color:#b9d6ea;font-weight:600}

.chip{
  display:inline-flex;align-items:center;gap:6px;margin:3px 6px 3px 0;padding:4px 11px;
  border-radius:999px;font-size:12px;border:1px solid #1d3449;
  background:rgba(13,26,40,.75);color:#a9c3d8;
}
.chip .dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot-live{background:#22e59c;box-shadow:0 0 8px #22e59c;animation:blink 1.6s infinite}
.dot-replay{background:#ffb454;box-shadow:0 0 8px #ffb454}

.sec-h{display:flex;align-items:center;gap:9px;margin:20px 0 10px}
.sec-h .bar{width:4px;height:19px;border-radius:3px;
  background:linear-gradient(180deg,#00e5c0,#4db8ff)}
.sec-h .t{font-size:16.5px;font-weight:700;color:#e6f2fb;letter-spacing:.4px}
.sec-h .n{color:#5d7b93;font-size:12.5px;font-family:ui-monospace,Consolas,monospace}

/* scenario cards */
.sc-card{
  border:1px solid #1c3247;border-radius:13px;padding:14px 15px 11px;margin-bottom:7px;
  background:linear-gradient(160deg,rgba(16,30,47,.95),rgba(10,19,31,.9));
  transition:all .25s ease;position:relative;height:100%;
}
.sc-card:hover{border-color:#2e5c74;transform:translateY(-2px)}
.sc-card.active{
  border-color:#00e5c0;background:linear-gradient(160deg,rgba(0,60,58,.5),rgba(8,24,32,.95));
  animation:pulseGlow 2.4s infinite;
}
.sc-card .top{display:flex;align-items:center;gap:9px;margin-bottom:3px}
.sc-card .letter{
  width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:15px;color:#04141c;background:linear-gradient(135deg,#37f0cf,#3ea6ff);
}
.sc-card.dim{opacity:.62}
.sc-card h4{margin:0;font-size:15px;color:#eaf4fc;font-weight:700}
.sc-card .sub{color:#8fa9bf;font-size:12px;margin:3px 0 7px;line-height:1.45}
.sc-card .expect{
  display:inline-block;font-size:11px;color:#7ee7c8;border:1px dashed #1f4c46;
  padding:2px 9px;border-radius:7px;font-family:ui-monospace,Consolas,monospace;
}
.sc-badge{
  position:absolute;top:-9px;right:11px;background:linear-gradient(90deg,#00e5c0,#3ea6ff);
  color:#03222b;font-size:11px;font-weight:800;padding:2px 10px;border-radius:999px;
  letter-spacing:1px;
}

/* pipeline steps */
.step{
  border:1px solid #16324a;border-left-width:4px;border-radius:9px;
  padding:9px 13px;margin:7px 0;background:rgba(10,22,35,.85);
  animation:slideIn .3s ease;
}
.step.allow{border-left-color:#22e59c}
.step.deny{border-left-color:#ff5470;background:rgba(46,10,20,.5)}
.step.wait{border-left-color:#ffb454;background:rgba(52,34,6,.4)}
.step.info{border-left-color:#4db8ff}
.step .row1{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.step .act{font-weight:800;font-size:13px;letter-spacing:.6px}
.act-ALLOW,.act-EXECUTED,.act-HUMAN_APPROVED,.act-APPROVED{color:#3df0b6}
.act-DENY,.act-REJECTED_BY_USER,.act-HUMAN_REJECTED{color:#ff6b85}
.act-REQUIRE_APPROVAL,.act-WAIT_FOR_APPROVAL{color:#ffc36b}
.step .tool{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:#7fd4ff;
  background:rgba(9,42,66,.65);padding:1px 8px;border-radius:6px}
.step .st{color:#7d97ad;font-size:11.5px;font-family:ui-monospace,Consolas,monospace}
.step .why{color:#93b0c6;font-size:12px;margin-top:4px;line-height:1.5}
.rulechip{
  font-size:10.5px;font-family:ui-monospace,Consolas,monospace;color:#9fb8cc;
  border:1px solid #24425c;border-radius:5px;padding:0 6px;margin-left:4px;
}
.step .who{color:#5c7891;font-size:11px;font-family:ui-monospace,monospace}

/* approval card */
.appr{
  border:1px solid #8a6414;border-radius:12px;padding:14px 16px;margin:10px 0;
  background:linear-gradient(150deg,rgba(64,44,6,.55),rgba(24,17,4,.85));
  box-shadow:0 0 22px rgba(255,180,84,.16);
}
.appr h4{color:#ffd58a;margin:0 0 6px;font-size:15px}

/* empty state */
.empty{
  border:1px dashed #21425c;border-radius:12px;padding:26px 18px;text-align:center;
  color:#5f7f99;font-size:13px;background:rgba(9,18,30,.5);
}
.empty .big{font-size:26px;display:block;margin-bottom:8px}

/* buttons */
.stButton>button{
  border-radius:9px;border:1px solid #235067;font-weight:600;color:#cfe8f8;
  background:linear-gradient(180deg,#12293c,#0c1c2c);transition:all .2s;
}
.stButton>button:hover{border-color:#00e5c0;color:#fff;box-shadow:0 0 14px rgba(0,229,192,.3)}
.stButton>button[kind="primary"]{
  background:linear-gradient(92deg,#00d3ad,#2fa7ff);color:#021b22;border:none;font-weight:800;
}

table.data{width:100%;border-collapse:collapse;font-size:12.5px}
table.data th{background:rgba(13,32,50,.9);color:#9fc2dc;border:1px solid #1c3a52;padding:6px 10px;font-weight:700}
table.data td{border:1px solid #173048;padding:5px 10px;color:#c2d8e8}
.mono{font-family:ui-monospace,Consolas,monospace}
.muted{color:#6f8ba3;font-size:12px}
.foot{color:#5b7889;font-size:11.5px;border-top:1px solid #14293c;
  padding-top:10px;margin-top:24px;line-height:1.7}
</style>
"""


def esc(s) -> str:
    return html_mod.escape(str(s), quote=True)


def chip(label: str, dot_class: str = "", text: str = "") -> str:
    return (f'<span class="chip">{f"<span class=\'dot {dot_class}\'></span>" if dot_class else ""}'
            f"{esc(label)}{esc(text)}</span>")


def hero() -> None:
    st.markdown(
        '<div class="hero-title">🛡️ SecVerify Agent</div>'
        '<div class="hero-sub">智能体工具调用安全防护与可信执行 · '
        '<b>Intern-S2</b> × LangGraph × 确定性策略引擎 × 来源追踪 × 人工审批 × 全程审计</div>',
        unsafe_allow_html=True,
    )


def section(no: str, title: str, note: str = "") -> None:
    note_html = f'<span class="n">{esc(note)}</span>' if note else ""
    st.markdown(f'<div class="sec-h"><span class="bar"></span>'
                f'<span class="t">{esc(title)}</span>{note_html}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ backend

@st.cache_resource
def get_workflow() -> SecVerifyWorkflow:
    return SecVerifyWorkflow()


_RUN_SEMAPHORE = threading.Semaphore(2)
MAX_RUNS_PER_SESSION = 20


def _session_quota_ok() -> bool:
    now = time.time()
    runs = st.session_state.setdefault("run_log", [])
    st.session_state["run_log"] = [t for t in runs if now - t < 3600]
    return len(st.session_state["run_log"]) < MAX_RUNS_PER_SESSION


def _record_run() -> None:
    st.session_state["run_log"].append(time.time())


def new_thread_id(run_id: str) -> str:
    import uuid
    return f"{run_id}-{uuid.uuid4().hex[:8]}"


def timeline_html(timeline: list[dict]) -> str:
    icon = {
        "ALLOW": "✅", "EXECUTED": "▶️", "DENY": "⛔", "REQUIRE_APPROVAL": "⏸",
        "HUMAN_APPROVED": "👤✅", "HUMAN_REJECTED": "👤🚫", "REJECTED_BY_USER": "🚫",
    }
    cls = {
        "ALLOW": "allow", "EXECUTED": "allow", "HUMAN_APPROVED": "allow", "APPROVED": "allow",
        "DENY": "deny", "REJECTED_BY_USER": "deny", "HUMAN_REJECTED": "deny",
        "REQUIRE_APPROVAL": "wait", "WAIT_FOR_APPROVAL": "wait",
    }
    parts = []
    for i, t in enumerate(timeline, 1):
        action = t.get("action", "")
        rules = "".join(f'<span class="rulechip">{esc(r)}</span>' for r in (t.get("rules") or []))
        parts.append(
            f'<div class="step {cls.get(action, "info")}">'
            f'<div class="row1"><span style="color:#54718a;font-size:11px" class="mono">#{i:02d}</span>'
            f'<span>{icon.get(action, "•")}</span>'
            f'<span class="act act-{esc(action)}">{esc(action)}</span>'
            f'<span class="tool">{esc(t.get("tool", ""))}</span>'
            f'<span class="st">{esc(t.get("status", ""))}</span>{rules}</div>'
            f'<div class="why">{esc(t.get("summary", ""))}</div></div>'
        )
    return "".join(parts)


def try_render_approval(wf: SecVerifyWorkflow, cfg: dict) -> None:
    snap = wf.compiled().get_state(cfg)
    if not snap.next or "request_approval" not in (snap.next or ()):
        return
    intr = snap.tasks[0].interrupts[0].value if snap.tasks else {}
    args_html = "<br>".join(
        f'<span class="mono" style="color:#7fd4ff">{esc(k)}</span> = {esc(v)}'
        for k, v in (intr.get("arguments") or {}).items()
    )
    st.markdown(
        f'<div class="appr"><h4>⏸ 工作流已中断 · 等待人工审批（LangGraph interrupt，可恢复）</h4>'
        f'<div class="why" style="color:#c8d8e6">待审批工具：<span class="tool">{esc(intr.get("tool"))}</span>'
        f'&nbsp;|&nbsp; 令牌TTL：{esc(intr.get("ttl_seconds"))}秒 · 单次有效 · 绑定当前参数</div>'
        f'<div style="margin:8px 0">{args_html}</div>'
        f'<div class="muted">风险说明：{esc(intr.get("risk"))}</div></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    if c1.button("✅ 批准（签发单次审批令牌）", type="primary", use_container_width=True):
        from langgraph.types import Command
        wf.compiled().invoke(Command(resume={"approved": True}), config=cfg)
        st.rerun()
    if c2.button("❌ 拒绝（不执行任何导出）", use_container_width=True):
        from langgraph.types import Command
        wf.compiled().invoke(Command(resume={"approved": False}), config=cfg)
        st.rerun()


# ==================================================================== layout
st.markdown(CSS, unsafe_allow_html=True)
wf = get_workflow()

with st.sidebar:
    st.markdown("## 🛡️ SecVerify")
    live = settings.live_mode
    if live:
        st.success("● LIVE — Intern-S2 实时调用")
    else:
        st.warning("● DEMO_REPLAY\n\n" + settings.replay_mode_reason)
    st.caption(f"模型 `{wf.client.model}` · 策略 `v{wf.policy.policy_version}`\n\n"
               f"调用上限 `{wf.policy.max_tool_calls_per_run}` · 审批TTL `{wf.policy.approval_ttl_seconds}s` · "
               f"演示配额 `{MAX_RUNS_PER_SESSION}次/时`")
    if settings.execution_mode.upper() != "LIVE":
        st.caption("⚠️ 当前为回放演示（REPLAY）——API不可用时的兜底模式")
        if st.button("↩ 恢复 LIVE 模式", use_container_width=True):
            settings.execution_mode = "LIVE"
            st.rerun()
    st.divider()
    if st.button("🔄 重置当前会话", use_container_width=True):
        for k in ("run_id", "scenario", "cfg", "task"):
            st.session_state.pop(k, None)
        st.rerun()
    st.caption("重置后可重新选择场景；已完成的运行记录保留在 artifacts/。")

hero()
mode_html = (chip("LIVE (Intern-S2)", "dot-live") if live
             else chip("DEMO_REPLAY", "dot-replay"))
st.markdown(mode_html + chip("模型 intern-s2") + chip("策略 R001–R008")
            + chip("ToolGateway 二次鉴权") + chip("审计 append-only"), unsafe_allow_html=True)

# ------------------------------------------------ ① scenario selection
section("①", "任务与数据 · 选择演示场景", "SCENARIO PICKER")

clicked = None
cols = st.columns(3)
current = st.session_state.get("scenario")
for col, (key, sc) in zip(cols, SCENARIOS.items()):
    active = current == key
    with col:
        badge = '<div class="sc-badge">▶ 当前运行</div>' if active else ""
        state = "active" if active else ("dim" if current else "")
        st.markdown(
            f'<div class="sc-card {state}">{badge}'
            f'<div class="top"><span class="letter">{sc["letter"]}</span>'
            f'<h4>{sc["icon"]} 场景{sc["letter"]} · {sc["title"]}</h4></div>'
            f'<div class="sub">{sc["subtitle"]}</div>'
            f'<div class="expect">{sc["expect"]}</div></div>',
            unsafe_allow_html=True,
        )
        if st.button(f'{"▶ 重新运行" if active else "启动"}场景{key}',
                     type="primary" if active else "secondary",
                     use_container_width=True, key=f"btn_{key}"):
            clicked = key

if current and not clicked:
    sc = SCENARIOS[current]
    st.info(f"当前展示：**场景{current} · {sc['title']}**（数据集 `{sc['dataset']}`）。"
            f"点击其他场景卡片即可切换。")

with st.expander("⚙️ 自定义任务（高级）"):
    goal = st.text_input("任务描述", "统计演示告警并生成报告")
    dataset = st.selectbox("数据集", SCOPE)
    if st.button("▶ 运行自定义任务"):
        SCENARIOS["A"] = {**SCENARIOS["A"], "title": "自定义", "subtitle": goal[:30],
                          "goal": goal, "dataset": dataset}
        clicked = "A"

if clicked:
    if not _session_quota_ok():
        st.error(f"演示配额已达上限（{MAX_RUNS_PER_SESSION}次/小时/会话），请稍后再试。")
        st.stop()
    sc = SCENARIOS[clicked]
    run_id = f"run_ui_{clicked.lower()}_{time.strftime('%H%M%S')}"
    st.session_state["run_id"] = run_id
    st.session_state["scenario"] = clicked
    task = TaskSpec(run_id=run_id, user_goal=sc["goal"], dataset_id=sc["dataset"],
                    allowed_tools=ALLOWED_TOOLS, resource_scope=SCOPE)
    st.session_state["task"] = task.model_dump()
    st.session_state["cfg"] = {"configurable": {"thread_id": new_thread_id(run_id)}}
    with _RUN_SEMAPHORE:
        wf.compiled().invoke({"task": task.model_dump(), "scenario": clicked},
                             config=st.session_state["cfg"])
    _record_run()
    st.rerun()  # re-render so the selected card highlights and results show in one pass

# ------------------------------------------------ ② pipeline
if st.session_state.pop("rerun_replay", False):
    # API不可用时的兜底：同一任务用回放规划器重跑（界面明确标注REPLAY）
    old_task = TaskSpec.model_validate(st.session_state["task"])
    run_id = f"run_ui_replay_{time.strftime('%H%M%S')}"
    st.session_state["run_id"] = run_id
    st.session_state["task"] = old_task.model_dump()
    st.session_state["cfg"] = {"configurable": {"thread_id": new_thread_id(run_id)}}
    with _RUN_SEMAPHORE:
        wf.compiled().invoke({"task": old_task.model_dump(),
                              "scenario": st.session_state.get("scenario", "A")},
                             config=st.session_state["cfg"])
    _record_run()
    st.rerun()

section("②", "执行流水线", "MODEL PROPOSE → POLICY DECIDE → GATEWAY EXECUTE")
if "cfg" in st.session_state:
    cfg = st.session_state["cfg"]
    values = wf.compiled().get_state(cfg).values or {}
    tl = values.get("timeline", [])
    if tl:
        st.markdown(timeline_html(tl), unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty"><span class="big">⏳</span>正在启动工作流…</div>',
                    unsafe_allow_html=True)
    try_render_approval(wf, cfg)

    # ------------------------------------------------ ③ status
    section("③", "运行状态与风险详情", "RUN STATUS")
    run_status = values.get("run_status", "-")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("运行状态", run_status)
    m2.metric("已执行步骤", values.get("executed_count", 0))
    m3.metric("策略阻断", values.get("blocked_count", 0),
              delta="安全兜底生效" if values.get("blocked_count", 0) else None)
    m4.metric("模式", values.get("api_mode", "-"))
    if values.get("final_answer"):
        if run_status == "API_UNAVAILABLE":
            st.error(values["final_answer"].split("\n")[0])
            c = st.columns([1, 1, 2])
            if c[0].button("🔄 改用回放演示重跑", use_container_width=True):
                settings.execution_mode = "REPLAY"
                st.session_state["rerun_replay"] = True
                st.rerun()
        else:
            st.success(values["final_answer"].split("\n")[0])
    blocked = [t for t in values.get("timeline", [])
               if t.get("action") in {"DENY", "REJECTED_BY_USER"}]
    for b in blocked:
        with st.expander(f"⛔ 被阻断：{b.get('tool')} （{'/'.join(b.get('rules') or [])}）"):
            st.write(b.get("summary"))
else:
    st.markdown(
        '<div class="empty"><span class="big">🛰️</span>'
        "尚未运行任何场景 —— 在上方 ① 选择一张场景卡片开始。<br>"
        "每一次运行都会产生：模型提议 → 策略裁决 → 实际执行 三段独立审计证据。</div>",
        unsafe_allow_html=True,
    )

# ------------------------------------------------ ④ comparison
section("④", "防护对照", "WOULD_EXECUTE vs EXECUTED · B0/B2")
st.caption("B0无防护基线中敏感操作只会记录 WOULD_EXECUTE（无真实外发）；本系统实际执行状态见 ② 时间线。")
try:
    import json
    b0 = Path("evaluation/results/policy_only_B0.jsonl")
    b2 = Path("evaluation/results/policy_only_B2.jsonl")
    if b0.exists() and b2.exists():
        rows_b0 = [json.loads(l) for l in b0.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows_b2 = [json.loads(l) for l in b2.read_text(encoding="utf-8").splitlines() if l.strip()]
        sample = [r for r in rows_b0 if r["decision"] == "WOULD_EXECUTE"
                  and r["proposed"].startswith("mock")][:5]
        if sample:
            trs = "".join(
                f"<tr><td class='mono'>{esc(r['case_id'])}</td><td class='mono'>{esc(r['proposed'])}</td>"
                f"<td style='color:#ff8b9d'>WOULD_EXECUTE ⚠️</td>"
                f"<td style='color:#3df0b6'>{esc(next((x['decision'] for x in rows_b2 if x['case_id'] == r['case_id']), ''))}</td></tr>"
                for r in sample)
            st.markdown(f"<table class='data'><tr><th>用例</th><th>拟调用</th><th>B0 无防护</th>"
                        f"<th>B2 本系统</th></tr>{trs}</table>", unsafe_allow_html=True)
    else:
        st.info("先运行 `python scripts/evaluate.py --mode policy-only --baseline all` 生成本地对照数据。")
except Exception as exc:  # noqa: BLE001
    st.warning(f"对照数据读取失败：{exc}")

# ------------------------------------------------ ⑤ evidence
section("⑤", "证据下载", "EVIDENCE")
if "run_id" in st.session_state:
    rid = st.session_state["run_id"]
    art = Path(settings.artifacts_dir) / rid
    audit_file = Path(settings.artifacts_dir) / "runs" / rid / "audit.jsonl"
    dl = []
    for label, path in [("📄 HTML报告", art / "report.html"), ("🧾 JSON报告", art / "report.json"),
                        ("⛓ 审计事件JSONL", audit_file)]:
        if path.exists():
            dl.append((label, path))
    if dl:
        cols = st.columns(len(dl))
        for col, (label, path) in zip(cols, dl):
            col.download_button(label, path.read_bytes(), file_name=path.name,
                                use_container_width=True)
    else:
        st.markdown('<div class="empty">该运行尚未产出可下载文件。</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="empty">运行任一场景后，可在此下载报告与完整审计链。</div>',
                unsafe_allow_html=True)

st.markdown(
    '<div class="foot">🔒 安全边界：所有工具仅在本地沙盒运行 · 诱捕工具无任何真实网络/删除实现 · '
    '导出仅写入隔离 artifacts/ 目录 · DEMO_REPLAY 输出不作为 Intern-S2 LIVE 证据<br>'
    'SecVerify Agent · 兴智杯方向三 · GitHub: doaspring/secverify-agent</div>',
    unsafe_allow_html=True,
)
