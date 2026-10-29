# 部署手册 — SecVerify Agent 公网体验入口（M5）

> 目标：评委无需账号、无需 API Key，点开 HTTPS 链接即可体验 A/B/C 三场景。
> 本机网络实测（2026-10-28）：github.com 可达；huggingface.co 不可达 → **HF Spaces 不作为主路径**。

## 已备好的部署物料（本仓库内）

| 文件 | 用途 |
| --- | --- |
| `requirements.txt` | 托管平台依赖（app.py 含 src/ 路径自举，无需安装包即可运行） |
| `.streamlit/config.toml` | headless、XSRF 防护、4MB 上传上限、关闭统计 |
| `Dockerfile` | 任何容器平台（含健康检查、非 root 运行） |
| `app.py` 内置护栏 | 并发信号量（2）+ 每会话每小时 20 次演示配额（§12 限流要求） |

无 Key 部署 = 纯 DEMO_REPLAY 模式，**零 API 成本、零密钥泄露面**；后续要 LIVE 演示时在平台 Secrets 配 `INTERN_API_KEY` 即可，代码无需改动。

## 路径一（推荐）：Streamlit Community Cloud + GitHub 私有仓库

代码保持私有，分享链接评委可匿名访问（免费版含 1 个私有 app 额度）。

**用户操作（约 10 分钟，需邮箱/手机验证，助手无法代办）：**
1. 注册 GitHub 账号：https://github.com/signup （邮箱验证）
2. 生成访问令牌：Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate
   - Repository access：Only select repositories（授权即将创建的仓库）
   - Permissions：Contents → Read and write
   - 把令牌发给助手（或自行 `git remote add` + push）
3. share.streamlit.io → 用 GitHub 登录 → New app
   - Repository：`<你的用户名>/secverify-agent`，Branch：`main`，Main file：`app.py`
   - Advanced → Python version 选 3.12；Secrets 暂不填（DEMO_REPLAY 即可上线）
   - Deploy → 等待构建（首次约 2–4 分钟）
4. 用**无痕窗口**打开分配的 `https://<app>.streamlit.app` 验证三场景
5. 把 URL 告知助手，记入 SUBMISSION_STATUS.md

## 路径二（国内评委访问更稳）：魔搭 ModelScope 创空间

1. 注册/登录 https://modelscope.cn （手机号）
2. 创空间（Studio）→ SDK 选 **Streamlit**，命名如 `secverify-agent`
3. 按页面提示 `git clone https://www.modelscope.cn/studios/<用户>/<空间>.git`，
   把本仓库文件拷入（或助手代办），push 即部署
4. 访问 `https://modelscope.cn/studios/<用户>/<空间>` 验证

## 安全清单（上线前自查）

- [ ] 仓库不含 `.env`（已在 .gitignore；密钥只进平台 Secrets）
- [ ] 无痕浏览器可访问；页面显示 DEMO_REPLAY / LIVE 真实模式
- [ ] 三场景 A/B/C 各跑一遍；场景C审批拒绝路径也验证
- [ ] `artifacts/`、`evidence/` 不随仓库分发（已 gitignore）
- [ ] 若配置了 LIVE Key：确认限流生效（并发 2、20 次/时/会话）

## 部署后回填

SUBMISSION_STATUS.md「公网体验 URL」从 DEPLOY_BLOCKED → 实际 URL + 匿名验证日期。
