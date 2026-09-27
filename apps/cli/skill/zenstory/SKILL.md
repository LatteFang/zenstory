---
name: zenstory
description: Reads, writes and organizes the user's novel projects stored in zenstory (chapters/drafts, outlines, character profiles, lore/world-building, materials) through the zenstory CLI and its Agent API. Use when the user mentions zenstory, refers to their novel or story project kept in zenstory, or asks to read, continue, draft, revise, or reorganize chapters, outlines, characters or settings stored there, or to check continuity across a zenstory project (e.g. "continue chapter 12 in zenstory", "add this character to my zenstory novel", "在 zenstory 里续写第三章", "把人物设定存到 zenstory").
compatibility: Requires Node.js 20+ (runs the zenstory CLI via a global install or npx) and network access to api.zenstory.ai.
metadata:
  version: "0.1.0"
  homepage: "https://zenstory.ai"
  cli: "zenstory"
  api_base: "https://api.zenstory.ai/api/v1"
---

# zenstory

zenstory is an AI-assisted novel writing workbench. Everything in a project is a **file**
(outline, draft chapter, character, lore, material, folder) arranged in a folder tree. This
skill operates those files with the `zenstory` CLI, which wraps the public Agent API.

## Running the CLI

Use `zenstory ...` if it is installed (`command -v zenstory`). Otherwise use
`npx -y zenstory ...` with exactly the same arguments. Examples below use `zenstory`.

Always add `--json` when you need to parse output. Errors go to stderr; the exit code tells
you what happened: `0` ok, `2` usage error, `3` auth/permission, `4` not found,
`5` rate limited, `1` anything else.

## Setup check (do this first, once per session)

```bash
zenstory whoami --json
```

- Exit `0`: note `scopes.read` / `scopes.write`. Without `write`, you can only read — tell
  the user before planning edits.
- Exit `3` ("Not logged in" / key rejected): ask the user to create an Agent API key in
  **zenstory → Settings → Agent** (enable the `write` scope if they want you to edit), then
  run this **themselves** in their own terminal and paste the key when prompted (input is
  hidden, so the key stays out of shell history):

  ```bash
  npx -y zenstory login
  ```

  Self-hosted zenstory: add `--api-base https://<their-server>/api/v1`.
- Never ask the user to paste the key into the chat, and never put a key on a command line.
  If they already pasted a key into the chat, treat it as exposed: recommend they
  **regenerate it in Settings → Agent** and log in again with the new key as above. Never
  echo, log or repeat a key.

## Orient in a project

```bash
zenstory projects list --json                 # pick the project id
zenstory files tree <projectId>               # folders + titles + ids, no content
zenstory files list <projectId> --type draft --json   # chapters (content omitted)
```

Projects created in the web app start with root folders whose ids are predictable, e.g.
`<projectId>-draft-folder` (正文/Drafts), `<projectId>-outline-folder` (大纲/Outlines),
`<projectId>-character-folder` (角色/Characters), `<projectId>-lore-folder` (设定/World
Building), `<projectId>-material-folder` (素材/Materials). Confirm with `files tree` before
relying on them. See [references/concepts.md](references/concepts.md) for file types,
folders per project type, and what writing-context returns.

## Workflow: continue or revise a chapter

1. Find the chapter: `zenstory files list <projectId> --type draft --json` (or `search`).
2. Gather context **before writing**:
   ```bash
   zenstory context <projectId> --file <chapterId> --query "what happens next" --json
   ```
   This returns AI-ranked snippets (parent outline, previous chapter, characters, lore,
   retrieved passages). Open any item you need in full with `zenstory files get <source_file_id>`.
3. Note the chapter's current `updated_at`, then read it into a private temp directory
   (use one directory per session and name files by file id):
   ```bash
   zenstory files get <chapterId> --fields id,title,updated_at --json   # note updated_at
   dir=$(mktemp -d)
   zenstory files get <chapterId> -o "$dir/<chapterId>.md"
   ```
4. Edit `$dir/<chapterId>.md` (keep the user's existing text unless asked to rewrite it).
5. Save, passing the `updated_at` you noted so the write is refused if the user changed
   the chapter in the browser meanwhile:
   ```bash
   zenstory files put <chapterId> --content-file "$dir/<chapterId>.md" \
     --if-updated-at <updated_at> --json
   ```
   If it fails with "changed on the server", re-read, re-merge, and retry with the new
   `updated_at`. The CLI prints `backupPath` (the previous content, saved locally) and the
   server keeps a version the user can roll back to.

`files put` **replaces the whole content**. Never put a partial chapter or a summary back.
It refuses content shorter than half of the current text unless you pass `--allow-shrink`
— only do that after the user confirmed the cut.

## Workflow: write a new chapter

```bash
zenstory context <projectId> --query "chapter 13: the duel at the pass" --json
# write the chapter to "$dir/ch13.md" (dir=$(mktemp -d)), then:
zenstory files create <projectId> --type draft --title "第十三章 关山对决" \
  --parent <projectId>-draft-folder --content-file "$dir/ch13.md" --json
```

Match the title pattern of existing chapters (look at `files list --type draft`). For a
chapter outline use `--type outline` under the outline folder.

## Workflow: characters, lore and materials

```bash
zenstory search <projectId> "林远" --type character --json      # avoid duplicates first
zenstory files create <projectId> --type character --title "林远" \
  --parent <projectId>-character-folder --content-file "$dir/linyuan.md" \
  --metadata '{"role":"protagonist"}' --json
zenstory files create <projectId> --type lore --title "灵脉体系" \
  --parent <projectId>-lore-folder --content-file "$dir/lingmai.md" --json
```

Materials (素材) use file type `snippet` (`--type material` is accepted as an alias).
If the project has no folders (projects created through the API start empty), create them
first: `zenstory files create <projectId> --type folder --title "角色" --json`.

## Workflow: continuity check

```bash
zenstory search <projectId> "玉佩的来历" --limit 10 --json
zenstory search <projectId> "Chen's scar" --type draft --type outline --json
```

Results carry `id`, `title`, `file_type`, `snippet`, `line_start` and `score`. Open the
source with `files get <id>` before asserting a fact. Newly written files are indexed in
the background, so a just-saved change may take a moment to appear in search.

## Safety rules

- **Confirm before destructive actions.** Ask the user before `files delete` /
  `projects delete` (both need `--yes`) and before `files put` that would shrink or
  replace substantial existing text (e.g. more than a few paragraphs). Show what will
  change.
- **Read before you write.** Never overwrite a file you have not just read; always pass
  `--if-updated-at` to `files put`.
- **Respect rate limits** (per key, per hour): read 2000, write 1000, search 500,
  writing-context 500. Use `files list --fields` / `files tree` instead of fetching every
  file's content, don't poll, and stop on exit code `5` and tell the user.
- **Keep secrets out of output.** The CLI masks the key; never print config files or
  environment variables that contain it.
- **Stay in scope.** Only touch the project the user named. If a command fails with exit
  `3` on write, the key likely lacks the `write` scope or is limited to other projects —
  report it instead of retrying.
- Prefer `--json` for anything you parse; use human output only to show the user.

## Reference

- [references/cli.md](references/cli.md) — every command, flag, endpoint and JSON shape.
- [references/concepts.md](references/concepts.md) — file types, folder conventions,
  writing-context contents, ordering caveats.
