# Agent Note: Agent API 补齐项目结构、章节顺序、移动与版本历史

Status: implemented

## Problem

外部 agent 通过 `zenstory` CLI / Agent API 操作项目时，有四处和网页端不一致，导致 skill 只能教 agent 绕路：

- `POST /api/v1/agent/projects` 只插入 `Project` 行，项目没有网页端按 `project_type` 建的默认根文件夹（设定/角色/素材/大纲/正文……）。skill 只好让 agent「先自己建文件夹」，而站内 Agent 工具与 skill 文档都依赖可预测的 `{project_id}-draft-folder` 这类 id。
- 新建文件的 `order` 固定为 0，更新接口也不能改 `order`。列表按 `order`、再按创建时间倒序排，外部 agent 写出的章节在列表里是倒序的，写作上下文按 `order` 找「上一章」也会找错。
- 没有移动接口；新建文件时只校验 parent 存在且同项目，不校验 parent 是文件夹（网页端 REST 与站内 Agent 工具都由 `services/file_tree_rules.py` 要求 parent 必须是 folder）。挂到普通文件下的章节在文件树里不可见。
- 没有版本接口。Agent API 的 `PUT` 已经会记版本，但外部 agent 看不到、也回滚不了，唯一的撤销手段是 CLI 写在本机的备份文件；新建文件时的正文也不记版本，第一次修改之后原文在服务端就找不回来了。

## Decision

- **默认文件夹**：新增 `services/project_service.py`：`create_project_with_default_folders(session, project, lang)` 在同一事务里写入项目和 `config/project_templates.get_folders_for_type` 给出的根文件夹（id 为 `{project_id}-{folder_id}`），失败时回滚后原样抛出；`resolve_template_lang(accept_language)` 取 `Accept-Language` 的主语言，缺省 `zh`。网页 `POST /api/v1/projects` 与 `POST /api/v1/agent/projects` 都调用它；网页端自己只负责默认项目名。Agent 端失败时返回 500 `ERR_INTERNAL_SERVER_ERROR`，响应在项目字段之外多一个 `folders: [{id, title, file_type, order}]`。
- **项目数上限与激活事件在 service 里**：`create_project_with_default_folders` 先调用 `quota_service.check_project_limit`，达上限抛 402 `ERR_QUOTA_PROJECTS_EXCEEDED`（与网页端原来的文案相同，不写任何数据），建成后调用 `activation_event_service.record_once` 记 `project_created`（失败只记日志）。两个入口都把 `APIException` 原样放行、只把其它异常翻译成 500，所以任何调用方都绕不过上限。复制灵感（`api/inspirations.py`）走 `copy_inspiration_to_project`，不经过这个函数，仍只在自己那里检查一次，不会重复计数。
- **限定项目的 key 不能建项目**：`POST /api/v1/agent/projects` 在 key 带项目白名单（`project_ids` 不为 `null`，含空列表）时直接返回 403 `ERR_NOT_AUTHORIZED`，`error_detail` 说明「This API key is limited to specific projects and cannot create new projects」——这种 key 读写不了自己新建的项目。
- **顺序**：`services/file_tree_rules.py` 新增 `resolve_new_file_order`，是从网页 `create_file` 抽出来的原逻辑：显式 `order` 经 `resolve_persisted_sequence_order` 归一化（`draft/outline/script` 的「第N章 / Chapter N」标题以 N 为准）；未给 `order` 时取标题或 metadata 里的序号，否则排在同父节点兄弟之后。网页 `create_file` 与 Agent `create_file` 都调用它。Agent `FileCreate`、`FileUpdate`、`FileMove` 的可选 `order` 限定 `0..2147483647`（`services/file_tree_rules.MAX_FILE_ORDER`，`File.order` 是 32 位 INTEGER，超出在 PostgreSQL 上会 500），越界 422；网页 `FileCreate.order`、`FileUpdate.order` 同样加了上界（不加下界，保持原契约）；Agent `PUT` 在给出 `order` 或 `title` 时按网页 `PUT` 的规则重算 `order`。
- **parent 校验与移动**：Agent 新建文件与新增的 `POST /api/v1/agent/files/{file_id}/move`（body `{parent_id: str|null, order?: int≥0}`，`parent_id` 必填、`null` 表示项目根；scope `write`）都调用 `validate_parent_assignment`：parent 不存在/跨项目/已删除 → 400 `ERR_FILE_NOT_FOUND`，不是 folder 或成环（移到自己或后代下）→ 400 `ERR_VALIDATION_ERROR`，`error_detail` 带原因。这对 Agent 新建文件是契约变化：以前 `parent_id: ""` 被当成项目根、挂到非 folder 下也放行，现在两者都是 400。移动不改内容、不记版本，给了 `order` 才改顺序；成功后像 `PUT` 一样异步重新写入向量索引，让索引 metadata 里的 `parent_id` 跟上新位置。网页 `POST /api/v1/files/{id}/move` 原来也不更新索引，现在同样重新写入。
- **版本**：新增三个端点，复用 `FileVersionService`（新增 `get_version_by_number`）。三个版本端点和移动端点是同步 `def`（与网页 `api/versions.py` 一致），由 FastAPI 放进线程池执行——回滚会拿 `threading.Lock`（SQLite）或 `SELECT ... FOR UPDATE`（PostgreSQL），不能跑在事件循环上：
  - `GET /api/v1/agent/files/{file_id}/versions`（scope `read`；`limit` 1–100 默认 50、`offset`、`include_auto_save` 默认 false）→ `{versions, total, limit, offset, file_id, file_title}`，每项为 `id, file_id, project_id, version_number, is_base_version, word_count, char_count, change_type, change_source, change_summary, lines_added, lines_removed, created_at`，不含正文，最新在前。
  - `GET /api/v1/agent/files/{file_id}/versions/{version_number}`（scope `read`）→ 上述字段加 `content`（`get_content_at_version` 重建）。
  - `POST /api/v1/agent/files/{file_id}/versions/{version_number}/rollback`（scope `write`）→ 调用与网页回滚相同的 `rollback_to_version`（文件写锁、恢复正文、配额允许时记一个 `restore` 版本、配额满时仍恢复正文），返回 `{success, message, file_id, restored_version, new_version_number, snapshot_created, version_quota_exceeded, updated_at}`，并像 `PUT` 一样异步更新向量索引。
  - 版本号不存在 → 404 `ERR_VERSION_NOT_FOUND`。
- **初始版本与版本额度**：Agent `create_file` 在正文非空时记第 1 版（`change_type=create`，来源与配额口径同 `PUT`：`user`），与站内 Agent 工具 `create_file` 的做法一致；快照失败不阻止创建。Agent 新建文件与 `PUT` 的响应和网页 `PUT` 一样带 `version_quota_exceeded: bool`：per-file 版本额度已满时正文照常保存、不记版本，该字段为 `true`；其它快照失败只记日志，字段为 `false`。
- **写作上下文超时**：`GET /agent/projects/{id}/writing-context` 组装超过 `WRITING_CONTEXT_TIMEOUT_SECONDS`（10 秒）返回 504 `ERR_SERVICE_UNAVAILABLE`（原来引用了不存在的 `ErrorCode.INTERNAL_ERROR`，超时时自身抛 `AttributeError` 变成 500）。
- **统一的鉴权与隔离**：所有新端点使用既有的 `require_scope` 与 `require_agent_rate_limit`（读 `agent_read` 2000/h，写 `agent_write` 1000/h）；按文件寻址的端点通过 `_load_accessible_file`：别人的文件或已删除项目 → 404，key 的项目白名单之外 → 403。
- **`/skill.md`**：端点表由路由自省生成，新路由以函数名 `move_file`、`list_file_versions`、`get_file_version`、`rollback_file_version` 作为摘要、带正确 scope 出现；`metadata.capabilities` 加入 `file_tree, version_history`，工作流示例补充默认文件夹、`order` 与「撤销一次修改」。
- **CLI 0.2.0**：`projects create` 打印默认文件夹，`--lang zh|en` 决定文件夹标题语言，以 `Accept-Language` 发送，缺省取 `ZENSTORY_LANG`，其次 `LC_ALL`、`LANG`（`zh*` → `zh`，其余 → `en`）；`files create/put --order`（整数 0..2147483647）；`files create/put` 在 `version_quota_exceeded` 为 `true` 时往 stderr 打警告（`--json` 输出里带该字段）；`files rollback` 在 `new_version_number` 为 `null` 时按 `version_quota_exceeded` 区分「版本额度已满」与「没有记下快照」；`files move <fileId> --parent <folderId|root> [--order n]`；`files versions`、`files version <fileId> <n> [-o]`（复用 `writePrivateFile`）、`files rollback <fileId> <n> --yes`。skill 文档改为：默认文件夹已存在、用 `--order` 排章节、用版本历史撤销，本机备份作为第二道保险；版本额度满时 CLI 会警告，只剩本机备份。

## Alternatives considered

- **Agent API 直接转调网页端路由函数（或 `api/versions.py` 的响应模型）**。最强理由：零复制，行为天然一致。被否：网页路由依赖 `get_current_active_user` 与 Bearer 鉴权，返回网页端的错误码组合（例如非 owner 返回 403 而不是 404），Agent API 需要自己的鉴权依赖、白名单检查和「不泄露存在性」的 404；共享层应当是 service，而不是路由，这也是 `2026-04-29-thin-api-shared-invariants-in-services.md` 的约定。
- **让 CLI 在 `projects create` 之后自己建文件夹**。最强理由：服务端零改动，老服务器也能用。被否：文件夹 id 无法做到 `{project_id}-draft-folder` 这种可预测形式（站内 Agent 工具的根文件夹修复逻辑依赖它），直接调 HTTP 的 agent 仍然拿到空项目，规则会在 CLI 与服务端各写一份。
- **显式 `order` 原样落库，不做章节标题归一化**。最强理由：调用方说什么就是什么，最好理解。被否：网页端已经以章节标题序号为准，文件树排序（`build_sequence_sort_key`）也按标题序号；Agent 端单独原样落库会让两个入口对同一个请求存出不同的 `order`，且排序结果与存储值不一致。

## Consequences

- 收益：外部 agent 建出的项目与网页端结构一致，skill 不再需要「自己建文件夹」的说明；章节按序排列，写作上下文能找到正确的上一章；文件树不再出现挂在普通文件下的隐形章节；撤销有了服务端路径，经 API 带正文新建的文件从第 1 版起就可以回滚。
- 代价：Agent 新建文件未给 `order` 时不再固定为 0，而是按标题序号或追加到末尾（行为变化，旧客户端若依赖 0 会看到不同的排序）；带正文新建文件会多占一个版本配额；`POST /agent/projects` 的响应多了 `folders` 字段，并且现在会因项目数上限返回 402、因 key 带项目白名单返回 403（以前都能建成功）；Agent 新建文件的 `parent_id: ""` 与非 folder parent 从放行变成 400；CLI 的 `--lang` 缺省按本机语言环境取值，非中文环境建出的项目文件夹标题是英文（服务端缺省仍是中文）；`/skill.md` 端点表的摘要仍是函数名。
- 已知缺口（网页端相同，本次不修）：两个并发的移动请求可能各自通过成环检查，然后互相挂到对方下面形成环；`validate_parent_assignment` 不锁父链。文件树的 `is_descendant_of` 与 CLI 的 `buildTree` 都能容忍已有的环，不会死循环。

## Verification

- `cd apps/server && python -m pytest tests/test_api/test_agent_api_structure.py`：项目数上限（Agent 402 且不落库、未满时 200 带文件夹并记 `project_created`、service 本身拒绝、网页端只检查一次）、带白名单的 key 建项目 403、`PUT`/新建/回滚在版本额度满时的 `version_quota_exceeded`、已删除文件或项目的移动与版本端点 404、移到已删除文件夹 400、`parent_id: ""` 400、Agent 与网页 `order` 上界、Agent 与网页移动后重新写入索引、版本与移动端点是同步函数、写作上下文超时 504；三种 `project_type` 的默认文件夹与 `Accept-Language`、`order` 的新建/追加/章节标题/负数、parent 非 folder/跨项目/不存在、移动到文件夹与根目录、成环与移到自身、缺 `parent_id`、版本列表/分页/详情/回滚（新版本为 `restore`，正文恢复）、不存在的版本号、scope 与白名单 403、他人文件 404、`/skill.md` 端点表。
- `tests/test_api/test_projects.py` 的回滚用例改为 monkeypatch `services.project_service.get_folders_for_type`，网页建项目失败时仍不落库。
- `cd apps/cli && pnpm test`：`projects create` 打印文件夹、`--lang` 与 `ZENSTORY_LANG`/`LC_ALL`/`LANG` 决定的 `Accept-Language`、白名单 key 的 403 提示、版本额度满时 `files put/create` 的警告、`files rollback` 按 `version_quota_exceeded` 区分提示、`--order` 超过 2147483647 退出码 2、`--order`、`files move`、`files versions|version|rollback` 的请求字段与输出。
- `rg "file_tree_rules" apps/server --glob '*.py'` 应命中 `api/files.py`、`api/agent_api.py` 与 `agent/tools/file_ops/crud.py`；`rg "create_project_with_default_folders" apps/server/api` 应命中 `projects.py` 与 `agent_api.py`。
