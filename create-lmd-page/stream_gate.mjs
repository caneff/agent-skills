#!/usr/bin/env node
// Stream gate for create-lmd-page (#1662): exit 0 only when OBS is neither streaming nor recording.
//
//   node stream_gate.mjs      (WSL node, from any directory)
//
// Reads OBS through twitch-rules-scroller's own obs-websocket client (OBS_URL / OBS_PASSWORD, else its
// obs-password.txt). An unreachable websocket means OBS is not running, which is idle. Every other
// failure (wrong password, a status that is not a boolean) is a refusal, never "not live".
// Prints one line; exit 1 refuses, with the reason on stderr.
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

export async function gate(withObs, outputStatus) {
  let status;
  try {
    status = await withObs((request) => outputStatus(request));
  } catch (err) {
    if (err?.unreachable === true) return { ok: true, line: "OBS is not running: idle" };
    return { ok: false, line: `cannot read OBS output status: ${err?.message ?? err}` };
  }
  if (status.streaming) return { ok: false, line: "OBS is streaming" };
  if (status.recording) return { ok: false, line: "OBS is recording" };
  return { ok: true, line: "OBS is neither streaming nor recording" };
}

async function main() {
  const root = path.join(os.homedir(), "src", "twitch-rules-scroller");
  const load = (f) => import(pathToFileURL(path.join(root, f)).href);
  const [{ withObs }, { outputStatus }] = await Promise.all([load("process-obs.mjs"), load("obs-client.mjs")]);
  const r = await gate(withObs, outputStatus);
  (r.ok ? console.log : console.error)(r.ok ? r.line : `stream gate: ${r.line}`);
  process.exit(r.ok ? 0 : 1);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((e) => { console.error(`stream gate: ${e.message}`); process.exit(1); });
}
