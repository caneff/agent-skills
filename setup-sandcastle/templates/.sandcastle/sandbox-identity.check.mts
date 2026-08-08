// Self-check for applyBotToken — no test runner in this repo (package.json
// "test" is a stub, `just check` is Python-only), so this runs via `npx tsx`.
//   npx tsx .sandcastle/sandbox-identity.check.mts
import assert from "node:assert";
import { applyBotToken } from "./sandbox-identity.mts";

// (a) A minted bot token overwrites BOTH gh env vars so host gh()/git() use it.
{
  const env: Record<string, string | undefined> = {};
  applyBotToken({ env: { GH_TOKEN: "minted-123" }, gitConfigCommands: [] }, env);
  assert.equal(env.GH_TOKEN, "minted-123", "GH_TOKEN should be set");
  assert.equal(env.GITHUB_TOKEN, "minted-123", "GITHUB_TOKEN should be set");
}

// (b) Personal-token mode (identity carries no token): leave an existing ambient
// token untouched — never clobber the maintainer's own credentials.
{
  const env: Record<string, string | undefined> = {
    GH_TOKEN: "personal",
    GITHUB_TOKEN: "personal",
  };
  applyBotToken({ env: {}, gitConfigCommands: [] }, env);
  assert.equal(env.GH_TOKEN, "personal", "personal GH_TOKEN preserved");
  assert.equal(env.GITHUB_TOKEN, "personal", "personal GITHUB_TOKEN preserved");
}

console.log("applyBotToken checks passed");
