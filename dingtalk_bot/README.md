# S9-Vocab 钉钉问答机器人

面向审核员团队的钉钉机器人，回答 S9 词汇生产质检项目的"操作"和"业务规则"问题。
形态：**企业内部应用 + Stream 模式**（免公网回调地址）+ 独立静态问答服务。

完整方案见 [../docs/钉钉机器人MVP方案.md](../docs/钉钉机器人MVP方案.md)。

## 当前进度

- [x] 任务1：Stream 接入（实测连接通过）
- [x] 任务2：消息净化 + reply_markdown 回复
- [x] 任务3：知识库（4 个 md + loader，代码级审计扩充，~6000 tokens）
- [x] 任务4：AI 客户端 + prompt（Gateway 同步路径实测可用）
- [x] 任务5：全链路 + 失败降级 + 边界拒答（实测通过）
- [x] 任务6：问答日志（JSONL）
- [x] 任务7：Docker + 单测（20 passed, 85% 覆盖）
- [ ] 上线收尾：AppSecret 重置、生产部署、黄金问答验收

## 钉钉控制台配置（一次性）

1. 企业内部应用已建：`S9单词内容生产质检小助手`（AgentId 4501436052）。
2. **应用功能 → 机器人与消息推送**：开启机器人能力，设名字/头像。
3. **事件与回调（或机器人消息接收）**：推送方式选 **Stream 模式**（无需公网地址）。
4. **基础信息**：记下 **AppKey / AppSecret**（密钥，仅填入 `.env`，勿提交）。

## 本地运行

```bash
cd dingtalk_bot
pip install -r requirements.txt
cp .env.example .env      # 填入 DINGTALK_APP_KEY / DINGTALK_APP_SECRET
python stream_client.py
```

启动后回到钉钉控制台点"验证连接通道"应通过；在群里 @机器人 发任意文字，应收到占位回声。

## 部署说明（与盖娅 / 主项目的关系）

**本服务与 vocab-pipeline 主应用同仓，但部署完全独立、互不影响：**

- 主项目盖娅构建用 `gaea/Dockerfile`，它只打包 `backend/` + 前端 + `docs/prompts/`，**不包含 `dingtalk_bot/`**。
- 所以 push 代码 + 走盖娅部署主项目时，**部署的仍只是主应用，本机器人不会被构建/部署，也不会影响主应用**。
- 机器人与主应用**不能共用一个容器**：入口不同（主应用 gunicorn 开 :80；机器人 `python stream_client.py` 长连 WebSocket、不开端口），环境不同（机器人需 `DINGTALK_APP_KEY/SECRET`）。

**要上线本机器人，单独搞一个部署单元（二选一）：**

1. **盖娅独立应用**：新建一个盖娅应用，构建指向 `dingtalk_bot/Dockerfile`，配机器人自己的环境变量（`DINGTALK_*` + 复用主项目的 `AI_*`）。
2. **任意主机常驻**：Stream 模式外拨连钉钉、不需要公网入口，任何能访问外网的机器 `docker build -t s9-dingbot . && docker run --env-file .env s9-dingbot` 即可。

> 当前为本机进程试运行（`.venv/bin/python stream_client.py`），关机即停；正式上线请用上面任一方式常驻。

## 设计原则

- 只读、不碰内网后端业务数据。
- 知识库圈定边界，没把握回"不确定/转人工"，绝不编。
- AppSecret / AI key 仅存在于环境变量，绝不进代码或日志。
