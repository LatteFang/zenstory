# zenstory CLI reference

Run as `zenstory <command>` or `npx -y zenstory <command>`. Every command accepts
`--json` (machine-readable output) and `-h/--help`. Paths below are relative to the API
base (default `https://api.zenstory.ai/api/v1`); all requests send `X-Agent-API-Key`.

## Contents

- [Auth and configuration](#auth-and-configuration)
- [Projects](#projects)
- [Files](#files)
- [Search and writing context](#search-and-writing-context)
- [Skill management](#skill-management)
- [Errors and exit codes](#errors-and-exit-codes)

## Auth and configuration

| Command | Endpoint | Notes |
|---|---|---|
| `zenstory login [--key -] [--api-base URL]` | `GET /agent/projects` (validation) | Without `--key` it prompts `Paste API key:` with echo off (terminal only; without a terminal it exits 2 and asks for `--key -`). `--key -` reads the key from stdin. Saves `{apiKey[, apiBase]}` to `$XDG_CONFIG_HOME/zenstory/config.json` (or `~/.config/zenstory/config.json`), mode 0600, dir 0700; `apiBase` is only stored when `--api-base` was given (or was already stored). A rejected key is not saved. |
| `zenstory logout` | – | Deletes the saved config. |
| `zenstory whoami` | `GET /agent/projects`, `PUT /agent/projects/<nonexistent>` | Prints API base, masked key, `read`/`write` scope and project count. The write probe targets a project id that cannot exist, so it changes nothing (404 = write allowed). |

Environment variables override the saved config: `ZENSTORY_API_KEY`, `ZENSTORY_API_BASE`
(blank values count as unset). Safety rules:

- API bases must be `https://`; plain `http://` is accepted only for `localhost`,
  `127.0.0.1` and `[::1]`.
- A saved key is bound to the API base it was saved with (default
  `https://api.zenstory.ai/api/v1`). If `ZENSTORY_API_BASE` points elsewhere, commands
  refuse to send the saved key (exit 2) unless `ZENSTORY_API_KEY` is also set or the
  global flag `--allow-base-override` is passed. `login` likewise refuses a differing
  `ZENSTORY_API_BASE` unless `--api-base` is given explicitly.
- The CLI warns on stderr when the config file is readable by group/others.

`whoami --json`:

```json
{
  "apiBase": "https://api.zenstory.ai/api/v1",
  "apiBaseSource": "config",
  "key": "eg_1a2b…9f0e",
  "keySource": "config",
  "configPath": "/home/me/.config/zenstory/config.json",
  "scopes": { "read": true, "write": true },
  "projectCount": 3
}
```

## Projects

| Command | Endpoint | Scope |
|---|---|---|
| `zenstory projects list` | `GET /agent/projects` | read |
| `zenstory projects get <projectId>` | `GET /agent/projects/{id}` | read |
| `zenstory projects create --name <name> [--description <text>] [--type novel\|short\|screenplay]` | `POST /agent/projects` | write |
| `zenstory projects update <projectId> [--name <name>] [--description <text>]` | `PUT /agent/projects/{id}` | write |
| `zenstory projects delete <projectId> --yes` | `DELETE /agent/projects/{id}` (soft delete) | write |

Project object: `id, name, description, project_type, owner_id, created_at, updated_at`.
`name` is 1–100 chars, `description` ≤ 500. Projects created through the API have **no
default folders** (the web app creates them; the API does not).

## Files

| Command | Endpoint | Scope |
|---|---|---|
| `zenstory files list <projectId> [--type T] [--parent <folderId>] [--fields csv] [--limit 1-200] [--offset N] [--all]` | `GET /agent/projects/{id}/files` | read |
| `zenstory files tree <projectId>` | `GET /agent/projects/{id}/files` (all pages, no content) | read |
| `zenstory files get <fileId> [--fields csv] [-o path [--force]]` | `GET /agent/files/{id}` | read |
| `zenstory files create <projectId> --title <t> [--type T] [--parent <folderId>] [--content-file path \| --content text\|-] [--metadata json]` | `POST /agent/projects/{id}/files` | write |
| `zenstory files put <fileId> [--content-file path \| --content text\|-] [--title t] [--if-updated-at ts] [--allow-shrink] [--allow-empty]` | `GET` then `PUT /agent/files/{id}` | read + write |
| `zenstory files delete <fileId> --yes` | `DELETE /agent/files/{id}` (soft delete) | write |

Details:

- `--type`: `outline | draft | character | lore | snippet | script | document | folder`.
  `material` is accepted as an alias for `snippet`. Unknown types are rejected locally.
- `files list` defaults to `--fields id,title,file_type,parent_id,order,updated_at` (no
  content, cheap). Add `content` to the list to fetch bodies. Valid fields: `id,
  project_id, title, content, file_type, parent_id, order, file_metadata, created_at,
  updated_at`. `--parent` returns only direct children. Results are ordered by `order`
  ascending, then newest first, then id. JSON shape: `{ "files": [...], "total", "limit", "offset" }`.
  `--all` pages through everything (it cannot be combined with `--limit`/`--offset`) and
  drops rows repeated across pages.
- `files tree --json` returns `{ "tree": [ {id, title, file_type, parent_id, order,
  children: [...]}, ... ], "total" }`. Files whose parent is missing, or that sit in a
  parent cycle, appear at the root.
- `files get` prints the raw content (a trailing newline is added on stdout only).
  `-o path` writes the exact content to a new file with mode 0600 (temp file + rename in
  the same directory). It refuses an existing path unless `--force`, and always refuses
  symbolic links. `--json` prints the file object:
  `id, project_id, title, content, file_type, parent_id, order, file_metadata (JSON
  string or null), created_at, updated_at`.
- `files create`: `--type` defaults to `draft`; content defaults to empty. `--parent`
  must be an existing file in the same project (otherwise HTTP 400). The API does not
  check that the parent is a folder, but you should always use one: the web tree and
  chapter context assume files live in folders. `--metadata` must be a JSON
  object; it is stored as `file_metadata`. New files get `order: 0`.
- `files put` replaces the whole content (and/or title). It first GETs the current file,
  then:
  - `--if-updated-at <ts>`: refuses (exit 1, code `STALE_WRITE`) when the server's
    `updated_at` differs — the user edited the file since you read it.
  - refuses new content shorter than 50% of the current content unless `--allow-shrink`,
    and empty/whitespace content unless `--allow-empty`.
  - saves the current content to `$XDG_CACHE_HOME/zenstory/backups/<fileId>-<timestamp>.md`
    (default `~/.cache/zenstory/backups`, mode 0600) and prints the path (`backupPath` in
    `--json` output).
  The server also records a file version, so the change can be rolled back in the web
  app's version history. Metadata, parent and order cannot be changed via the API.
- `--content -` / `--content-file -` read from stdin. Content must be UTF-8 text.

## Search and writing context

| Command | Endpoint | Scope / limit |
|---|---|---|
| `zenstory search <projectId> <query...> [--limit 1-50] [--type T ...] [--content]` | `POST /agent/projects/{id}/search` | read, 500/h |
| `zenstory context <projectId> [--file <fileId>] [--query text] [--max-items 1-30]` | `GET /agent/projects/{id}/writing-context` | read, 500/h |

`search` request body: `{ "query", "top_k" (default 10), "file_types"?, "include_content"? }`.
Response:

```json
{
  "query": "玉佩的来历",
  "results": [
    { "id": "…", "title": "第三章", "file_type": "draft", "content": null,
      "score": 0.82, "snippet": "…", "line_start": 41, "fused_score": 0.03,
      "sources": ["semantic", "lexical"], "metadata": {} }
  ],
  "result_count": 1
}
```

`context` query params: `file_id`, `query`, `max_items` (default 10). Response:

```json
{
  "items": [
    { "type": "character", "title": "林远", "content_snippet": "≤500 chars…",
      "source_file_id": "…", "relevance": 0.9 }
  ],
  "refs": ["…"],
  "total_available": 12,
  "returned": 10,
  "token_estimate": 3400
}
```

The server caps the payload at ~50 KB and times out after 10 s (HTTP 504).

## Skill management

| Command | Effect |
|---|---|
| `zenstory skill install [--target claude\|codex\|openclaw\|agents\|<dir>] [--force]` | Copies this skill to `~/.claude/skills/zenstory` (claude, default), `~/.agents/skills/zenstory` (codex, agents), `~/.openclaw/skills/zenstory` (openclaw; `$OPENCLAW_STATE_DIR/skills` when set), or `<dir>/zenstory`. Refuses to overwrite without `--force`; even with `--force` it only replaces a previous install (just `SKILL.md` named `zenstory` plus `references/`). A symlink at the destination is never followed (with `--force` only the link is removed). |
| `zenstory skill path` | Prints the bundled skill directory. |

## Errors and exit codes

| Exit | Meaning | Typical cause |
|---|---|---|
| 0 | Success | |
| 1 | Other error | Network failure, 5xx (search index unavailable = 503, context timeout = 504), `--if-updated-at` conflict |
| 2 | Usage error | Missing argument, bad flag, invalid type, 400 bad request, 422 validation, delete without `--yes`, refused API base, `files put` shrink guard |
| 3 | Auth / permission | Not logged in, 401 invalid/expired key, 403 missing scope or project not allowed for this key |
| 4 | Not found | 404 project/file id (also for files in projects you do not own) |
| 5 | Rate limited | 429; limits per key per hour: read 2000, write 1000, search 500, context 500 |

With `--json`, errors are written to stderr as
`{"error": {"message", "status", "code", "exitCode"}}`; `code` is the server error code
(e.g. `ERR_FILE_NOT_FOUND`, `ERR_NOT_AUTHORIZED`).
