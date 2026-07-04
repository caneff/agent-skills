// @vitest-environment node
import { test, expect, describe, beforeAll } from "vitest";
import { generateKeyPairSync } from "node:crypto";
import { buildJwt, loadCredentials } from "../mint-gh-token.mjs";

let testPrivateKeyPem;

beforeAll(() => {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  testPrivateKeyPem = privateKey.export({ type: "pkcs1", format: "pem" });
});

// ── buildJwt ──────────────────────────────────────────────────────────────────

describe("buildJwt", () => {
  test("returns a 3-part dot-separated JWT string", () => {
    const jwt = buildJwt("12345", testPrivateKeyPem);
    expect(jwt.split(".")).toHaveLength(3);
  });

  test("header decodes to { alg: RS256, typ: JWT }", () => {
    const [headerB64] = buildJwt("12345", testPrivateKeyPem).split(".");
    const header = JSON.parse(Buffer.from(headerB64, "base64url").toString());
    expect(header.alg).toBe("RS256");
    expect(header.typ).toBe("JWT");
  });

  test("payload contains iss equal to the appId string", () => {
    const [, payloadB64] = buildJwt("99999", testPrivateKeyPem).split(".");
    const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString());
    expect(payload.iss).toBe("99999");
  });

  test("payload iat is in the past (clock-drift buffer)", () => {
    const [, payloadB64] = buildJwt("1", testPrivateKeyPem).split(".");
    const { iat } = JSON.parse(Buffer.from(payloadB64, "base64url").toString());
    expect(iat).toBeLessThan(Math.floor(Date.now() / 1000));
  });

  test("payload exp is at most 600s ahead of now (GitHub's hard cap)", () => {
    const before = Math.floor(Date.now() / 1000);
    const [, payloadB64] = buildJwt("1", testPrivateKeyPem).split(".");
    const { exp } = JSON.parse(Buffer.from(payloadB64, "base64url").toString());
    // 600s is GitHub's hard cap for exp. <= 600 is intentional: a second boundary
    // between before and the JWT's internal now causes exp - before == 600, which
    // is still valid. Strictly < 600 would flake on that one-second skew.
    expect(exp - before).toBeLessThanOrEqual(600);
  });

  test("normalises literal \\n sequences in the private key", () => {
    // Env vars often store multiline PEMs with literal \n; buildJwt must expand them.
    const escapedKey = testPrivateKeyPem.replace(/\n/g, "\\n");
    expect(() => buildJwt("12345", escapedKey)).not.toThrow();
    const jwt = buildJwt("12345", escapedKey);
    expect(jwt.split(".")).toHaveLength(3);
  });
});

// ── loadCredentials ───────────────────────────────────────────────────────────

describe("loadCredentials", () => {
  const VARS = {
    GITHUB_APP_ID: "42",
    GITHUB_APP_PRIVATE_KEY:
      "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
    GITHUB_APP_INSTALLATION_ID: "1001",
  };

  function withEnv(overrides, fn) {
    const saved = {};
    const all = { ...VARS, ...overrides };
    for (const [k, v] of Object.entries(all)) {
      saved[k] = process.env[k];
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    try {
      return fn();
    } finally {
      for (const [k, v] of Object.entries(saved)) {
        if (v === undefined) delete process.env[k];
        else process.env[k] = v;
      }
    }
  }

  test("returns parsed credentials when all vars are set", () => {
    const creds = withEnv({}, () => loadCredentials());
    expect(creds.appId).toBe("42");
    expect(creds.installationId).toBe("1001");
    expect(creds.privateKey).toContain("BEGIN RSA PRIVATE KEY");
  });

  test("throws with var name when GITHUB_APP_ID is missing", () => {
    expect(() =>
      withEnv({ GITHUB_APP_ID: undefined }, () => loadCredentials())
    ).toThrow(/GITHUB_APP_ID/);
  });

  test("throws with var name when GITHUB_APP_PRIVATE_KEY is missing", () => {
    expect(() =>
      withEnv({ GITHUB_APP_PRIVATE_KEY: undefined }, () => loadCredentials())
    ).toThrow(/GITHUB_APP_PRIVATE_KEY/);
  });

  test("throws with var name when GITHUB_APP_INSTALLATION_ID is missing", () => {
    expect(() =>
      withEnv({ GITHUB_APP_INSTALLATION_ID: undefined }, () =>
        loadCredentials()
      )
    ).toThrow(/GITHUB_APP_INSTALLATION_ID/);
  });
});
