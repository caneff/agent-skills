# mechanism-audit hand run on agent-skills (#1364)

2026-11-23, run by the worker that built the audit, at commit `9c90194c`. It is a
bounded sample, not a full pass: pass one lists 1421 candidate lines on this
repo (`audit.py candidates .`), and the sample judged the ones below. The first
`all-audits` sweep is the full run.

## Sample judged

Candidates in `AGENTS.md`, `implement/codex-audit.md`, and every source comment
saying "falls back" or "if absent": `implement-spec/closure.py`, `agents.py`,
`mutation-audit/audit.py`, plus the hook wiring claims in
`implement/SKILL.md` § Control.

## Findings

| Type | Rule | Searched | Verdict |
|---|---|---|---|
| no-mechanism | `implement/codex-audit.md:10`, "Run it by hand near the end of the window" | `rg codex-audit` across the repo (docs, tests and the script itself only); `~/.claude/settings.json` (no entry); `crontab -l` (no codex entry); `~/.local/bin` (only `codex`) | A recurring weekly duty whose only carrier is a controller remembering. Nothing reminds anyone, which is how it went unrun from 2026-10-03 to the kill switch. Chris's 2026-11-22 comment on #1364 already read this as weaker than first stated (by design a hand run), so it is a real instance of the shape, not new drift. |
| carried | `implement-spec/closure.py:483`, "the caller falls back to the named files alone" | `rg ClosureError` outside the module | `closure.py:588` catches it and clumps conservatively. |
| carried | `implement/SKILL.md:184`, "The stop hook alerts the controller" | `~/.claude/settings.json` | `worker-stop-alert.sh` is wired (line 260). |
| carried | `test-audit/bootstrap.sh`, called by "the four suites" | `rg bootstrap test-audit` | Called by `assertion-free-gate.test.sh`, `audit-mjs.test.sh`, and checked by `bootstrap.test.sh`. |

## Never reached: none found in the sample

No "mechanism present, never reached" instance turned up. The sample's two
best leads were scripts nothing named (`test-audit/bootstrap.sh`, the fixture
helpers), and each was called under a different spelling. The known witness for
this type, the unwired Stop hook (#1939), is fixed, and #2014's
`settings-rules` suite now asserts every hook script is wired, so a hook
instance of it cannot recur silently. What the sample did not read is the other
1400 candidates, mostly rules in `flow/` and `implement*`; the type is not shown
absent.
