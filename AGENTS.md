# AGENTS.md — SecVerify Agent GLM5.3工程强制规范

## 项目身份
- 新项目：`secverify-agent`；严禁继续开发旧SciVerify的生物统计领域模块。
- 竞赛：兴智杯·方向三，2026-11-05截止，内部最晚2026-11-04封版。
- 评分：实用性40%，完整性30%，技术实现难度30%。
- 作品运行模型：**真实书生Intern-S2**。GLM5.3只是编码、测试与文档助手。

## 读取顺序
1. `SECVERIFY_EXECUTION_SPEC.md`（功能/架构/安全/官方提交要求的权威规范）
2. `GLM53_PHASE_PROMPTS.md`（逐日闸门）
3. `SUBMISSION_CHECKLIST.md`（竞赛最终交付）
4. 已有源码和测试记录（若存在）

## 不得触碰的限制
- 不接真实用户邮箱、网盘、生产系统、实际内网扫描、真实网络外传、删除真实文件；所有攻击/越权操作仅沙盒模拟。
- 绝对不执行模型生成的Shell/Python/SQL命令或未经登记的MCP工具。
- 权限判断必须由确定性PolicyEngine完成，最终ToolGateway必须二次鉴权。
- 模型输出与所有文件、日志、工具响应都不等价于可信授权。
- 没有真实Intern-S2工具调用与日志不能标为LIVE成功。
- 未跑测试不能宣称测试通过；真实评测的失败、跳过、超时不能删。
- 严禁把私密API Key写入代码、git、日志、报告或公开部署。
- 技术PDF、网盘视频链接、公开体验链接、代码模型ZIP、两层官方ZIP是必须交付物。

## 当前任务优先级
P0 = 正常任务+攻击任务+人工审批三场景，Intern-S2 tool_calls，LangGraph，信任来源追踪，强制策略，证据链，测试和线上演示。
P1 = MCP stdio (仅P0、部署、材料均通过)，OpenTelemetry结构化trace。
P2 = OPA/Rego、A2A、多智能体攻防和模型训练，不纳入硬交付。

## 对GLM5.3的操作授权
允许在当前`secverify-agent`工作目录中创建/编辑/删除**本项目内部**代码及演示数据、执行依赖安装、pytest、非破坏性本地运行、Git提交（若已建立仓库）。禁止运行危险命令、扫描真实目标、外传文件或操作真实外部账号。
若需要API Key、部署平台登录授权、上传视频、队长信息或比赛提交，由用户完成；不可绕过。

## 每阶段的完成报告格式
- Phase / Date / Git Commit:
- Files changed:
- Commands executed and exit codes:
- Pytest PASS/FAIL/SKIP:
- LIVE Intern-S2 status, redacted evidence path:
- Normal task outcome:
- Attack test outcome (proposed vs executed):
- Approval test:
- Public URL and anonymous test status:
- Technical PDF/video/inner ZIP readiness:
- Blockers / user actions:
- Next phase:

将每个Phase实际命令、结果截图/日志保存到`docs/phase_reports/`，并每日更新`SUBMISSION_STATUS.md`。如果遇到冲突，优先按正式比赛要求修正，并将决策记录入`DECISIONS.md`。
