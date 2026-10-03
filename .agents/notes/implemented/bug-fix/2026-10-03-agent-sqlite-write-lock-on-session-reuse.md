# Agent Note: 同一对话的下一轮不得让请求级 session 攥住 SQLite 写锁

Status: implemented

## Problem

SQLite 部署（本地开发、自托管）上，同一个对话接着问下一轮时，Agent 的所有写工具（create_file / edit_file 等）都失败：每次写入等满 busy_timeout（30 秒）后报 `sqlite3.OperationalError: database is locked`，模型看到失败就反复重试写档，整轮卡住并持续烧 token。第一轮（新建会话）不受影响。

根因在 `agent/service.py` 的 `_resolve_or_create_chat_session_id`：前端带着已存在且活跃的 `session_id` 时，函数把 `candidate.updated_at = utcnow()` 加进 session，但只有 `changed`（需要去激活旧会话或重新激活 candidate）时才 commit。最常见的情况——会话本来就是唯一活跃的——这个脏 UPDATE 留在 session 里：

- SQLite 分支（`_should_offload_session_work` 只对 `postgresql` 为真）直接用**请求级 session**（`Session(sync_engine)`，autoflush=True）。随后 `SessionLoader.load_chat_session` 的第一条读查询触发 autoflush，pysqlite 在 DML 前隐式 `BEGIN`，写事务和库级 RESERVED 锁一直挂到整轮 SSE 结束、历史保存 commit 才释放。工具跑在 `asyncio.to_thread` 的工作线程里、各自 `create_session()`，是另一个连接，拿不到写锁。
- PostgreSQL 分支用 `with create_session()` 包住解析逻辑，脏修改在 close 时被直接丢弃：不锁库，但 `updated_at` 的刷新在生产上从未落库。

## Decision

- `_resolve_or_create_chat_session_id` 复用已有会话时，即使没有去激活旧会话或重新激活 candidate，也在刷新 `updated_at` 后立即 `session.commit()`，提交前取出 `candidate.id` 返回（不再 `refresh`）。两种方言行为一致：刷新真正落库，请求级 session 不留脏状态。
- `process_stream` 在设置 `ToolContext`、启动工作流之前，若请求级 session `in_transaction()` 则 `commit()`，作为整类问题的兜底：工作流前任何步骤（会话解析、历史加载、技能目录、system prompt 组装）在请求级 session 上留下已 flush 的写，都在工具开始写库前提交掉。只读时 pysqlite 不会发出 `BEGIN`，这次 commit 不向数据库发语句；PostgreSQL 分支此时请求级 session 没有事务（路由层已 `rollback()`，前置步骤都 offload 到独立 session），不进分支。
- 审计结论：`_resolve_or_create_chat_session_id` 的其余分支（旧客户端运行时 UUID 回落、无 `session_id` 取最新活跃、新建会话）凡有写都已 commit；`SessionLoader.load_chat_session` 修复多活跃时会 commit；`_prepare_prompt_artifacts` 只读，技能用量走独立 session。修复前唯一的残留写就是上面的 `updated_at`。

## Alternatives considered

- **只在 `changed` 时刷新 `updated_at`，会话本来就活跃时什么都不写**。最强理由：每轮少一次单行 UPDATE + COMMIT，而且 PostgreSQL 上这次刷新本来就从未落库，生产行为不变。被否：SQLite 上这次刷新过去是会随轮末历史保存一起落库的，删掉等于悄悄改掉开发环境的语义；保留并立即提交让两种方言对齐到同一个"复用即刷新最近使用时间"的契约，代价只是一次单行写，与轮末历史保存同量级。
- **SQLite 也走 offload 分支，所有前置步骤改用独立 session**。最强理由：请求级 session 在流式期间彻底不碰写，从结构上消灭这一类问题。被否：`SessionLoader` 明确把 SQLite/测试保留在调用方 session 上以维持内存库与现有 fixture 的确定性，改动面横跨 SessionLoader、技能注入与大量测试，超出一个 bug 修复的范围；工作流前的兜底 commit 以一行代价拿到同样的不变量。
- **只加工作流前的兜底 commit，不改 `_resolve_or_create_chat_session_id`**。最强理由：一处覆盖所有前置步骤。被否：PostgreSQL 分支的解析不经过请求级 session，刷新仍会被丢弃；SQLite 上写锁也会在历史加载与上下文组装期间被无谓持有。根因与兜底都要修。

## Consequences

- 收益：SQLite 部署上同一对话的后续轮次，工具写库不再被请求级 session 锁死，Agent 不再因 "database is locked" 反复重试；会话 `updated_at` 在两种方言上都按"复用即刷新"落库。
- 代价：PostgreSQL 生产上每轮新增一次 `chat_session` 单行 UPDATE + COMMIT。SQLite 分支的兜底 commit 会让请求级 session 上已加载的 ORM 实例过期，之后访问会惰性重查（`process_stream` 之后只用标量与字典，历史保存会重新加载会话）。若将来某个前置步骤在请求级 session 上留下了已 flush 的写，它会在工作流前就被提交，而不是像过去那样在失败/取消路径随 session 关闭被回滚——前置步骤的写必须自己保证完整，不能指望轮末回滚兜底。

## Verification

`cd apps/server && pytest tests/test_agent/test_agent_service_session_id.py -q --no-cov`。回归测试用文件型 SQLite（WAL + 200ms busy timeout）：解析已有会话后，另一个 engine 的写入必须成功；`process_stream` 第二轮里模拟工具在独立连接写库必须成功；前置步骤故意留下已 flush 的写时兜底 commit 必须放锁。回退修复后前两类测试以 `database is locked` 失败，回退兜底后第三个测试失败，`updated_at` 落库测试在旧实现下失败。
