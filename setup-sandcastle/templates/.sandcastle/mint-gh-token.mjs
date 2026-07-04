#!/usr/bin/env node
// Mint a short-lived GitHub App installation token.
//
// Reads GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_APP_INSTALLATION_ID
// from the environment, signs a JWT, and exchanges it for an installation
// access token. Prints the token to stdout so callers can capture it:
//
//   export GITHUB_TOKEN=$(node .sandcastle/mint-gh-token.mjs)
//   gh api user   # → returns the bot's login, not the maintainer's
//
// See .sandcastle/bot-setup.md for one-time GitHub App creation steps.

import { createSign } from "node:crypto";
import { fileURLToPath } from "node:url";

/**
 * Build a GitHub App JWT signed with RS256.
 * @param {string} appId   GitHub App ID (numeric, as string)
 * @param {string} privateKey  PEM-encoded PKCS#1 or PKCS#8 RSA private key
 * @returns {string} Signed JWT valid ~9 minutes (under GitHub's 10-min cap, for drift)
 */
export function buildJwt(appId, privateKey) {
  // Env vars often store multiline PEMs with literal \n; expand them.
  privateKey = privateKey.replace(/\\n/g, "\n");
  const now = Math.floor(Date.now() / 1000);
  const header = Buffer.from(
    JSON.stringify({ alg: "RS256", typ: "JWT" })
  ).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({
      iat: now - 60, // 60-second past buffer for clock drift
      // GitHub caps exp at 10 min ahead of ITS clock and recommends <10 min to
      // absorb drift. A fast local clock (WSL2 runs ahead) pushes now+600 past
      // the cap → 401 "'exp' too far in the future". 540s keeps ~60s of margin.
      exp: now + 540,
      iss: String(appId),
    })
  ).toString("base64url");

  const signer = createSign("RSA-SHA256");
  signer.update(`${header}.${payload}`);
  const sig = signer.sign(privateKey, "base64url");

  return `${header}.${payload}.${sig}`;
}

/**
 * Load and validate GitHub App credentials from environment variables.
 * @returns {{ appId: string, privateKey: string, installationId: string }}
 */
export function loadCredentials() {
  const appId = process.env.GITHUB_APP_ID;
  const installationId = process.env.GITHUB_APP_INSTALLATION_ID;
  let privateKey = process.env.GITHUB_APP_PRIVATE_KEY;

  if (!appId) throw new Error("Missing required env var: GITHUB_APP_ID");
  if (!privateKey)
    throw new Error("Missing required env var: GITHUB_APP_PRIVATE_KEY");
  if (!installationId)
    throw new Error("Missing required env var: GITHUB_APP_INSTALLATION_ID");

  return { appId, privateKey, installationId };
}

/**
 * Exchange a GitHub App JWT for a short-lived installation access token.
 * @param {string} appId
 * @param {string} privateKey
 * @param {string} installationId
 * @returns {Promise<string>} Installation access token (valid ~1 hour)
 */
export async function mintInstallationToken(appId, privateKey, installationId) {
  const jwt = buildJwt(appId, privateKey);
  const res = await fetch(
    `https://api.github.com/app/installations/${installationId}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    }
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API ${res.status}: ${body}`);
  }
  const { token } = await res.json();
  return token;
}

// Run as a CLI: print the token to stdout.
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { appId, privateKey, installationId } = loadCredentials();
  mintInstallationToken(appId, privateKey, installationId)
    .then((token) => process.stdout.write(token))
    .catch((err) => {
      process.stderr.write(`Error: ${err.message}\n`);
      process.exit(1);
    });
}
