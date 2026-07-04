# Sandcastle bot GitHub App — one-time setup

This guide creates a GitHub App that Sandcastle uses as its bot identity.
Actions (commits, PR comments, issue labels) attributed to the App render
as `sandcastle-bot[bot]` in GitHub's UI instead of your personal account.

---

## Step 1 — Create the GitHub App

1. Go to **Settings → Developer settings → GitHub Apps → New GitHub App**
   (direct link: `https://github.com/settings/apps/new`)

2. Fill in the form:
   | Field | Value |
   |---|---|
   | GitHub App name | `sandcastle-bot` (or any unique name) |
   | Homepage URL | URL of this repository |
   | Webhook | **Disable** (uncheck "Active") |

3. **Permissions** — set Repository permissions:
   | Permission | Access |
   |---|---|
   | Contents | Read & write |
   | Pull requests | Read & write |
   | Issues | Read & write |
   | Metadata | Read (required, auto-set) |

4. **Where can this GitHub App be installed?** → "Only on this account"

5. Click **Create GitHub App**.

---

## Step 2 — Generate a private key

On the App's settings page (the one you land on after creation):

1. Scroll to **Private keys** → **Generate a private key**.
2. A `.pem` file downloads automatically — keep it secret.

Note the **App ID** shown near the top of the page (a small integer like `1234567`).

---

## Step 3 — Install the App on the repository

1. In the App's settings page, click **Install App** in the left sidebar.
2. Click **Install** next to your account.
3. Choose **Only select repositories** → pick this repo → **Install**.

---

## Step 4 — Find the Installation ID

After Step 3, GitHub lands you on the installation's settings page. Its URL ends
with the Installation ID:

```
https://github.com/settings/installations/<INSTALLATION_ID>
```

That trailing number is `GITHUB_APP_INSTALLATION_ID` (e.g. `12345678`).

> The `gh api /repos/<owner>/<repo>/installation` endpoint does **not** work here —
> it requires a JWT signed by the App itself, not your personal token, so it
> returns `401 "A JSON web token could not be decoded"`. Use the URL above.

---

## Step 5 — Store the credentials

### Local development

Sandcastle reads `.sandcastle/.env` (NOT a top-level `.env`). If you don't have
one yet, copy the template, then fill in the values:

```bash
cp .sandcastle/.env.example .sandcastle/.env
# Edit .sandcastle/.env:
#   GITHUB_APP_ID=<app-id>
#   GITHUB_APP_PRIVATE_KEY="$(cat /path/to/downloaded.pem)"
#   GITHUB_APP_INSTALLATION_ID=<installation-id>
#   SANDCASTLE_BOT_GIT_NAME=sandcastle-bot
#   SANDCASTLE_BOT_GIT_EMAIL=<bot email — see Step 5b>
```

`.sandcastle/.env` is gitignored — it will not be committed.

Once the bot works, blank out the old personal `GH_TOKEN=` line in
`.sandcastle/.env` so runs can't silently fall back to your account.

### Step 5b — Bot email

The commit-author email is the bot account's no-reply address, in this exact shape:

```
<BOT_USER_ID>+<app-slug>[bot]@users.noreply.github.com
```

`<BOT_USER_ID>` is the numeric **user ID of the bot account** — NOT the App ID
(they differ, and using the App ID leaves commits unlinked: GitHub shows a
fallback avatar instead of the bot's). Fetch it once the App is installed:

```bash
gh api '/users/<app-slug>[bot]' --jq .id
# e.g. /users/sandcastle-bot[bot] → 296302627
```

Example: bot user ID `296302627`, name `sandcastle-bot` →
`296302627+sandcastle-bot[bot]@users.noreply.github.com`. Only when the prefix is
the bot's user ID does GitHub link commits to the bot's avatar.

### CI (GitHub Actions)

Add three repository secrets at **Settings → Secrets and variables → Actions**:

| Secret name                  | Value                                               |
| ---------------------------- | --------------------------------------------------- |
| `GITHUB_APP_ID`              | numeric App ID                                      |
| `GITHUB_APP_PRIVATE_KEY`     | full PEM content (multi-line is fine in GH secrets) |
| `GITHUB_APP_INSTALLATION_ID` | numeric Installation ID                             |

---

## Step 6 — Mint a token (one-liner)

With the three env vars set, mint a short-lived (~1 hour) installation token:

```bash
export GITHUB_TOKEN=$(node .sandcastle/mint-gh-token.mjs)
```

Verify the identity:

```bash
gh api user --jq '.login'
# → sandcastle-bot[bot]   (not the maintainer's login)
```

Use `$GITHUB_TOKEN` anywhere `gh` or `git` needs to authenticate as the bot.

---

## Notes

- Tokens expire in ~1 hour. Re-run the one-liner to refresh.
- The App consumes no seat and is ToS-clean (preferred over a PAT on a second account).
