# release → main 同步清单

> 生成时间：2026-05-08（基于 history rewrite 后的 SHA）
> 范围：`git log main..release`（共 54 个 commit）
> 上下文：2026-05-08 通过 git filter-repo 删除了 3 个含 secret 的文件历史，所有 SHA 已重写
> 目的：按 51Talk AoneFlow 规范，release 发布完成后必须合并回 master/main。当前 release 比 main 多 54 个 commit，需要对齐。

## 摘要

| 类型 | 数量 | 风险等级 |
|---|---|---|
| feat (新功能) | 11 | 中 — 需评估是否已稳定 |
| fix (修复) | 24 | 低 — 应直接合回 |
| perf (性能) | 2 | 低 |
| refactor (重构) | 1 | 低 |
| docs (文档) | 6 | 极低 |
| chore (杂项) | 1 | 极低 |
| add (非规范) | 9 | **高** — 早期 Gaea 部署调试 commit，需逐个核查 |

## main 比 release 多的 9 个 commit

> 这些是历史上直接 push 到 main 的"实验性"内容 + 2 个 security 修复，未来 release → main 同步时需要保留。

| Hash | 主题 |
|---|---|
| 5932431 | chore(security): .gitignore 补全 docs/gaea-test-env.md |
| 172335d | fix(security): 删除废弃的 qc-model-eval 目录清除硬编码 API Key + 补全 .gitignore |
| a2f9e39 | fix: 修复前端 TypeScript 编译错误（未使用变量、类型收窄） |
| d12ee8f | feat: 质检模型评估数据与报告入库 |
| d496918 | refactor: 质检评分公式改为 acc - FPR - 0.5*FNR |
| f71ef3b | docs: 添加修复文档和评估测试脚本 |
| f07a554 | refactor: 合并 Gemini-GW 到 Gemini，评估报告统一为 3 模型对比 |
| 1cde14b | feat: 质检模型评估工具（GPT-5.2 / Gemini / 豆包 对比） |
| d88b5b1 | feat: 全部 7 个维度质检升级完整 Prompt + 并发请求错开 |

## 处理建议

1. **优先合回**（24 fix + 2 perf + 1 refactor + 6 docs + 1 chore = 34 个）：纯修复/优化，几乎无风险
2. **逐个评估**（11 feat）：含日志体系、AI 用量追踪、大规模导入优化、英美音标分离等较大改动
3. **先核查再处理**（9 add）：早期 Gaea 部署调试时的非规范 commit，部分 message 是 "add gaea5" / "add execlin2222"，建议先 `git show <hash>` 看 diff

---

## 全量清单（按时间倒序）

### feat（11 个）
| Hash | 日期 | 主题 |
|---|---|---|
| 06050a7 | 2026-05-08 | 词中词话术降为 200-250 字 + 改 1v1 私教风格 (#2)（PR #2 squash） |
| f43b073 | 2026-03-31 | 补充 021_add_ai_task_queue 迁移文件 |
| 6fac1f7 | 2026-03-26 | 导入缺失释义警告提示 + 新增「剑桥释义」列名映射 |
| 44ee937 | 2026-03-26 | 后端日志体系完善——结构化格式、请求追踪、全链路覆盖 |
| 11ae05e | 2026-03-25 | regenerate 端点异步化 + 504 超时修复 |
| da78557 | 2026-03-25 | 导出增加音频URL、教材ID/词书ID/单元ID字段 |
| 8b1fe9e | 2026-03-25 | 英美音标分离 + 教材来源结构化 + 音频URL支持 |
| 6092405 | 2026-03-24 | 生产记录自动导出 — 按 Package 聚合 AI 用量 + xlsx 导出 |
| e625295 | 2026-03-24 | 大规模导入+生产性能优化 — 支撑 4400 词 / 9000 义项 |
| 7a74982 | 2026-03-23 | AI 用量追踪 — 全路径埋点 + 统计 API + 测试修复 |
| 1df501a | 2026-03-19 | 生产部署配置 + 质检评估 Gemini ERROR 注明原因 |

### fix（24 个）
| Hash | 日期 | 主题 |
|---|---|---|
| 4674534 | 2026-03-31 | 审核页面刷新时不再闪 loading，仅首次加载显示 |
| d201384 | 2026-03-31 | 自动批准时同步清理残留的 pending review_items |
| 2575e75 | 2026-03-31 | C6 语块中文翻译字数规则移除上限检查 |
| da8f799 | 2026-03-27 | N5 话术字数规则移除上限检查 + 提效报告文档改版 |
| 892baa9 | 2026-03-27 | 导出按义项级别过滤 + 导入音频URL列名别名补全 |
| f27e677 | 2026-03-27 | 模型定价表更新为 Gateway 人民币费率 |
| 48d49ef | 2026-03-27 | 助记质检规则优化——标点不计入字数 + N5 阈值对齐 + 渐进式轮询 |
| 1ef6318 | 2026-03-26 | sources 表教材 ID 字段从 Integer 改为 String |
| 92cd6f3 | 2026-03-25 | 添加 openpyxl 运行时依赖，修复 Docker 环境导入/导出报错 |
| c3002ae | 2026-03-25 | PreviewRow 接口补齐 ipa_uk/ipa_us 字段，修复 CI 构建失败 |
| fad7394 | 2026-03-25 | ReviewItem 并发重复防护 + 错误处理改进 |
| 4bdb5ee | 2026-03-25 | 代码审查修复 — func.now() 替换、缓存、确定性查询、遗漏路径 |
| d2fb693 | 2026-03-25 | 审核重生成路径补充 package_id，确保成本完整归因 |
| 7fdc3c1 | 2026-03-24 | 生产环境 gunicorn 启用 access log 和 info 级别日志 |
| d859173 | 2026-03-20 | Settings 添加 strip_whitespace 处理 Gaea 环境变量末尾换行符 |
| b1b18bf | 2026-03-20 | 还原 nginx-svc/run shebang + 修复 nginx 配置目录 |
| f357ad1 | 2026-03-20 | alembic env.py 改用 Settings 读取数据库连接串 |
| d218bd0 | 2026-03-20 | Settings 添加 database_url_migrate 字段，避免 extra_forbidden 报错 |
| 299903f | 2026-03-19 | Layer 2 AI 调用失败项标记为 LAYER2_FAILED，进入人工审核队列 |
| 0eb7808 | 2026-03-19 | 将 gaea 生产配置文档加入 gitignore（含敏感凭据） |
| 7b37011 | 2026-03-19 | .dockerignore 添加 docs/prompts/ 例外，修复 COPY 失败 |
| 5278eb5 | 2026-03-19 | 切换 Stage 2 基础镜像为 Alpine，绕过 Gaea 内存限制 |
| 9bf5cb8 | 2026-03-19 | 修复 Gaea 构建环境 apt Post-Invoke 脚本执行失败 |
| 657bbe2 | 2026-03-19 | 修复前端 TypeScript 编译错误（未使用变量、类型收窄） (#1) |

### perf（2 个）
| Hash | 日期 | 主题 |
|---|---|---|
| 0ddc6f2 | 2026-03-30 | 人工编辑跳过 Layer 2 AI 质检，仅执行 Layer 1 算法规则 |
| 4036346 | 2026-03-25 | gunicorn worker 4→6 + 一键修复 BATCH_SIZE 3→4 |

### refactor（1 个）
| Hash | 日期 | 主题 |
|---|---|---|
| e14b56a | 2026-03-31 | L2 质检 prompt 移除字数检测，统一由 L1 算法规则处理 |

### docs（6 个）
| Hash | 日期 | 主题 |
|---|---|---|
| 604e203 | 2026-03-31 | 添加测试环境文档、话术示例及消息对话文档 |
| aa48eb3 | 2026-03-27 | 修正 gpt-5.2 用途描述 + gitignore 生产环境配置模板 |
| da79b19 | 2026-03-27 | 修正 AI 成本估算文档 gpt-5.2 用途描述 |
| 3f507e7 | 2026-03-27 | 添加 S9 词汇生产 AI 成本估算文档 |
| 2316852 | 2026-03-24 | 更新 CLAUDE.md 和 README.md 中过时的数据 |
| 2ab97b3 | 2026-03-19 | 更新质检评估报告选型决策流程，与代码 fail-safe 机制对齐 |

### chore（1 个）
| Hash | 日期 | 主题 |
|---|---|---|
| ff9f31d | 2026-03-24 | 重新生成 package-lock.json（前端依赖补全） |

### add（9 个，非规范，**重点核查**）
| Hash | 日期 | 主题 |
|---|---|---|
| e63bb63 | 2026-03-20 | add execlin2222 |
| 2717235 | 2026-03-20 | add execlined |
| f2a5155 | 2026-03-19 | 修复 s6-overlay oneshot migrate/up 脚本语法错误 |
| fb65973 | 2026-03-19 | add gaea5 |
| 93d26c8 | 2026-03-19 | add gaea4 |
| 115de6a | 2026-03-19 | add gaea3 |
| 49d79e0 | 2026-03-19 | add gaea2 |
| 0d300a9 | 2026-03-19 | add gaea1 |
| 985940f | 2026-03-19 | add gaea |

> ⚠️ "add execlin2222" / "add execlined" 字面像临时 Excel 文件，建议 `git show e63bb63 2717235` 核查内容。

---

## 下一步

1. **方案选择**：
   - 方案 A（保守）：在 GitLab 创建 `release → main` 的 MR，分批 cherry-pick 上面 34 个无风险 commit + 评估后的 11 个 feat，最后处理 9 个 add commit
   - 方案 B（激进）：直接 `git checkout main && git merge release` 一次性合回，依赖 CI 测试兜底
2. 9 个 "add *" commit 可考虑用 `git rebase -i` squash 成 1 个 "feat(deploy): Gaea 首次部署配置" 再合
3. 6 个 fix(gaea) 类的（apt Post-Invoke、s6-overlay 语法、Alpine 切换、nginx 配置等）可一起 squash 成 "fix(deploy): Gaea 容器化首版调通"
