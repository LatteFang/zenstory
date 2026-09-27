# Agent Note: 素材库剧情（Story）归属到所属小说，修复剧情不可见与跨书合并

Status: implemented

## Problem

`Story` 表没有 `novel_id`，剧情只能经 `story_line_id → StoryLine.novel_id` 找到所属小说，所有读取路径（剧情列表、故事线计数、素材库摘要、搜索、预览）都按这条链过滤。由此产生两个 bug：

1. **剧情不可见**：故事线那一步 LLM 重试耗尽失败、或故事线阶段被关闭时，已经聚合好的剧情全部查不到，花掉的 token 白费。
2. **跨书、跨用户串联**：`StoriesService.upsert_story` 的 `novel_id` 参数被改名为 `_novel_id` 且未使用，只按「标题 + 梗概」全局匹配已有剧情。同一本书被上传两次（同一用户或不同用户，热门网文很常见）时，后一次会更新前一本的剧情行、把自己的情节点挂上去，随后再把它的 `story_line_id` 指到新书的故事线，使剧情从原书消失、出现在别人的书里。

同一轮排查还发现 `handle_orphan_plots.py` 以 `novel_id=` 调用参数名为 `_novel_id` 的任务，每批都在参数绑定时失败并被静默吞掉，孤儿情节分配从未生效。两处都像是批量给「未使用参数」加下划线造成的；全库扫描确认调用端与参数名不一致的只有这一处，带归属语义却被标成未使用的参数只有 `upsert_story` 一处。

## Decision

1. `Story` 新增可空外键 `novel_id`（索引 `ix_stories_novel_id`，外键 `fk_stories_novel_id_novels`）。迁移 `c3d5e7f9a1b2`（接在 `b7e4c2a9d1f3` 之后）按顺序回填：a. 取故事线的 `novel_id`；b. 仍为空的，若挂接的情节点全部来自同一本书则取该书（直接按 `story_plot_links.story_id` 关联子查询，`HAVING COUNT(DISTINCT novel_id) = 1`）；c. 挂接情节点跨多本书的（跨书合并的证据）只统计不猜测，保留 a 的结果或留空。迁移打印一行各类计数，供运维评估历史数据受影响的程度。
2. **写入**：`upsert_story(session, novel_id, ...)` 只在同一本书内按「标题 + 梗概」匹配，新剧情必定带 `novel_id`。`attach_stories_to_storyline` 拒绝挂接其他书的剧情；`attach_plots_to_story` 拒绝其他书的情节点并跳过已存在的链接；孤儿情节分配只接受本批次发给 LLM 的剧情 ID 与情节点 ID，丢弃畸形 ID 和重复配对。这几处的 ID 都来自 LLM 输出，是另外几条可能串书的路径。
3. **读取**：`stories_service.story_in_novel(novel_id)` = `Story.novel_id == novel_id`，或 `novel_id` 为空的旧数据经故事线归属到该书。剧情列表、故事线计数、素材库摘要、预览、统计、故事线导出 Markdown、对话上下文附加都用它；素材库摘要与搜索用同样形状的 `or_/and_` 条件（可走索引），`coalesce` 只出现在 SELECT/GROUP BY 中用于归属。所有路径先校验小说归属当前用户。
4. 修正 `handle_orphan_plots.py` 的参数名，孤儿情节分配恢复生效。
5. 剧情不再依赖故事线才可见，拆解开关随之拆开：故事依赖摘要与情节点，故事线依赖故事；两者默认仍关闭，快照新增 `storylines` 键。

## Alternatives considered

- **不加列，把读取路径改成经 `story_plot_links → plots → chapters` 反查小说**。最强理由：不需要迁移。被否：每次读取都要多表连接，性能差；没有情节点的剧情仍然查不到；也无法在写入时限定匹配范围，跨书合并照样发生。
- **迁移时拆开已被跨书合并的剧情**。最强理由：能把历史脏数据还原。被否：无法可靠判断合并前每本书各自的剧情内容，猜测拆分可能造成新的错误；改为只统计、保留故事线的归属。
- **`novel_id` 设为非空**。最强理由：约束最强。被否：部分历史剧情无法可靠回填，强制非空会让迁移失败或需要丢数据；新数据由写入路径保证必带 `novel_id`。

## Consequences

- 收益：剧情可见性不再受故事线阶段成败影响；上传同一本书不再污染别人的数据；孤儿情节分配恢复生效。
- 上线顺序：迁移必须先于新的 API 与 worker 代码运行，否则查询 `stories.novel_id` 会失败；迁移后要立刻重新部署 Prefect worker，旧 worker 仍会按全局「标题 + 梗概」写入不带 `novel_id` 的剧情（读取条件里的兼容分支能让它们经故事线可见，但不能阻止串书）。
- 代价：一次数据迁移；读取条件多一个兼容旧数据的 OR 分支，等旧数据清理后可以移除；已被跨书合并的历史剧情无法自动还原，只能按迁移输出的计数人工评估。

## Verification

- `tests/test_api/test_materials_story_scope.py`：两本书同标题同梗概生成两行；故事线挂接拒绝他书剧情；无故事线时各读取路径可见；旧数据经故事线仍可见；归属 A 书但指向 B 书故事线的剧情不出现在 B 书；删除（软删除）小说后剧情隐藏。
- `tests/test_models/test_story_novel_id_migration.py`：回填 a/b/c 三种情况与降级。
- `tests/test_flows/unit/test_handle_orphan_plots.py`：参数名回归测试（未修复时失败）；越界的 LLM ID 被丢弃、已有链接不重复创建。
- `tests/test_api/test_materials_story_scope.py::test_library_summary_and_search_filter_stories_without_coalesce`：WHERE 子句中不出现 `coalesce(stories.novel_id`。
