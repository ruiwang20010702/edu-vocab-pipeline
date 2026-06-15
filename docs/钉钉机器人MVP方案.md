# S9-Vocab 钉钉问答机器人 — MVP 方案

> 状态：✅ **MVP 已实现并实测通过（2026-06-15）**，待上线收尾
> 形态：**企业内部应用 + Stream 机器人** + 独立静态问答服务
> 代码：`dingtalk_bot/`（feature 分支 `feature/dingtalk-qa-bot`）
>
> **前置条件已全部落实**：钉钉企业内部应用已创建（`S9单词内容生产质检小助手`，AgentId `4501436052`），开发者权限具备，事件/消息推送已选 **Stream 模式（无需公网回调地址）**。

## 实现状态（2026-06-15）

- **已完成**：任务 1–7 全部实现并实测——Stream 连接、消息净化、知识库（代码级审计扩充至 ~6000 tokens）、AI 客户端（Gateway 同步路径已验证可用 ~6s）、全链路+失败降级+边界拒答、问答日志(JSONL)、Docker、单测（20 passed / 85% 覆盖）。
- **知识库**：`dingtalk_bot/knowledge/` 共 4 个 md（01 操作手册 / 02 质检规则+POS / 03 FAQ / 04 维度+业务规则），由 3 个子 agent 深审后端代码后汇成，代码级准确。
- **测试集**：`dingtalk_bot/测试集.md` + 一键评测脚本 `dingtalk_bot/eval_qa.py`。
- **审计发现（待主项目订正）**：① CLAUDE.md/README 原写"Layer1 22 条规则"，代码实际 25 条（已订正主项目文档）；② 音节维度代码定义了 L2 规则但生产编排不拿它卡门（Layer1 过即批准）——知识库已写准。
- **上线收尾待办**：重置 AppSecret（曾在聊天暴露）、生产部署（Docker 常驻取代本机进程）、用测试集做黄金问答验收。
- **成本**：Gemini Flash 档，每问约 ¥0.016，每千问约 ¥13–20，可忽略。

## 0. 为什么不用自定义机器人（已确认的事实）

- 钉钉**自定义机器人只能"发送"消息，不能"接收"@消息**；且自 2023-09-01 起停止创建。
- 要做能"应答"的问答机器人，**必须用企业内部应用机器人**。其消息接收支持两种：HTTP 回调（需公网）/ **Stream 模式（WebSocket 外拨，免公网）**。
- 我们选 **Stream**：免公网地址、适配内网部署、支持群@ + 私聊 + 多轮，且后续扩实时数据可平滑衔接。

## 1. 目标与范围

**目标**：审核员在钉钉群 @机器人（或私聊）提问，机器人基于项目知识回答"怎么操作"和"业务规则"两类问题。

**In scope**：操作类（导入 / 审核 / 导出 / 重新生产 / 补缺字段）、业务规则类（释义合并、内容按义项挂载、质量门禁、POS 标签、质检规则说明）。

**Out of scope（明确不做，留给后续阶段）**：实时数据 / 进度查询、需查日志的故障排查、写操作、身份映射。

**核心原则**：
1. 只读、不碰内网后端业务数据；
2. 知识库圈定边界，没把握就回"不确定 / 转人工"，绝不编；
3. 服务独立部署、独立进程。

## 2. 架构总览

```
审核员在群里 @机器人 / 私聊机器人 提问
   → 钉钉通过 Stream(WebSocket) 把消息推到 已连接的机器人服务
   → 独立问答服务 (Python Stream Client, 可放内网, 免公网)
        1. Stream SDK 用 AppKey/AppSecret 握手, 长连接订阅机器人消息
        2. 收到消息 → 解析 + 净化用户输入 (<user_input> 包裹)
        3. 拼 prompt: [知识库全量(缓存锚点)] + [问题]
        4. 调 51talk AI Gateway (同步, 纯文本)
        5. 把答案 POST 到消息携带的 sessionWebhook 回到群/私聊
   → 用户收到 markdown 回答
   (旁路: 每条问答落日志, 供沉淀 FAQ / 发现知识盲区)
```

> Stream 模式下机器人服务是**主动外拨**连接钉钉，因此**不需要公网 HTTPS 端点、不需要配服务器出口IP白名单**。服务可直接放内网（甚至与后端同一 docker-compose）。

## 3. 知识库设计（关键决策：先塞 prompt，不做 RAG）

项目知识总量小（CLAUDE.md + 规则 + FAQ 估算 <20K token），gemini-3-flash 上下文极大。**MVP 直接把精选知识全量放进 system prompt + prompt caching 锚点**，不建向量库——避免过度设计，等知识涨到 ~50K token 再上检索。

新建 `dingtalk_bot/knowledge/`（人工精选 markdown）：

| 文件 | 内容来源 |
|---|---|
| `01_操作手册.md` | 导入词表 / 审核流程 / 导出门禁 / 重新生产 / 一键补缺字段 |
| `02_业务规则.md` | 释义合并、内容按义项挂载、质量门禁三道关、生产中锁 |
| `03_质检规则.md` | Layer1 25 条 + Layer2 AI 校验说明（从 qc/registry 提炼） |
| `04_POS标签.md` | 23 个权威带点标签清单 |
| `05_FAQ.md` | 高频问答（被拒怎么办、留空正常吗、音标格式等） |

## 4. 服务设计（关键技术点）

- **接入**：Python 钉钉 Stream SDK（`dingtalk-stream`），用 **AppKey / AppSecret** 握手建立长连接，注册机器人消息回调（Chatbot message handler）。无 HTTP 入站端点，故**无需 HTTP 验签**——安全边界转为"凭证保管 + 出站校验"。
- **回复**：从收到的消息体取 `sessionWebhook`，把答案以 markdown POST 回去。Stream 模式**没有自定义机器人那个 3 秒公网回调超时压力**，LLM 慢一点也没关系（仍应及时 ack 消息）。
- **Prompt 结构**：system = 角色 + 边界规则 + 知识库全量；user = `<user_input>净化后的问题</user_input>`。系统提示不在输出暴露。
- **AI 调用**：复用 Gateway 信封逻辑，但 **`async=False` 同步、`use_json_format=False` 纯文本**（聊天答案不需要 JSON）。⚠️ 待验证：Gateway 同步路径能否内联返回结果（现项目走的是异步轮询）。
- **降级**：AI 失败 / 超时 → 回"暂时答不了，稍后再试或找 @管理员"，不静默吞错。
- **边界拒答**：越界问题（实时数据/写操作）统一回"暂不支持，请用系统页面 / 找管理员"。

## 5. 目录结构（新增，独立于主项目代码，仓内同居）

```
dingtalk_bot/                    # 独立服务，独立进程，可放内网
├── stream_client.py            # 入口: 建 Stream 长连接 + 注册消息回调
├── handler.py                  # 消息处理: 解析→净化→拼prompt→调AI→回复
├── dingtalk_reply.py           # 用 sessionWebhook 回复 markdown
├── ai_client.py                # 精简版 Gateway 同步客户端(~50 行, 不依赖主项目)
├── knowledge_loader.py         # 启动时加载 knowledge/*.md 拼成知识块
├── prompt.py                   # system prompt 模板 + 输入净化
├── config.py                   # 环境变量(DINGTALK_ / AI_)
├── knowledge/                  # 上面 5 个 md
├── tests/                      # 单元 + 集成
├── Dockerfile
└── README.md                   # 部署 + 钉钉控制台配置步骤
```

## 6. 配置项（env）

```
DINGTALK_APP_KEY        # 企业内部应用 AppKey (Client ID)
DINGTALK_APP_SECRET     # 企业内部应用 AppSecret (Client Secret) —— 密钥, 仅入 env
AI_API_KEY              # 复用 51talk Gateway key
AI_API_BASE_URL
AI_MODEL                # 默认 gemini-3-flash-preview|efficiency
AI_GATEWAY_BIZ_TYPE     # vocab_qc_bot
BOT_LOG_PATH            # 问答日志落盘路径
```

## 7. 任务分解（每步带验证标准）

```
1. 搭骨架: Stream SDK 接入 + 配置加载 + 空消息回调
   → 验证: 启动后能与钉钉建立 Stream 连接(控制台"验证连接通道"通过)
2. 消息处理链路: 解析@消息 + 输入净化 + sessionWebhook 回复
   → 验证: 群里@机器人发"hi", 收到固定回声; 单测覆盖净化/解析
3. 知识库: 编写 5 个 md + loader 拼装
   → 验证: loader 输出含全部 5 块, token 量打印 < 阈值
4. AI 客户端 + prompt 拼装
   → 验证: 单测 prompt 含知识块+净化后输入; 真连 Gateway 同步返回非空文本
   → ⚠️ 此步同时确认 Gateway 同步路径可用(关键不确定性)
5. 串起全链路 + 失败降级 + 边界拒答
   → 验证: @机器人问"怎么导入词表"收到正确回答; 问"我这批审到哪了"回越界提示
6. 问答日志旁路
   → 验证: 每次问答落一条结构化日志
7. Docker + 部署文档
   → 验证: 容器跑通; 黄金问答集验收
```

## 8. 验收标准（MVP Done 的定义）

- 群里 @机器人（或私聊）问操作 / 规则类问题，10 个典型问题答对 ≥8（用一组黄金问答验收）。
- 越界问题（如"我这批审到哪了"）正确回"暂不支持，请用系统页面 / 找管理员"。
- 测试覆盖 ≥80%（净化、prompt、消息解析、回复封装为重点）。
- 全程不暴露 system prompt、不泄 AppSecret/AI key。

## 9. 风险 / 待确认

| 项 | 影响 | 处置 |
|---|---|---|
| ✅ 企业内部应用 + Stream 可用 | 接入路径 | 已确认（应用已建、Stream 模式可选、免公网） |
| 🟠 Gateway 同步(非异步)路径是否内联返回 | 影响延迟实现 | 任务 4 实测；不行则用轮询 + sessionWebhook |
| 🟡 机器人需在控制台开启并配 Stream + 加权限 | 联调前提 | 「机器人与消息推送」开启机器人；按 SDK 文档勾权限 |
| 🟡 知识库时效 | 规则变了答案会过期 | MVP 人工维护 md；后续做同步 |

## 10. 后续演进（不在 MVP）

验证有价值后 → 加身份映射（邮箱匹配 `User.email`，或加 `dingtalk_userid` 列 + 绑定）→ 实时进度 / 为何被拒 / 故障排查 tool 路由（JSON 意图分类，绕过 tool-calling 不确定性）。**接入层（Stream）和知识问答内核整体复用，无需重做。**

---

## 附：前期调研结论（已确认的代码事实）

- **AI 层**：当前 `ai_gateway_mode=True`，模型 `gemini-3-flash-preview|efficiency`，走异步提交 + 轮询。Gateway 是 51talk 自定义信封（`provider`/`biz_type`/content 数组），`tools` 能否透传未确认——但 MVP 静态问答不依赖 tool-calling，已规避。（`core/generators/base.py:build_ai_request`）
- **用户表**：`User` 仅有 `email`(唯一登录身份) / `name` / `role` / `is_active`，无手机号、无 dingtalk 字段。后续身份映射走"邮箱匹配"或"加 `dingtalk_userid` 列 + 绑定流程"。（`core/models/user.py`）
- **钉钉应用**：企业内部应用 AgentId `4501436052`；消息推送支持 Stream 模式（控制台「事件与回调」可选「Stream模式推送」，标注"无需注册公网回调地址"）。
