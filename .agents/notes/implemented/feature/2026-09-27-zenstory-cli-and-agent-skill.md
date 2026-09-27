# Agent Note: 以 `zenstory` Node CLI + 标准 Agent Skill 作为外部 AI 助手的接入方式

Status: implemented

## Problem

zenstory 希望用户能让 Claude Code、OpenClaw、Codex 等外部编码 agent 直接操作自己的小说项目，但目前只有两样东西：

- `/skill.md`：由 `services/skill_md_service.py` 从路由自动生成的 API 文档。frontmatter 不符合标准（`name` 含空格和中文，夹带 `version`、`api_base`、`triggers` 等非标准字段），不能装进 `~/.claude/skills/`。
- 设置 → Agent 里的「复制给 AI 的提示词」：把 API Key 明文拼进一段提示词，让用户贴进对话，由 agent 读文档后自己用 curl 拼 HTTP 请求。Key 因此进入对话历史，agent 拼请求也容易出错。

没有 CLI，也没有可安装的 skill 包。另外，首页（`DashboardHome`）常驻一张「连接你的 AI 助手」卡片，对大多数只在网页里写作的用户来说是噪音。

## Decision

1. **CLI**：`apps/cli` 是 npm 包 `zenstory`（bin 名 `zenstory`，当前版本 0.2.0），零运行时依赖，要求 Node ≥ 20，TypeScript 编译到 `dist/`。命令一一对应公开的 Agent API（`/api/v1/agent/*` 与向量搜索）：`login / logout / whoami`、`projects list|get|create|update|delete`、`files list|tree|get|create|put|move|delete`、`files versions|version|rollback`、`search`、`context`、`skill install|path`。`files create/put` 支持 `--order`；项目默认文件夹、移动与版本接口见 `2026-09-27-agent-api-structure-and-versions.md`。所有命令支持 `--json`；退出码约定为 0 成功、1 错误、2 用法/400、3 认证、4 不存在、5 限流。
2. **凭证**：`zenstory login` 不带 `--key` 时在终端里隐藏输入、提示粘贴 key；非终端环境要求 `--key -` 从标准输入读取；直接写 `--key eg_...` 仍可用但会提示 shell 历史风险。key 先经 `GET /agent/projects` 验证，再写入 `$XDG_CONFIG_HOME/zenstory/config.json`（目录 0700、文件 0600，原子写入）。保存的 key 绑定登录时的 API 地址：环境变量 `ZENSTORY_API_BASE` 与之不同时拒绝发送，除非同时提供 `ZENSTORY_API_KEY` 或显式 `--allow-base-override`；API 地址只接受 https（localhost 例外）。所有输出（含错误信息）都对 key 打码。
3. **写入安全**：服务端版本历史是撤销的主路径（`files versions` / `files version` / `files rollback --yes`）；`files put` 另外先读取当前内容并备份到 `$XDG_CACHE_HOME/zenstory/backups/<fileId>-<ts>.md`（0600）；支持 `--if-updated-at` 乐观锁；新内容短于原文一半时须加 `--allow-shrink`，空内容须加 `--allow-empty`；删除与回滚须加 `--yes`。`files get -o` 与 `files version -o` 经同目录临时文件改名写入（0600），拒绝符号链接，已有文件须加 `--force`。服务端 Agent API 的 `update_file` 在内容变化时与网页编辑器一样创建版本快照（类型 `ai_edit`，占用同一份版本配额，配额满或快照失败不阻止保存）；文件列表排序以 `File.id` 作最后的决胜键。
4. **标准 skill 包**：`apps/cli/skill/zenstory/`（`SKILL.md` + `references/cli.md` + `references/concepts.md`）随 CLI 发布，教 agent「先读写作上下文，再读取、编辑、带 `--if-updated-at` 回写章节」、用 `--order` 排章节、把文件放进（或 `files move` 进）默认文件夹、用版本历史撤销修改，临时文件用 `mktemp -d` 按文件 id 命名，并要求不在对话里索取 key、已泄露时提示用户重新生成。`zenstory skill install` 默认装到 `~/.claude/skills/zenstory`，`--target codex|agents` 为 `~/.agents/skills`，`--target openclaw` 为 `$OPENCLAW_STATE_DIR/skills`（默认 `~/.openclaw/skills`）。已存在的目标默认拒绝；`--force` 只替换「看起来是先前安装」的目录（仅含 `name: zenstory` 的 `SKILL.md` 与 `references/`），符号链接只解除链接不跟随，经临时目录改名替换。`SKILL.md` 的 `metadata.version` 由测试保证与 `package.json` 一致。
5. **`/skill.md` 对齐标准**：frontmatter 顶层只有 `name: zenstory`、`description`、`metadata`；标准要求 metadata 是字符串映射，所以原来的 `version`、`api_base`、`rate_limit`、`triggers`、`capabilities`、`file_types` 移到 `metadata` 下，嵌套结构改为逗号分隔字符串。这对解析旧顶层字段的外部程序是**破坏性变更**（仓库内没有这类消费者）。正文在认证说明之前推荐 CLI 接入；`API_BASE_URL` 不是官方地址时，命令自动带上 `--api-base`。服务端的异常处理器现在透传响应头，限流时的 `Retry-After` 能到达客户端。
6. **入口**：首页的 `AgentConnectionCard` 已删除。设置 → Agent 顶部是三步接入指引（创建 key → `npx zenstory login` 并按提示粘贴 → `npx zenstory skill install`），附 `/skill.md` 链接供其他 agent 阅读；创建 key 后的弹窗给出同样的终端命令，不再提供把 key 拼进提示词、贴进对话的做法。网页的 API 地址不是官方地址（自部署）时，命令与链接改用该地址。README 与 `docs/docker-compose.md` 的接入说明同步改为 CLI 流程。
7. **CI**：`.github/workflows/ci.yml` 新增 `cli-test` 任务（安装、测试、构建、`npm pack --dry-run`），`scripts/ci/ci.sh` 的本地闸门同样运行 CLI 测试。

这里的 skill 脚本和 CLI 都运行在**用户自己的机器**上，由用户的 agent 执行，因此不适用「服务端技能不执行代码」那份决策（见 `2026-09-27-standard-skills-without-execution.md`）；服务端只提供 HTTP API，权限边界仍由 API Key 的 scope（read/write）与限流保证。

## Alternatives considered

- **stdio MCP server（`npx zenstory-mcp`）**。最强理由：工具直接出现在 agent 的工具清单里，不用解析命令行输出。被否：OpenClaw 等不支持 MCP 的客户端用不了；工具 schema 要和 API 同步维护两份。以后可以在同一个包里加一个薄的 MCP 入口，复用 CLI 的 HTTP 客户端。
- **Python CLI（pipx / uv）**。最强理由：能和后端共用 Pydantic 模型。被否：大多数编码 agent 用户已经有 Node，却不一定有合适的 Python 环境；`npx` 可以免安装直接运行。
- **只把 `/skill.md` 改成标准格式，不做 CLI**。最强理由：工作量最小，没有新包要维护。被否：agent 仍然要自己拼 curl 请求和认证头，出错率高，而且 key 还得进入对话。

## Consequences

- 收益：外部 agent 接入变成两条命令，key 不再进入对话历史；skill 符合标准，可以在多个 agent 之间通用；首页更干净。
- 发布顺序是硬性前提：npm 包 `zenstory` 必须在网页和 `/skill.md` 上线**之前**由维护者账号发布。否则任何人都能抢注这个名字，复制设置页命令的用户会运行别人的代码并交出 API Key。
- 代价：多一个需要发版的 npm 包，API 有破坏性变更时要同步发布 CLI；`/skill.md` 和 skill 包里的 `references/cli.md` 是两份文档，前者从路由自动生成，后者手写，可能出现偏差。npm 发布需要维护者账号，不在本次改动范围内。`files put` 的服务端版本快照记录的是写入后的内容；经 Agent API 带正文新建的文件以正文作为第 1 版，但一个在别处创建、此前从未有过版本的文件无法在服务端回滚到 API 写入之前的状态，这种情况只能依赖 CLI 的本地备份。

## Verification

- `pnpm --filter zenstory build && pnpm --filter zenstory test`；`node apps/cli/dist/cli.js --help`。
- 用 skills-ref 类校验或人工核对：`apps/cli/skill/zenstory/SKILL.md` 的 `name` 与目录名一致，description ≤ 1024 字符。
- `curl /skill.md` 的 frontmatter 顶层只有 `name`、`description`、`metadata`。
- 首页不再渲染 `AgentConnectionCard`，`rg AgentConnectionCard apps/web/src` 无命中。
