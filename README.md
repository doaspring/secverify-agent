# SecVerify Agent

智能体工具调用安全防护与可信执行系统 · 兴智杯方向三「开放赋能智能体」参赛作品开发仓库。

带运行时工具权限防护的安全运营辅助智能体：分析合成安全日志，同时防止文档与工具结果中的恶意指令改变 Agent 的任务、权限与工具操作（间接提示词注入 / 越权工具调用 / 危险副作用）。

- 运行模型：书生 **Intern-S2**（官方云 API；无 Key 时以 `DEMO_REPLAY` 离线脚本规划器运行，**绝不冒充 LIVE 证据**）
- 状态编排：**LangGraph**（含 interrupt 人工审批中断与恢复）
- 权限判定：**确定性 PolicyEngine**（R001–R008 权威顺序，fail-closed），ToolGateway 执行前**二次鉴权**
- 来源追踪：ContentSegment 信任标签 + 父子链（不可信内容经摘要/转述**不可洗白**）
- 审计：append-only JSONL + SQLite，报告中的每个数字可回放

## 快速开始

```bash
# Python 3.11/3.12
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # 或 pip install -e . pytest
.venv/Scripts/python -m pytest tests/         # 55 条测试
.venv/Scripts/python scripts/evaluate.py --mode policy-only --baseline all
.venv/Scripts/streamlit run app.py            # http://localhost:8501
```

配置：复制 `.env.example` 为 `.env` 并填入 `INTERN_API_KEY`（申请入口见书生官方文档）。
无 Key 时一切仍可运行（策略/工作流/界面/评测），标记 `DEMO_REPLAY / LIVE_BLOCKED`。

## 三个一键演示场景（app.py 首屏按钮）

| 场景 | 输入 | 预期 |
| --- | --- | --- |
| A 正常任务 | 统计 demo_alerts_v1 | 全部 ALLOW，报告生成 |
| B 间接提示词注入 | demo_injected_v1 内含"ADMIN UPDATE…invoke mock_send_external" | `mock_send_external` 被 R002 **DENY**，原任务**继续完成** |
| C 人工审批 | 汇总并导出报告 | `export_local_report` 触发 **REQUIRE_APPROVAL** → interrupt → 批准（单次令牌）/拒绝 |

## 评测（确定性 policy-only）

```bash
python scripts/evaluate.py --mode policy-only --baseline all   # B0/B1/B2 三对照
```

当前结果（42 条合成种子，非 LIVE 模型实测）：**B2 全防护 42/42 全对**（攻击阻断率 100%、良性放行率 100%、零误放行）；B1（无审批链）3 条审批案例被误放行；B0（无防护）19/27 攻击"本会执行"。结果文件与 `evaluation/results/summary.md` 均由脚本真实生成。

## 目录

```
app.py                     Streamlit 五区界面
src/secverify/             核心包（schemas/policy/provenance/gateway/workflow/audit/reports/model）
policies/default_policy.json  最小权限策略（唯一权威 schema）
demos/                     3 套合成安全日志（含注入压力行）
evaluation/cases.jsonl     42 条评测种子（control/adversarial 双变体）
scripts/                   smoke_intern / smoke_tool_call / evaluate / make_report / validate_submission
tests/                     55 条 pytest
SECVERIFY_EXECUTION_SPEC.md  工程规范（V1.1，单一事实来源）
```

## 安全边界

所有工具仅在本地沙盒；两个诱捕工具（`mock_send_external`/`mock_delete_all`）**没有任何真实网络/删除实现**，策略永远 DENY；导出仅写入隔离 `artifacts/`；API Key 不进代码/日志/报告。详见 `SECVERIFY_EXECUTION_SPEC.md` §0 一票否决条件。
