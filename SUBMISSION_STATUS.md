# SUBMISSION_STATUS.md — 提交就绪度看板（每日更新）

## 总体状态
- 当前阶段：M0+M1+M2+M3核心 于 2026-10-28 一次性推进（落后日历1天，M3部分完成）
- 日期：2026-10-28
- P0 三场景（离线 DEMO_REPLAY 模式）：A ✅ / B ✅ / C ✅（浏览器实测通过）

## 关键交付物状态
| 交付物 | 状态 | 证据 |
| --- | --- | --- |
| Intern-S2 LIVE tool_calls 证据 | **LIVE_BLOCKED**（无 API Key） | scripts/smoke_intern.py, smoke_tool_call.py 均诚实退出码3 |
| 公网体验 URL | **DEPLOY_BLOCKED** | 待用户配置托管平台（M5） |
| 5分钟内720P视频 | **VIDEO_BLOCKED** | 待录制（M7） |
| 技术PDF | DRAFT（TECH_REPORT_TEMPLATE.md 待填实测） | M7 |
| 内层代码/模型ZIP | 部分（代码可复现，模型权重说明模板就位） | M8 |
| 外层官方命名ZIP | BLOCKED（缺队长信息） | M8 |

## 测试与评测（真实执行）
- pytest：**55 PASS / 0 FAIL / 0 SKIP**（2026-10-28，全部离线确定性）
- 评测 policy-only（42条种子，scripts/evaluate.py）：
  - B2 全防护：**42/42 match**，attack_block_rate=1.0，benign_allow=1.0，false_allows=0
  - B1 无审批链：39/42（3条审批案例误放行——审批链价值的消融证据）
  - B0 无防护：8/42（19/27攻击 WOULD_EXECUTE）
  - 结果：evaluation/results/{policy_only_B0,B1,B2}.jsonl + summary.md
- Streamlit：本地 8501/8599 端口 HTTP 200；A/B/C 三场景浏览器实测通过（含审批中断/批准/拒绝）

## 工程现状
- src/secverify 全模块：schemas / tool_registry / policy_engine / provenance / approval /
  tool_gateway / demo_tools / audit / build_report / intern_client / scripted_planner / graph
- LangGraph 状态机：多轮工具循环、DENY 安全重规划、interrupt 审批、审计与报告闭环
- 离线模式所有输出标记 DEMO_REPLAY；LIVE 证据必须待 Key 后由 smoke 脚本真实生成

## 等待用户的事项
1. **申请书生 API Token**（备注"兴智杯+团队名称"提额）→ 填入 .env 后重跑 smoke 脚本产出 LIVE 证据
2. 部署平台账号（Streamlit Cloud / HF Spaces）与 Secrets 配置 → M5 公网体验
3. 队长姓名/手机号/单位简称（官方 ZIP 命名用）
4. 视频录制授权与网盘上传（M7）
5. 向组委会确认云 API 型项目的模型文件/权重说明接受方式

## 下一阶段任务（M3 收尾 + M4）
1. LIVE 冒烟（依赖 Key）：smoke_tool_call.py 产出 evidence/live_tool_call.json
2. 评测图表两张（matplotlib，英文标签）+ evaluation/summary.md 扩展
3. SQLite checkpointer 切换验证（D005）
4. 复现包 ZIP 导出（run 的报告+审计打包下载）
5. 开始 P1（MCP stdio 只读适配）仅当上述全绿
