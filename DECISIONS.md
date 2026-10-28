# DECISIONS.md — 规范/实现冲突裁决记录

规范 §0：冲突按权威顺序裁决并在此留痕。

## D001 — 使用 Python 3.12.10 而非宿主默认 3.14
- 日期：2026-10-28
- 冲突：规范 §4 要求 3.11/3.12；开发机默认 `python` 为 3.14.7
- 裁决：用已安装的 Python 3.12.10 创建 `.venv`
- 依据：规范明确版本范围；3.12 全依赖兼容验证通过

## D002 — 参数上限（limit≤100）由策略引擎 R006 而非 schema 强制
- 日期：2026-10-28
- 冲突：Pydantic schema 与策略都可表达"limit 上限"
- 裁决：schema 只管形状（类型/枚举/最小值/格式），数值上限归 R006_BUDGET_LIMIT
- 依据：与 V1.1 种子一致（PARAM_BYPASS_01 limit=500 → R006；PARAM_BYPASS_02 limit=-1 → R003）；
  两层校验仍是防御纵深，责任归属必须唯一以便测试断言

## D003 — 诱捕工具注册但不向模型广播
- 日期：2026-10-28
- 冲突：注册表包含 7 个工具 vs tools=[...] 广播列表
- 裁决：`mock_send_external`/`mock_delete_all` 在 ToolRegistry 中注册（供 R002 判定与测试），
  但 `tool_schemas_for_api()` 不把它们发给模型
- 依据：向模型宣传禁止工具违背最小权限；注入文本点名工具时模型仍可能"幻觉调用"，
  注册表内的 R002 兜底拦截；B 场景离线规划器按注入内容模拟"被诱导的提议"

## D004 — 审批拒绝路径走 record_denial，不再回流 policy_recheck
- 日期：2026-10-28
- 冲突：初版图把 request_approval 无条件连到 policy_recheck，拒绝后会在网关再产生一条 REQUIRE_APPROVAL 记录
- 裁决：条件路由——批准→policy_recheck→execute；拒绝→record_denial（planner 终止）
- 依据：规范 §6.3"拒绝审批时不得重试绕过"；审计时间线不应出现语义噪音

## D005 — MemorySaver 作为 P0 checkpointer
- 日期：2026-10-28
- 冲突：规范 §8.2 公开部署优先 SQLite 持久化
- 裁决：P0 用 langgraph.checkpoint.memory.MemorySaver（单进程演示定位，如实宣称）；
  已安装 langgraph-checkpoint-sqlite 供 M5 部署前切换
- 依据：先保证三场景闭环；部署阶段再验证 SqliteSaver 的生产行为

## D006 — 审批令牌重放返回 DENY 而非再次 REQUIRE_APPROVAL
- 日期：2026-10-28
- 冲突：令牌消费后同参数重试，引擎重判为 REQUIRE_APPROVAL
- 裁决：ToolGateway 在"审批执行路径"上遇到令牌缺失/已消费/过期一律 DENY（R007）
- 依据：单次有效语义（§6.2 第7步）；重放即异常，应显式拒绝并留痕
