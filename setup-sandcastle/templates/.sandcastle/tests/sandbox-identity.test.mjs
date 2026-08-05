import { test, expect, beforeEach, afterEach } from "vitest";

// The module is imported once; sandboxIdentity() reads process.env at call time,
// so manipulating process.env between tests is enough to exercise both branches.

const botVars = [
  "SANDCASTLE_BOT_GH_TOKEN",
  "SANDCASTLE_BOT_GIT_NAME",
  "SANDCASTLE_BOT_GIT_EMAIL",
];

const appVars = [
  "GITHUB_APP_ID",
  "GITHUB_APP_PRIVATE_KEY",
  "GITHUB_APP_INSTALLATION_ID",
];

let savedEnv;
beforeEach(() => {
  savedEnv = {};
  for (const v of [...botVars, ...appVars]) {
    savedEnv[v] = process.env[v];
    delete process.env[v];
  }
});
afterEach(() => {
  for (const v of [...botVars, ...appVars]) {
    if (savedEnv[v] === undefined) delete process.env[v];
    else process.env[v] = savedEnv[v];
  }
});

// Import once; the helper reads process.env at call time, not at module load.
const { sandboxIdentity, sandboxConfig } =
  await import("../sandbox-identity.mts");

// ── sandboxConfig ─────────────────────────────────────────────────────────────

test("sandboxConfig: calls dockerFn with identity.env and the read-only skills mount", () => {
  const identity = { env: { GH_TOKEN: "tok" }, gitConfigCommands: [] };
  let captured = null;
  sandboxConfig(identity, (opts) => {
    captured = opts;
    return {};
  });
  expect(captured.env).toEqual({
    GH_TOKEN: "tok",
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

test("sandboxConfig: gitConfigCommands fold into the chained git entry, before uv sync", () => {
  const identity = {
    env: {},
    gitConfigCommands: [{ command: "git config user.name Bot" }],
  };
  const cfg = sandboxConfig(identity, () => ({}));
  const ready = cfg.hooks.sandbox.onSandboxReady;
  // The identity write is chained into the single git-config entry (not its own
  // entry — that would race the lock, #52), which still runs before uv sync.
  const gitIdx = ready.findIndex((c) => c.command.includes("git config"));
  const uvIdx = ready.findIndex((c) => c.command === "uv sync");
  expect(ready[gitIdx].command).toContain("git config user.name Bot");
  expect(gitIdx).toBeLessThan(uvIdx);
});

test("sandboxConfig: onSandboxReady is [disable-hooks, uv sync] when no gitConfigCommands", () => {
  const identity = { env: {}, gitConfigCommands: [] };
  const cfg = sandboxConfig(identity, () => ({}));
  expect(cfg.hooks.sandbox.onSandboxReady).toEqual([
    {
      command:
        "mkdir -p /home/agent/.git-no-hooks && git config core.hooksPath /home/agent/.git-no-hooks",
    },
    { command: "uv sync" },
  ]);
});

test("sandboxConfig: ALL git-config writes chain into ONE onSandboxReady entry (no .git/config.lock race, #52)", () => {
  // Identity writes and the core.hooksPath write hit the same .git/config.lock;
  // Sandcastle runs onSandboxReady hooks concurrently, so any two git-config
  // entries race and the loser dies. Exactly one entry may touch `git config`.
  const identity = {
    env: {},
    gitConfigCommands: [
      { command: 'git config user.name "Bot" && git config user.email "b@x"' },
    ],
  };
  const ready = sandboxConfig(identity, () => ({})).hooks.sandbox
    .onSandboxReady;
  const gitEntries = ready.filter((c) => c.command.includes("git config"));
  expect(gitEntries).toHaveLength(1);
  // That one entry carries both the identity writes and the hooks-path write.
  expect(gitEntries[0].command).toContain("user.name");
  expect(gitEntries[0].command).toContain("core.hooksPath");
});

// ── no-op branch: bot vars unset ─────────────────────────────────────────────

test("sandbox-identity: no-op when bot vars unset — env and gitConfigCommands are empty", async () => {
  const id = await sandboxIdentity();
  expect(id.env).toEqual({});
  expect(id.gitConfigCommands).toEqual([]);
});

// ── identity branch: all bot vars set ────────────────────────────────────────

test("sandbox-identity: env and gitConfigCommands are fully populated when all bot vars set", async () => {
  process.env.SANDCASTLE_BOT_GH_TOKEN = "ghp_test_token";
  process.env.SANDCASTLE_BOT_GIT_NAME = "Sandcastle Bot";
  process.env.SANDCASTLE_BOT_GIT_EMAIL = "bot@example.com";

  const id = await sandboxIdentity();
  expect(id.env.GH_TOKEN).toBe("ghp_test_token");
  const cmd = id.gitConfigCommands.map((c) => c.command).join(" && ");
  expect(cmd).toMatch(/user\.name/);
  expect(cmd).toMatch(/user\.email/);
  expect(cmd).toContain("Sandcastle Bot");
  expect(cmd).toContain("bot@example.com");
});

test("sandbox-identity: name+email collapse into ONE chained command (no .git/config.lock race)", async () => {
  process.env.SANDCASTLE_BOT_GH_TOKEN = "ghp_test_token";
  process.env.SANDCASTLE_BOT_GIT_NAME = "Sandcastle Bot";
  process.env.SANDCASTLE_BOT_GIT_EMAIL = "bot@example.com";

  const id = await sandboxIdentity();
  // Sandcastle runs hooks concurrently; two git config writes would race on
  // the config lock. Exactly one hook entry, chaining both writes sequentially.
  expect(id.gitConfigCommands).toHaveLength(1);
  expect(id.gitConfigCommands[0].command).toMatch(
    /user\.name.*&&.*user\.email/
  );
});

// ── App creds branch: installation token minting ─────────────────────────────

const fakeTokenMinter = async () => "ghs_minted_token";

test("sandbox-identity: mints installation token when App creds set and SANDCASTLE_BOT_GH_TOKEN unset", async () => {
  process.env.GITHUB_APP_ID = "42";
  process.env.GITHUB_APP_PRIVATE_KEY = "fake-key";
  process.env.GITHUB_APP_INSTALLATION_ID = "1001";

  const id = await sandboxIdentity(fakeTokenMinter);
  expect(id.env.GH_TOKEN).toBe("ghs_minted_token");
});

test("sandbox-identity: SANDCASTLE_BOT_GH_TOKEN takes priority over App creds", async () => {
  process.env.SANDCASTLE_BOT_GH_TOKEN = "ghp_direct_token";
  process.env.GITHUB_APP_ID = "42";
  process.env.GITHUB_APP_PRIVATE_KEY = "fake-key";
  process.env.GITHUB_APP_INSTALLATION_ID = "1001";

  const minter = async () => "ghs_should_not_be_used";
  const id = await sandboxIdentity(minter);
  expect(id.env.GH_TOKEN).toBe("ghp_direct_token");
});

test("sandbox-identity: no-op when App creds partially set (missing installationId)", async () => {
  process.env.GITHUB_APP_ID = "42";
  process.env.GITHUB_APP_PRIVATE_KEY = "fake-key";
  // GITHUB_APP_INSTALLATION_ID intentionally unset

  const id = await sandboxIdentity(fakeTokenMinter);
  expect(id.env).toEqual({});
});

test("sandbox-identity: tokenMinter called with appId, privateKey, installationId from env", async () => {
  process.env.GITHUB_APP_ID = "99";
  process.env.GITHUB_APP_PRIVATE_KEY = "pem-data";
  process.env.GITHUB_APP_INSTALLATION_ID = "777";

  let captured = null;
  const capturingMinter = async (appId, privateKey, installationId) => {
    captured = { appId, privateKey, installationId };
    return "ghs_token";
  };

  await sandboxIdentity(capturingMinter);
  expect(captured.appId).toBe("99");
  expect(captured.installationId).toBe("777");
  expect(captured.privateKey).toBeTruthy();
});

test("sandbox-identity: no-op when App creds not set and SANDCASTLE_BOT_GH_TOKEN unset", async () => {
  // All vars cleared by beforeEach
  const id = await sandboxIdentity(fakeTokenMinter);
  expect(id.env).toEqual({});
  expect(id.gitConfigCommands).toEqual([]);
});
