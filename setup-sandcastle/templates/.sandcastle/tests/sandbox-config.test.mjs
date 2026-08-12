import { test, expect, beforeAll, afterAll } from "vitest";
import { rmSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { hasCopier, renderPythonArm } from "./render-fixture.mjs";

// sandbox-config.mts carries the sandbox plumbing that survived the bot-identity
// deletion (#245): the read-only skills mount, the hooks-path isolation, and the
// dependency-install hook. No token minting, no bot git identity — every sandbox
// authenticates with the .env PAT Sandcastle forwards as a file.
//
// The module branches on LANGUAGE, so there is no plain `.mts` beside this file
// to import — render the Python arm once and exercise THAT, the same move
// copier-template.test.mjs makes. The Node arm's two divergent values (npm vs uv)
// are asserted as text over there, where both arms sit side by side.
const here = dirname(fileURLToPath(import.meta.url));
// tests/ -> .sandcastle/ -> templates/ -> setup-sandcastle/ -> repo root
const repoRoot = join(here, "..", "..", "..", "..");
const withRender = test.skipIf(!hasCopier());

let rendered;
let sandboxConfig;
beforeAll(async () => {
  if (!hasCopier()) return;
  rendered = renderPythonArm(repoRoot, { linkModules: true });
  ({ sandboxConfig } = await import(
    pathToFileURL(join(rendered, ".sandcastle", "sandbox-config.mts")).href
  ));
}, 60_000);
afterAll(() => rendered && rmSync(rendered, { recursive: true, force: true }));

withRender("sandboxConfig: passes the sandbox env and the read-only skills mount to dockerFn", () => {
  let captured = null;
  sandboxConfig((opts) => {
    captured = opts;
    return {};
  });
  // No bot token merged in any more — the .env PAT reaches the sandbox as a
  // forwarded file, not through this env map. The Python arm keeps only uv's var.
  expect(captured.env).toEqual({
    UV_PROJECT_ENVIRONMENT: "/home/agent/.venv",
  });
  // The host's global Claude skills are mounted read-only so the in-sandbox
  // agent has /tdd etc. — not vendored into the repo.
  expect(captured.mounts).toContainEqual({
    hostPath: "~/.claude/skills",
    sandboxPath: "~/.claude/skills",
    readonly: true,
  });
});

withRender("sandboxConfig: onSandboxReady is [disable-hooks, uv sync]", () => {
  const cfg = sandboxConfig(() => ({}));
  expect(cfg.hooks.sandbox.onSandboxReady).toEqual([
    {
      command:
        "mkdir -p /home/agent/.git-no-hooks && git config core.hooksPath /home/agent/.git-no-hooks",
    },
    { command: "uv sync" },
  ]);
});

withRender("sandboxConfig: exactly ONE onSandboxReady entry touches git config (no .git/config.lock race, #52)", () => {
  // Sandcastle runs onSandboxReady hooks concurrently, so any two git-config
  // entries race on the lock and the loser dies. With bot identity gone the only
  // git-config write is core.hooksPath — assert it stays a single entry so a
  // later addition can't quietly reintroduce the race.
  const ready = sandboxConfig(() => ({})).hooks.sandbox.onSandboxReady;
  const gitEntries = ready.filter((c) => c.command.includes("git config"));
  expect(gitEntries).toHaveLength(1);
  expect(gitEntries[0].command).toContain("core.hooksPath");
});
