# GLM5.3 逐阶段实施提示词 | SecVerify Agent

约定：每次开始读取主手册与AGENTS；每个阶段真实执行测试，保存`docs/phase_reports/Mx.md`，提交代码；不得用规划代替运行。若你在GLM5.3中通过多次会话完成，下一次从报告与测试恢复。

## M0 — 10月27日（API/骨架）
> 依据实施规范，建立Python 3.11+项目、app.py、.env.example、ToolRegistry、PolicyEngine占位但可安装运行。先写真实Intern-S2 `smoke_tool_call.py`，非流式thinking mode，返回真实`tool_calls`、执行本地无害工具后以tool消息回传；无Key则LIVE_BLOCKED。跑pytest，生成实际测试证据、GAP_REPORT与Git commit。不得引入复杂MCP、OPA或真正危险工具。

**通过条件**：项目能启动，live工具调用真证据或明确阻断；单测无无法解释失败。

## M1 — 10月28日（数据与来源）
> 用3套明确“合成数据”的日志/告警fixture，实现CSV/JSONL读取、文件大小与字段校验、DataProvenance节点、信任标签和父子传播；实现5个只在本地工作的演示工具与2个永不产生副作用的禁用模拟工具。加载本包evaluation_seed_cases.jsonl为初始化案例，实际测试时另存运行结果。编写来源追踪、工具schema、文件安全测试，保存报告。

**通过条件**：正常只读工具能返回合成数据、低可信日志无法改变ToolRegistry；样例来源ID可回溯。

## M2 — 10月29日（防护核心）
> 完成固定JSON策略和PolicyEngine，严格定义ALLOW/DENY/REQUIRE_APPROVAL；每次ToolGateway执行前重新检查工具、参数、角色、resource_scope、调用预算与审批状态。审批仅可信UI发起，绑定run_id、tool、canonical_args、策略版本且单次有效。构建至少15条安全规则用例；禁止未经批准的export及所有模拟外发/删除。

**通过条件**：任何路径都不能让未授权工具实际执行；策略抛错时fail-closed。

## M3 — 10月30日（LangGraph + Intern）
> 用LangGraph状态机串起context→Intern-S2 plan/tool_calls→PolicyGate→执行/阻断/暂停→审计→报告，至少A正常任务与B注入任务可在Streamlit真实运行。将工具输出明确标为低可信；日志分模型提议与执行结果。准备Streamlit Cloud部署与备选HF Spaces所需代码。所有API调用失败在UI明确显示，不用回放假装LIVE。

**通过条件**：两个LIVE端到端流程、候选公网地址（若用户完成账号配置）、无外部副作用。

## M4 — 10月31日（审批/三场景/封P0）
> 实现可恢复的LangGraph interrupt人工审批，可信UI能批准/拒绝export_local_report，ToolGateway重新验证审批及参数，运行后令牌作废。完成报告HTML和JSONL事件下载/ZIP复现包、SQLite审计（环境允许）。A正常/B阻断/C审批至少三场景一键运行；没有M4真实E2E就不能开发加分功能。

**通过条件**：三场景真实日志+统计/审计报告，模型API请求/执行区别可复查。

## M5 — 11月1日（公开体验+可选MCP）
> 先做公网HTTPS体验（评委无需本团队账号），开通演示模式下的真实Intern-S2调用并设置限流/成本/隐私保护；在无痕浏览器与另一网络验证。只有P0、链接与材料进度都健康，才实现MCP v2 stdio服务端，注册2个只读工具，并保留ToolGateway强制权限检查。若MCP安装/部署导致异常，回退到P0。

**通过条件**：线上A/B/C可体验；有MCP实际调用才宣称使用了MCP。

## M6 — 11月2日（真实评测）
> 依据seed cases扩展或校订至少24条案例，至少30条pytest；真实运行B0/B1/B2（所有危险动作仍仅SIMULATED），导出分母/成功/失败/误报/延迟/调用数和原始日志，绘制至少两张English labels图。验证“正常任务成功率”和“越权执行率”是不同指标。不要制造符合目标的假数据。只有测试充分再做可选追踪OTel，不安排OPA。

**通过条件**：评价表有真实数据、每条case状态和失败原因；报告能复现。

## M7 — 11月3日（参赛材料）
> 准备10–15页左右正式参赛技术PDF（不是开发规范本身）：行业痛点、真实架构、测试证据、实用性分析、正式公网链接、演示视频网盘链接、源码运行和模型权重说明。按4分40秒脚本录屏，时长<300s、分辨率>=1280×720；若需要本人录屏上传，输出可操作分镜和人工事项，不得虚构链接。对视频分享权限、体验站点匿名访问、PDF点击链接逐个核验。

**通过条件**：PDF/视频/公网URL均真实；缺一项即BLOCKED。

## M8 — 11月4日（双层ZIP与上传）
> 停止新功能。根据官方格式生成外层`单位简称-作品名称-队长姓名-队长手机号-日期.zip`，恰好包含技术PDF和内层代码/模型ZIP。代码压缩包包含源码、requirements.lock或锁文件、测试、demo数据、运行与复现实录、模型权重说明，不得包含密钥。运行正式验包、全量pytest、一次LIVE路径，保存SHA256。用户最后完成参赛平台上传并保留回执，11月5日仅用于意外补救。

**通过条件**：真实官方上传回执、最终zip hash、PDF/视频/链接验证记录一致。

## 未达成时的优先级
10/30还未有LIVE模型工具调用→先修API与权限；不允许以GLM代替Intern。
10/31缺三场景→砍MCP/OPA/OTel，仅修完整闭环。
11/01无公网URL→把部署作为唯一优先事项。
11/03缺PDF或视频→停止编码，先做材料。
11/04没有真实队长信息→打包保持BLOCKED，提示用户填写；不能用占位符提交。
