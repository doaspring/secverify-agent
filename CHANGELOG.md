# CHANGELOG

## 0.1.0 — 2026-10-28
- M0：项目骨架、Python 3.12 venv、依赖锁定、Intern-S2 客户端（LIVE_BLOCKED 语义）、
  smoke 脚本两枚（chat / tool-call 回合），无 Key 时诚实退出码 3
- M1：固定 ToolRegistry（7 工具 + schema pinning digest）、5+2 沙盒演示工具、
  数据集加载校验、ProvenanceStore 信任标签与父子链、42 条评测种子入库
- M2：PolicyEngine（R001–R008 权威顺序、fail-closed R000、语义收紧只许 R9xx）、
  ApprovalStore（单次令牌绑定 canonical 参数 + TTL）、ToolGateway 二次鉴权与令牌消费
- M3核心：LangGraph 状态机（多轮循环、DENY 安全重规划、interrupt 审批/恢复）、
  append-only 审计（JSONL+可选SQLite）、HTML/JSON 报告、Streamlit 五区界面
- 测试 55 条全绿；评测 B0/B1/B2 三对照脚本与真实结果
- 详见 docs/phase_reports/ 与 SUBMISSION_STATUS.md

## 0.2.0 — 2026-10-29（界面重设计 + LIVE加固）
- 界面：深色SOC科技风主题；场景A/B/C卡片化，选中态高亮+徽章+其余变暗（解决"不知道点了哪个"）
- 流水线时间线卡片化（按ALLOW/DENY/WAIT着色、规则chips、等宽字体）；③区指标行(st.metric)
- API_UNAVAILABLE 明确错误态 + "改用回放演示重跑"兜底按钮（现场断网保险），侧栏可恢复LIVE
- LIVE加固：系统提示词强制数据结论必须来自工具调用；finalize区分API失败与正常完成
- 已验证：本地+生产（生产LIVE场景C全流程：真模型6步→审批中断→批准→导出执行）
