# Google Sheets CLIs: adopt, wrap, or build `gsheet`

Research date: 2026-10-09. Written for #1335. Question: which existing CLI can
sit behind one allow rule and cover four jobs on a Google Sheet: (1) read a
range, (2) apply a write plan (a batch of cell writes), (3) add a tab,
(4) snapshot values, notes and comments to a file that diffs against the
previous snapshot. Today each sheet change gets a one-off scratch script.

Nothing below was installed or run. Every capability cell is read from the
tool's own docs or source, not from a live call.

## Headline

- **The brief's premise is out of date as of 2026-09-30.** Comments used to
  be reachable only through the Drive API. The Sheets API v4 now reads
  comment threads (replies, author, status) with cell anchors on
  `spreadsheets.get` when `commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED` is
  set. Google marks this Generally Available on 2026-09-30, after a
  2026-07-23 developer preview of the write side
  ([Google Sheets API release notes, Google, page updated 2026-09-03 but
  carrying the 2026-09-30 entry](https://developers.google.com/workspace/sheets/release-notes);
  [Manage comments, Google Sheets API guide, Google, updated 2026-09-30](https://developers.google.com/workspace/sheets/api/guides/comments)).
  A single `spreadsheets.get` call can therefore return values, notes and
  cell-anchored comments together.
- No tool has a snapshot verb that writes a diff-stable file. That is the
  gap that decides the question (see Recommendation).
- Two tools reach all four jobs through one binary: **`gog`** (openclaw/gogcli,
  which has named verbs for each job and released 2026-10-01) and **`gws`**
  (googleworkspace/cli, a raw Discovery passthrough whose last release was
  2026-03-31).

## Notes and comments: which API exposes what

| Thing | API and field | Source |
|---|---|---|
| Cell note | Sheets API v4 `CellData.note` ("Any note on the cell."), returned by `spreadsheets.get` with grid data | [Cells, Sheets API reference, Google, updated 2026-06-16](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells) |
| Comment threads, Drive route | Drive API v3 `comments.list`: "Required: The `fields` parameter must be set." Scopes: `drive`, `drive.file`, `drive.meet.readonly`, `drive.readonly`. At most 100 per page | [Method: comments.list, Drive API reference, Google, updated 2026-07-07](https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/list) |
| Drive comment anchors on a Sheet | Opaque: "the `anchor` field contains editor-specific internal anchor data (such as a `workbook-range` JSON string on Sheets files). The Drive API treats this data as opaque and can't resolve … cell coordinates". Resolve happens only by posting a reply with `action`. `resolved` is read-only | [Manage comments and replies, Drive API guide, Google, updated 2026-09-10](https://developers.google.com/workspace/drive/api/guides/manage-comments) |
| Comment threads, Sheets route (new) | `spreadsheets.get?commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED` returns a top-level `comments[]` of `CommentThread` (`commentId`, `anchorId`, `headPost`, `replies`, `status`, `plainTextQuote`), plus `sheets[].commentAnchors[]` that map `anchorId` to a `GridRange`. Writes go through `spreadsheets.batchUpdate` (`insertComment`, `addCommentReply`, …), whose response carries a `commentUpdateState` field for partial failures | [Manage comments, Sheets API guide, Google, updated 2026-09-30](https://developers.google.com/workspace/sheets/api/guides/comments); the live Discovery document `https://sheets.googleapis.com/$discovery/rest?version=v4` (revision `20261005`, fetched 2026-10-09) lists `commentsViewMode` on `spreadsheets.get` and the `CommentThread` and `CommentAnchor` schemas |

Comments filtered by `ranges` leave out unanchored threads. Leaving the get
unfiltered returns all of them (same Sheets guide).

## Scopes

| Call | Accepted scopes | Source |
|---|---|---|
| `spreadsheets.values.batchUpdate` (write plan) | `drive`, `drive.file`, `spreadsheets` | [Method: spreadsheets.values.batchUpdate, Google, updated 2026-06-16](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate) |
| `spreadsheets.batchUpdate` (addSheet, notes, comments) | `drive`, `drive.file`, `spreadsheets` | Discovery doc rev `20261005` (above) |
| `spreadsheets.get` / `values.get` (read, snapshot) | also `drive.readonly` and `spreadsheets.readonly` | Discovery doc rev `20261005` |
| Drive `comments.list` | `drive`, `drive.file`, `drive.readonly`, `drive.meet.readonly` | comments.list page (above) |

The minimum write path is `spreadsheets`. Reaching comments through Drive
adds a Drive scope. The Sheets route needs no Drive scope according to the
discovery scope list, but `COMMENTS_VIEW_MODE_INCLUDED` "will return a 403
error if the user does not have permission to view comments" (the enum
description in the discovery doc).

## Candidates enumerated

Release dates come from the GitHub releases API
(`gh api repos/<r>/releases`) unless a registry is named. Each release page
is `https://github.com/<r>/releases/tag/<tag>`.

| Tool | Repo / docs | Last release (where read) | Auth | Kind | Read depth |
|---|---|---|---|---|---|
| **gog** (gogcli) | https://github.com/openclaw/gogcli (`steipete/gogcli` redirects here) | v0.43.0, 2026-10-01T03:52Z (GitHub releases; CHANGELOG dates it 2026-09-30) | Desktop OAuth client, direct access token, ADC, Workspace service account (README "Accounts and authentication") | CLI, Go, curated verbs plus `gog api call` Discovery fallback | README, the command reference pages, `internal/cmd/comment_ops.go`, CHANGELOG head, `go.mod` |
| **gws** | https://github.com/googleworkspace/cli | v0.22.5, 2026-03-31T18:53Z (GitHub releases; npm `@googleworkspace/cli` time also 2026-03-31). `main` was still being pushed on 2026-10-06 | OAuth (`gws auth login`, `gws auth setup` needs gcloud), service-account or exported credentials file, pre-minted token such as `gcloud auth print-access-token` (README "Authentication") | CLI, Rust, built at runtime from Google Discovery | README, `CONTEXT.md` |
| gws-cli (andmarios) | https://pypi.org/project/gws-cli/ → https://github.com/andmarios/google-workspace-skill | 1.5.0, 2026-08-07 (PyPI JSON) | OAuth desktop client (PyPI description) | CLI, Python | PyPI description, `SKILL.md`, `reference/sheets.md` |
| sheets-cli | https://github.com/gmickel/sheets-cli | v1.0.2, 2026-02-11 | OAuth desktop client (README) | CLI, TS/Bun | README |
| google-sheet-cli | https://github.com/jroehl/google-sheet-cli | v3.0.0, 2026-09-09 (GitHub; npm `time.modified` matches) | Service account only (README) | CLI, Node/oclif | README, `docs/{data,worksheet,spreadsheet}.md` |
| gsheet-cli | https://github.com/shakydata/gsheet-cli (was dipankar/gsheet-cli) | **no releases or tags**; last push 2026-04-01; 1 star | OAuth or service account (README) | CLI, Rust, with an MCP mode | README |
| gdrive | https://github.com/glotlabs/gdrive | 3.9.1, 2024-02-01; last push 2024-08-03 | OAuth client (README) | Drive file CLI, no Sheets API | README |
| rclone (drive backend) | https://rclone.org/drive/ | v1.75.2, 2026-10-09 | OAuth or service account | File sync. Exports a Sheet as xlsx/csv/ods/tsv (`--drive-export-formats`, default `docx,xlsx,pptx,svg`). No range read/write | rclone "Google Drive" docs page |
| clasp | https://github.com/google/clasp | clasp-v3.4.1, 2026-08-28 | OAuth (`clasp login`); service accounts listed as "EXPERIMENTAL/NOT WORKING" (README) | Apps Script project CLI (`push`, `pull`, `run-function`). It would mean writing Apps Script, which is the scratch-script problem again | README section headings |
| gspread | https://github.com/burnash/gspread | v6.2.1, 2025-05-14 (GitHub; PyPI upload same day) | service account, OAuth, API key (PyPI description) | **Library, not a CLI** | PyPI description (search snippet) |
| xing5/mcp-google-sheets | https://github.com/xing5/mcp-google-sheets | v0.6.3, 2026-05-14 | service account (recommended), OAuth, ADC (README) | **MCP server, not a CLI** | README tool list |
| taylorwilsdon/google_workspace_mcp | https://github.com/taylorwilsdon/google_workspace_mcp | v2.1.0, 2026-10-09 | not read | **MCP server, not a CLI** | metadata only, plus issue #788 in a search snippet (its Sheets comments go through Drive and cannot anchor to a cell) |
| Google Sheets MCP (`sheetsmcp.googleapis.com`) | https://developers.google.com/workspace/sheets/api/reference/mcp | remote service; comments support added 2026-10-01 (release notes) | user OAuth | **Remote MCP, not a CLI** | release notes; tool list from a search snippet only |
| gcloud | — | — | ADC | Has no Sheets command group that I know of. Its only role here is minting a token for gws or gog | not opened |
| Composio Sheets toolkit | https://composio.dev/toolkits/googlesheets | — | hosted OAuth | **hosted MCP/REST**, third-party custody of tokens | search snippet only |

## Capability matrix

Legend: **Y** covered · **P** partial (what is missing) · **N** not covered.

| Tool | 1 Read range | 2 Write plan (batch) | 3 Add tab | 4a Snapshot values | 4b Notes | 4c Comments |
|---|---|---|---|---|---|---|
| **gog** | Y `gog sheets get <id> <range> [--render FORMULA\|…] --json` | Y `gog sheets batch-update <id> --data-json @plan.json` (one `values.batchUpdate`; `--dry-run`, `--input RAW\|USER_ENTERED`). Also `sheets batch-request` for raw structural arrays (CHANGELOG 0.42.0) | Y `gog sheets add-tab <id> <name> [--index]` | P `gog sheets raw <id> --include-grid-data [--sheet] --json` dumps `spreadsheets.get` "lossless", but it is raw API JSON and not a flat per-cell file | Y `gog sheets notes <id> <range>`; also in `raw --include-grid-data`; write with `sheets update-note` | P `gog drive comments list <id> --all --json` requests `comments(id,author,content,createdTime,modifiedTime,resolved,replies)` (`comment_ops.go` L18) through **Drive**, so anchors are opaque. No `commentsViewMode` found in its source (GitHub code search, 2026-10-09). `gog api call sheets v4 …` could reach the Sheets route but was not verified |
| **gws** | Y `gws sheets spreadsheets values get --params '{"spreadsheetId","range"}'` or the `+read` helper | Y `gws sheets spreadsheets values batchUpdate --json @…` (Discovery method; `--dry-run`) | Y `gws sheets spreadsheets batchUpdate` with an `addSheet` request (Discovery method) | P `gws sheets spreadsheets get` with `includeGridData`, `--fields` mask; raw JSON | Y via the same get (`sheets.data.rowData.values.note`) | P/Y Discovery is fetched at runtime and cached 24h (README "Architecture"), so `commentsViewMode` should be reachable **today** in the same get, cell-anchored. Not run. Drive route `gws drive comments list` also exists |
| gws-cli (andmarios) | Y `sheets read`, `sheets batch-get` | P `sheets write` takes one range per call; no batch write found in `reference/sheets.md` | Y `sheets add-sheet` | P `sheets read` | N no note command found in `reference/sheets.md` | P Drive comments (PyPI table: "comments, replies") |
| sheets-cli (gmickel) | Y `read range` | Y `batch --ops '<json>'` (append, updateRow, updateKey, setRange) with `--dry-run` | N no tab command in README "Commands" | P `read table` JSON | N | N |
| google-sheet-cli (jroehl) | Y `data:get` (`--csv`) | P `data:update` writes one range per call | Y `worksheet:add` | P `data:get --csv` | N | N |
| gsheet-cli (shakydata) | Y `range get` | P `range set` writes one range | Y `sheet create` | P `-o json\|csv` | N not in README | N not in README |
| rclone | N | N | N | P whole-file export only (xlsx keeps notes; csv is a single sheet, which I did not verify) | N | N |
| gdrive, clasp, gspread, gcloud | N as a ready CLI | N | N | N | N | N |
| MCP servers (xing5, Google's) | Y | Y `batch_update_cells` / `update_values` | Y `create_sheet` / `addSheet` | P | N (xing5 README) / P via `get_spreadsheet` grid data | Google's server: Y since 2026-10-01. Not a CLI, so it cannot sit behind a Bash allow rule |

Sources for each row: gog command pages under
https://github.com/openclaw/gogcli/tree/main/docs/commands
(`gog-sheets-get.md`, `gog-sheets-batch-update.md`, `gog-sheets-add-tab.md`,
`gog-sheets-raw.md`, `gog-sheets-notes.md`, `gog-sheets-update-note.md`,
`gog-drive-comments-list.md`, `gog-api-call.md`, each marked "Generated from
`gog schema --json`") and
https://github.com/openclaw/gogcli/blob/main/internal/cmd/comment_ops.go.
gws: https://github.com/googleworkspace/cli/blob/main/README.md
("Google Sheets — Shell Escaping", "Helper Commands", "Architecture") and
https://github.com/googleworkspace/cli/blob/main/CONTEXT.md (`--fields`,
`--dry-run`). andmarios:
https://github.com/andmarios/google-workspace-skill/blob/main/reference/sheets.md.
gmickel: https://github.com/gmickel/sheets-cli/blob/main/README.md. jroehl:
https://github.com/jroehl/google-sheet-cli/blob/master/docs/data.md and
`docs/worksheet.md`. shakydata:
https://github.com/shakydata/gsheet-cli/blob/main/README.md. xing5:
https://github.com/xing5/mcp-google-sheets/blob/main/README.md.

## Diff-friendly output

| Tool | Output | Stable ordering? |
|---|---|---|
| gog | `--json` (compact; `raw --pretty`), `--plain` = "stable, parseable text … (TSV)" (flag help on every command page); `--results-only`, `--select` | Row/column order follows the API. The order of Drive comments is not documented by Google (comments.list page) |
| gws | "All output … is structured JSON" (README "Architecture"); `--page-all` gives NDJSON | same as the API |
| others | JSON (gmickel, andmarios), CSV (jroehl, shakydata) | values only |

None of them produce a per-cell flat record such as
`Sheet!A1 \t value \t note \t comment-thread-ids`, sorted, which is what a
line diff needs. Raw `spreadsheets.get` JSON nests rows positionally, so an
inserted row shows up as a diff on every row below it.

## Allow-rule angle

- Claude Code Bash allow rules match on command prefixes such as
  `Bash(job-run:*)` (this repo's
  [permission-rule precedence note](2026-10-04-permission-rule-precedence.md),
  read 2026-10-04 from https://code.claude.com/docs/en/permissions). So "one
  allow rule" means one prefix.
- **gog**: `Bash(gog sheets:*)` covers jobs 1–3 and the values-and-notes half
  of 4. Comments need a second prefix, `gog drive comments list`, or `gog api
  call`. Never allow `gog api call` as a bare prefix: it reaches any
  Discovery API and any method, writes included. gog also enforces its own
  allowlist inside the binary (`--enable-commands-exact sheets.get,…`,
  `--readonly`) and documents build-time "Safety Profiles" with the policy
  baked in (README "Automate safely").
- **gws**: `Bash(gws sheets:*)` covers all four jobs if the Sheets-route
  comments get works. That prefix also admits `spreadsheets create` and
  every other Sheets method. gws has no allowlist inside the binary
  (README, none found).
- **Wrapper**: a `gsheet` script with fixed verbs (`read`, `apply`,
  `add-tab`, `snapshot`) gives one tight prefix, `Bash(gsheet:*)`, and keeps
  the broad underlying binary off the allow list.

## Recommendation

**Wrap one tool: put a thin `gsheet` wrapper over `gog`, and do not build a
new client.** The deciding gap is **job 4: no tool writes a diff-stable
snapshot of values, notes and cell-anchored comments.** Every tool returns
raw API JSON at best, and the tools with curated verbs fetch comments through
Drive, whose Sheets anchors are opaque. Jobs 1–3 are solved verbs in `gog`
(`get`, `batch-update --data-json @plan`, `add-tab`), each with `--dry-run`.
The snapshot is one `spreadsheets.get` with `includeGridData` plus
`commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED`, flattened and sorted by
(sheet, row, col). That fits in a small script, reached through `gog api
call` or `gws sheets spreadsheets get`.

Why gog over gws: gog has the steadier release cadence (v0.39.1 to v0.43.0
between 2026-09-05 and 2026-10-01), named Sheets verbs, notes read and write,
and an allowlist inside the binary. gws has not released since 2026-03-31 and
says "Expect breaking changes as we march toward v1.0" (README). gws's one
advantage is that its runtime Discovery reaches the new comments field with
no code change. If the `gog api call` path to `commentsViewMode` fails,
switch the snapshot verb alone to gws, or call the REST endpoint with a
token from `gog auth`. Building a whole `gsheet` client does not pay: it
would re-implement OAuth and keyring storage that both tools already ship.

Proposed shape (not built): `gsheet read|apply|add-tab|snapshot`. The first
three pass through to `gog sheets`. `snapshot` writes sorted TSV or JSONL,
one record per non-empty cell (value, formula, note) and one per comment post
(thread id, anchor A1, author, time, status, content). Needed scope:
`spreadsheets` for writes; read-only would be `spreadsheets.readonly`.

## Not verified

- No tool was installed or run. In particular, that `gog api call sheets v4
  spreadsheets.get --params '{"commentsViewMode":…}'` and `gws sheets
  spreadsheets get` actually return `comments[]` today is inferred from
  their docs (gog: Discovery fallback; gws: runtime Discovery) and from the
  live Discovery doc. Neither was observed.
- gog's absence of `commentsViewMode` rests on one GitHub code search
  (2026-10-09); the index can lag. The vendored `google.golang.org/api
  v0.300.0` may or may not carry the new fields.
- Whether `spreadsheets.readonly` alone is enough to read comments on the
  Sheets route. The discovery scope list says yes, but the comments guide
  does not list scopes.
- Order of Drive `comments.list` results, and of `comments[]` on the Sheets
  route: not documented on the pages read.
- rclone CSV export covering only the first sheet: not confirmed on the
  rclone page.
- gws `+read` flags, gws-cli (andmarios) Drive comment field set,
  taylorwilsdon/google_workspace_mcp capabilities, and the Google Sheets
  MCP tool list: read from search snippets or metadata only, not opened in
  full.
- gcloud has no Sheets command group: from memory, reference index not
  opened.
- Chris's existing scratch scripts and auth setup (service account vs.
  OAuth) were not inspected. The choice between gog's ADC and OAuth depends
  on them.

## Coverage of this search

- **Enumerated and opened** (README or command pages or source): gog, gws,
  gws-cli (andmarios), sheets-cli (gmickel), google-sheet-cli (jroehl),
  gsheet-cli (shakydata), gdrive (glotlabs), clasp (README headings),
  rclone drive docs, xing5/mcp-google-sheets README; Google pages: Cells
  reference, values.batchUpdate, Drive comments.list, Drive manage-comments
  guide, Sheets manage-comments guide, Sheets release notes, Sheets Discovery
  doc rev 20261005.
- **Metadata or search snippet only**: gspread (PyPI), taylorwilsdon MCP
  (GitHub API), Google Sheets MCP reference, Composio, and one result
  (`a6b8/get-sheet`) that returned 404 from the GitHub API.
- **Searches run**: two web searches for Sheets CLIs on GitHub and PyPI, one
  for Sheets MCP servers with notes or comments. Registry searches were
  **not** run on npm (beyond the named packages), crates.io, or Go
  pkg.go.dev, so a Sheets CLI that lives only on those registries could be
  missing. GitHub code search was rate-limited partway through, so notes and
  comments support for jroehl and shakydata rests on their READMEs, not
  their source.
