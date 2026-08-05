/**
 * Sandbox identity helper — gated, no-op by default.
 *
 * Returns the GH_TOKEN env and git user config commands that identify Sandcastle
 * as a bot in sandboxes. When the bot env vars are unset (the default), both
 * fields are empty and every sandbox attributes commits/PRs/comments to the
 * maintainer exactly as before.
 *
 * Token resolution order (first match wins):
 *   1. SANDCASTLE_BOT_GH_TOKEN — direct token, no minting needed
 *   2. GITHUB_APP_{ID,PRIVATE_KEY,INSTALLATION_ID} — mint an installation token
 *   3. Neither set — empty env, no-op
 *
 * Bot git config env vars (independent of token source):
 *   SANDCASTLE_BOT_GIT_NAME  — git user.name for commits made in-sandbox
 *   SANDCASTLE_BOT_GIT_EMAIL — git user.email for commits made in-sandbox
 *
 * Wire-up in main.mts:
 *   sandcastle.run({ ...sandboxConfig(identity), ... })
 */

import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { mintInstallationToken } from "./mint-gh-token.mjs";

export interface SandboxIdentity {
  /** Environment variables to merge into docker({ env }). Empty when bot vars unset. */
  env: Record<string, string>;
  /** Commands to prepend to sandbox.onSandboxReady for git identity. Empty when bot vars unset. */
  gitConfigCommands: Array<{ command: string }>;
}

type TokenMinter = (
  appId: string,
  privateKey: string,
  installationId: string
) => Promise<string>;

export async function sandboxIdentity(
  tokenMinter: TokenMinter = mintInstallationToken
): Promise<SandboxIdentity> {
  const name = process.env.SANDCASTLE_BOT_GIT_NAME;
  const email = process.env.SANDCASTLE_BOT_GIT_EMAIL;

  let resolvedToken = process.env.SANDCASTLE_BOT_GH_TOKEN;

  if (!resolvedToken) {
    const appId = process.env.GITHUB_APP_ID;
    const privateKey = process.env.GITHUB_APP_PRIVATE_KEY;
    const installationId = process.env.GITHUB_APP_INSTALLATION_ID;

    if (appId && privateKey && installationId) {
      resolvedToken = await tokenMinter(appId, privateKey, installationId);
    }
  }

  const env: Record<string, string> = resolvedToken
    ? { GH_TOKEN: resolvedToken }
    : {};
  // Sandcastle runs onSandboxReady hooks with unbounded concurrency, and each
  // `git config` write takes an exclusive .git/config.lock. Two separate hook
  // entries race and the loser dies with "could not lock config file: File
  // exists". Chain both writes into ONE hook so they run sequentially.
  const cfgs: string[] = [];
  if (name) cfgs.push(`git config user.name ${JSON.stringify(name)}`);
  if (email) cfgs.push(`git config user.email ${JSON.stringify(email)}`);
  const gitConfigCommands: Array<{ command: string }> = cfgs.length
    ? [{ command: cfgs.join(" && ") }]
    : [];
  return { env, gitConfigCommands };
}

/**
 * Returns the sandbox and hooks config that bakes identity into every sandbox
 * creation site. Spread the result into sandcastle.run() or createSandbox():
 *   sandcastle.run({ ...sandboxConfig(identity), name: "...", ... })
 *
 * The per-issue site adds its own host.onWorktreeReady on top:
 *   const cfg = sandboxConfig(identity);
 *   createSandbox({ ...cfg, hooks: { ...cfg.hooks, host: { ... } }, ... })
 */
export function sandboxConfig(
  identity: SandboxIdentity,
  dockerFn: typeof docker = docker
) {
  return {
    sandbox: dockerFn({
      env: { ...identity.env, UV_PROJECT_ENVIRONMENT: "/home/agent/.venv" },
      // Mount the host's global Claude skills read-only so the in-sandbox
      // `claude` agent has the same skills you do (e.g. /tdd, referenced by
      // implement-prompt.md). Not vendored into the repo — always live/current.
      mounts: [
        {
          hostPath: "~/.claude/skills",
          sandboxPath: "~/.claude/skills",
          readonly: true,
        },
      ],
    }),
    hooks: {
      sandbox: {
        onSandboxReady: [
          ...identity.gitConfigCommands,
          { command: "uv sync" },
        ],
      },
    },
  };
}
