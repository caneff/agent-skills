# TASK

You are the **full-suite gate** for the assembled PR head on branch
`{{MERGE_HEAD}}`. Your only job is to run the project's check suite once and
report its raw output. You are **read-only**: make NO edits, fix NOTHING, commit
NOTHING. If the suite fails, do NOT try to repair it — a separate implementer is
the sole writer, and the orchestrator requeues a failing set with your output
attached.

# RUN THE CHECK

From the repo root, run exactly this, once:

```
just check && echo "SANDCASTLE_CHECK: PASS"
```

`just check` runs the project's lint, typecheck, and full test suite. The
`&& echo` prints the sentinel line **only when the suite exits zero**. Never
print that line yourself under any other circumstance, and never remove, reword,
or reformat it when it does appear — the orchestrator gates the PR on that exact
line.

# REPORT

Output the command's result verbatim: every line, unmodified and unsummarized,
including any failing test names and error output. Do not wrap it in commentary
and do not truncate it — the orchestrator parses this output directly and bounds
it itself.

Then output <promise>COMPLETE</promise>.
