# SUBMISSION_STATUS.md — 提交就绪度看板（每日更新）

## 总体状态
- 当前阶段：M0–M3核心 + **M5公网LIVE体验全部完成**（2026-10-29）
- 日期：2026-10-29
- P0 三场景：本地（A/B/C 全通过）+ 公网（B/C 匿名实测、A LIVE 实测通过）

## 关键交付物状态
| 交付物 | 状态 | 证据 |
| --- | --- | --- |
| **公网体验 URL** | ✅ **https://secverify-agent-9cb76gvynzcnedjqenezs7.streamlit.app** | 匿名可访问（Public app + 私有Secrets）；生产 LIVE 模式实测场景A：真模型规划3步全ALLOW |
| **Intern-S2 LIVE tool_calls 证据** | ✅ **LIVE_OK** | 本地 `evidence/live_chat_smoke.json`（chat LIVE_OK, model=Intern-S2）；`evidence/live_tool_call.json`（真实tool_calls回合137+291=428）；LIVE场景A端到端（read→aggregate→report 全真模型） |
| 5分钟内720P视频 | **VIDEO_BLOCKED** | 待录制（M7） |
| 技术PDF | DRAFT | M7，体验URL已可填入 |
| 内层代码/模型ZIP | 部分 | M8 |
| 外层官方命名ZIP | BLOCKED（缺队长信息） | M8 |

## LIVE 模式记录（2026-10-29，真实运行）
- chat 冒烟：LIVE_OK，model=Intern-S2，延迟约3s
- tool_calls 回合：finish_reason=tool_calls，add_numbers(137,291)→428，二轮回传成功
- 场景A（LIVE）：模型自主规划3步全ALLOW，报告生成
- 场景B（LIVE，注入数据集）：**模型本轮未被诱导**（诚实记录 unauthorized_proposal_rate=0）；
  策略兜底由 policy-only 评测（B2 42/42）证明；DEMO_REPLAY 回放用于UI演示阻断路径
- LIVE 模式修复（真实运行暴露）：消息历史接入（模型可见工具结果）、参数归一化（模型传字符串limit）、
  run_id 可选并绑定当前运行（模型无法知道服务器run_id）、空请求路由守卫、Streamlit st.secrets 桥接

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

## 等待用户的事项（按优先级）
1. **申请书生 API Token**（唯一技术闸门）：https://internlm.intern-ai.org.cn 注册 → API Token，
   提额备注"兴智杯+团队名称"。拿到后两处配置：本地 `.env` 填 `INTERN_API_KEY`（跑 smoke 脚本出 LIVE 证据）；
   线上 app Settings → Secrets 添加 `INTERN_API_KEY`（评委可见真实 Intern-S2 调用，注意已有并发/频次护栏）
2. 队长姓名/手机号/单位简称（官方 ZIP 命名用）
3. 视频录制授权与网盘上传（M7）
4. 向组委会确认云 API 型项目的模型文件/权重说明接受方式
5. （可选）Streamlit app 自定义子域名；删除遗留的 sciverify-agent-3.0 旧应用避免混淆

## 部署就绪度（2026-10-28 更新）
- requirements.txt / .streamlit/config.toml / Dockerfile（含健康检查、非root）/ DEPLOYMENT.md 已备
- app.py 已内置公网护栏：并发信号量(2) + 20次/小时/会话配额（§12）
- 无 Key 部署 = DEMO_REPLAY，零成本零密钥面；本机实测 health 端点 OK
- 网络探测：github.com 可达（主路径）；huggingface.co 不可达（不作为主路径）

## 下一阶段任务（M3 收尾 + M4）
1. LIVE 冒烟（依赖 Key）：smoke_tool_call.py 产出 evidence/live_tool_call.json
2. 评测图表两张（matplotlib，英文标签）+ evaluation/summary.md 扩展
3. SQLite checkpointer 切换验证（D005）
4. 复现包 ZIP 导出（run 的报告+审计打包下载）
5. 开始 P1（MCP stdio 只读适配）仅当上述全绿
