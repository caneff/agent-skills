#!/usr/bin/env node
// Posts one puzzle to Logic Masters Deutschland through a Chrome it drives over CDP (#1659, #1661).
//
//   node lmd_driver.mjs --endpoint http://127.0.0.1:9334 --png <board.png> --template <page.html> \
//     --values <values.json> [--base-url https://logic-masters.de] [--timeout-ms 30000]
//
// In real use Windows `node.exe` runs it against the stream browser on 9334 (WSL cannot reach a Windows
// loopback port); the caller checks the stream gate first. In one new tab it uploads the PNG on LMD's
// file page ("author created", "others may use" unchecked) and reads the new image id, fills the page
// template's {{IMAGE_ID}}, fills the English-only submit form and clicks "Create", which saves the
// puzzle inactive, then reads the new puzzle id. It never clicks "Aktivieren". It closes its tab and
// prints one JSON line: {"image_id", "puzzle_id", "puzzle_url", "html"}.
//
// values.json: {"slug", "title", "code", "difficulty" (1-5), "sudoku" ("Ja" | "Nein", default "Ja"),
//   "labels" ([<n> of label_<n>]), "freetags" (string), "codedescr_en"}.
//
// Any failure exits 1 with "lmd_driver: <error>" on stderr; a usage error exits 2. Field names and where
// the ids appear: docs/research/2026-11-06-lmd-upload-and-submit-forms.md.
import { readFileSync, statSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";

const IMAGE_PLACEHOLDER = "{{IMAGE_ID}}";
const UPLOAD_DESCRIPTION = "author created";
const MAX_UPLOAD_BYTES = 4194304; // the upload form's MAX_FILE_SIZE
// LMD strips any other character from a solution code silently (its help page and the form's hint:
// "Letters, numbers and ()<>~+-*= /\|!#$%&"). Letters are uppercased, so lowercase is kept.
const CODE_ALLOWED = /^[A-Za-z0-9()<>~+\-*= /\\|!#$%&]*$/;
const GERMAN_TEXT = ["htmlcode", "codedescr"];
const DATE_FIELDS = ["day", "month", "year", "hour", "min", "sec"];

class DriverError extends Error {}
const fail = (msg) => { throw new DriverError(msg); };

function readInputs(argv) {
  const { values: a } = parseArgs({
    args: argv,
    options: {
      endpoint: { type: "string" }, png: { type: "string" }, template: { type: "string" },
      values: { type: "string" }, "base-url": { type: "string", default: "https://logic-masters.de" },
      "timeout-ms": { type: "string", default: "30000" },
    },
  });
  for (const k of ["endpoint", "png", "template", "values"]) if (!a[k]) throw new UsageError(`--${k} is required`);
  const timeoutMs = Number(a["timeout-ms"]);
  if (!(timeoutMs > 0)) throw new UsageError(`--timeout-ms must be a positive number, got ${a["timeout-ms"]}`);
  const png = path.resolve(a.png);
  let size;
  try { size = statSync(png).size; } catch (e) { fail(`cannot read the PNG ${png}: ${e.message}`); }
  if (size > MAX_UPLOAD_BYTES) fail(`the PNG is ${size} bytes, over LMD's upload limit of ${MAX_UPLOAD_BYTES}`);
  const template = readFileSync(a.template, "utf8");
  if (!template.includes(IMAGE_PLACEHOLDER)) fail(`the page template has no ${IMAGE_PLACEHOLDER} placeholder`);
  const v = JSON.parse(readFileSync(a.values, "utf8"));
  for (const k of ["slug", "title", "code", "codedescr_en"]) {
    if (typeof v[k] !== "string" || (k !== "codedescr_en" && !v[k].trim())) fail(`values.${k} must be a non-empty string`);
  }
  if (!CODE_ALLOWED.test(v.code)) {
    const bad = [...new Set([...v.code].filter((c) => !CODE_ALLOWED.test(c)))].join("");
    fail(`the solution code ${JSON.stringify(v.code)} has characters LMD would strip: ${JSON.stringify(bad)}`);
  }
  if (!Number.isInteger(v.difficulty) || v.difficulty < 1 || v.difficulty > 5) fail(`values.difficulty must be 1-5, got ${JSON.stringify(v.difficulty)}`);
  const sudoku = v.sudoku ?? "Ja";
  if (sudoku !== "Ja" && sudoku !== "Nein") fail(`values.sudoku must be "Ja" or "Nein", got ${JSON.stringify(sudoku)}`);
  const labels = v.labels ?? [];
  if (!Array.isArray(labels) || !labels.every(Number.isInteger)) fail("values.labels must be a list of label numbers");
  const freetags = v.freetags ?? "";
  if (typeof freetags !== "string") fail("values.freetags must be a string");
  return {
    endpoint: a.endpoint.replace(/\/+$/, ""), base: a["base-url"].replace(/\/+$/, ""), timeoutMs, png, template,
    form: { slug: v.slug, title: v.title, code: v.code, difficulty: v.difficulty, sudoku, labels, freetags, codedescr_en: v.codedescr_en },
  };
}
class UsageError extends Error {}

// One CDP session on a tab's websocket, hand-rolled on Node's global WebSocket like twitch-rules-scroller's
// e2e client (e2e/chrome-windows.mjs withCdp): no dependency. Every wait has a deadline.
async function withTab(endpoint, timeoutMs, run) {
  let tab;
  try {
    const r = await fetch(`${endpoint}/json/new?about:blank`, { method: "PUT" });
    if (!r.ok) fail(`CDP ${endpoint}/json/new answered ${r.status} ${await r.text()}`);
    tab = await r.json();
  } catch (e) {
    if (e instanceof DriverError) throw e;
    fail(`no CDP endpoint at ${endpoint}: ${e.cause?.message ?? e.message}`);
  }
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  const pending = new Map();
  const listeners = new Set();
  let nextId = 0;
  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.id === undefined) { for (const l of listeners) l(msg); return; }
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    if (msg.error) p.rej(new DriverError(`CDP ${p.method}: ${msg.error.message}`));
    else p.res(msg.result);
  };
  ws.onclose = () => {
    for (const p of pending.values()) p.rej(new DriverError(`the CDP socket closed during ${p.method}`));
    pending.clear();
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const id = ++nextId;
    pending.set(id, { res, rej, method });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const waitFor = (method, what) => {
    let done;
    const promise = new Promise((res, rej) => {
      const timer = setTimeout(() => { listeners.delete(done); rej(new DriverError(`${what} did not finish loading within ${timeoutMs} ms`)); }, timeoutMs);
      done = (msg) => { if (msg.method === method) { clearTimeout(timer); listeners.delete(done); res(msg.params); } };
      listeners.add(done);
    });
    return promise;
  };
  const evaluate = async (expression) => {
    const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (exceptionDetails) fail(`the page threw: ${exceptionDetails.exception?.description ?? exceptionDetails.text}`);
    return result?.value;
  };
  const navigate = async (url) => {
    const loaded = waitFor("Page.loadEventFired", url);
    const { errorText } = await send("Page.navigate", { url });
    if (errorText) fail(`cannot open ${url}: ${errorText}`);
    await loaded;
  };
  // Runs `expression`, which submits a form, and waits for the page it leads to.
  const submit = async (expression, what) => {
    const loaded = waitFor("Page.loadEventFired", what);
    await evaluate(expression);
    await loaded;
  };
  try {
    await new Promise((res, rej) => {
      ws.onopen = res;
      ws.onerror = () => rej(new DriverError(`CDP websocket unreachable at ${tab.webSocketDebuggerUrl}`));
    });
    await send("Page.enable");
    return await run({ send, evaluate, navigate, submit });
  } finally {
    ws.close();
    await fetch(`${endpoint}/json/close/${tab.id}`).catch(() => {});
  }
}

// What the page says, for an error report: its URL and its visible text.
const pageReport = async (tab) => {
  const { url, text } = await tab.evaluate("({ url: location.href, text: (document.body?.innerText ?? '').replace(/\\s+/g, ' ').trim().slice(0, 4000) })");
  return `${url}: ${text}`;
};

// Refuses a page that is not the expected form; a login form there means the browser is logged out.
async function requireForm(tab, selector, what) {
  const { hasForm, login } = await tab.evaluate(
    `({ hasForm: !!document.querySelector(${JSON.stringify(selector)}), login: !!document.querySelector('input[name=pwd]') })`);
  if (hasForm) return;
  if (login) fail(`LMD shows a login page instead of the ${what}: the browser is not logged in (${await tab.evaluate("location.href")})`);
  fail(`the ${what} is not on the page: ${await pageReport(tab)}`);
}

const uploadRows = (tab, name) => tab.evaluate(`[...document.querySelectorAll('table.upload_list_gross tr')]
  .map((tr) => ({ name: tr.querySelector('span.upload_list_gross_name')?.textContent.trim(),
                  id: (tr.querySelector('span.upload_list_gross_id')?.textContent.match(/ID:\\s*(\\S+)/) ?? [])[1] }))
  .filter((r) => r.name === ${JSON.stringify(name)}).map((r) => r.id ?? null)`);

async function uploadImage(tab, base, png, name) {
  const page = `${base}/Dateien/`;
  await tab.navigate(page);
  await requireForm(tab, "input[name=datei]", "upload form");
  // An id already listed under this name is an earlier upload's: the new one must be an id not seen here.
  const before = new Set(await uploadRows(tab, name));
  const { result } = await tab.send("Runtime.evaluate", { expression: "document.querySelector('input[name=datei]')" });
  await tab.send("DOM.setFileInputFiles", { files: [png], objectId: result.objectId });
  await tab.submit(`(() => {
    const form = document.querySelector('input[name=datei]').form;
    form.elements.name.value = ${JSON.stringify(name)};
    form.elements.anmerkung.value = ${JSON.stringify(UPLOAD_DESCRIPTION)};
    form.elements.offen.checked = false;
    form.querySelector('[name=dateiupload]').click();
  })()`, "the image upload");
  // The page the POST answers with is not yet seen live, so the id is read from a fresh copy of the list.
  await tab.navigate(page);
  await requireForm(tab, "input[name=datei]", "upload page");
  const [newest] = await uploadRows(tab, name);
  if (!newest || before.has(newest)) fail(`no new image named ${JSON.stringify(name)} on the upload page after the upload`);
  return newest;
}

async function submitPuzzle(tab, base, form, html) {
  await tab.navigate(`${base}/Raetselportal/Eigene/einstellen.php`);
  await requireForm(tab, "input[name=einstellen]", "puzzle submit form");
  const problem = await tab.evaluate(`(() => {
    const v = ${JSON.stringify({ ...form, html, GERMAN_TEXT, DATE_FIELDS })};
    const f = document.querySelector('input[name=einstellen]').form;
    const el = (name) => f.elements[name] ?? (() => { throw new Error('the submit form has no field ' + name); })();
    const radio = [...f.querySelectorAll('input[name=Sudoku_JaNein]')].find((r) => r.value === v.sudoku);
    if (!radio) return 'the submit form has no Sudoku_JaNein choice ' + v.sudoku;
    radio.checked = true;
    el('name').value = v.title;
    for (const n of v.GERMAN_TEXT) el(n).value = '';
    el('htmlcode_en').value = v.html;
    el('codedescr_en').value = v.codedescr_en;
    el('code').value = v.code;
    if (![...el('dif').options].some((o) => o.value === String(v.difficulty))) return 'the submit form has no difficulty ' + v.difficulty;
    el('dif').value = String(v.difficulty);
    el('frei').value = 'nein';
    for (const n of v.DATE_FIELDS) el(n).value = '';
    const boxes = [...f.querySelectorAll('input[type=checkbox][name^=label_]')];
    const unknown = v.labels.filter((n) => !boxes.some((b) => b.name === 'label_' + n));
    if (unknown.length) return 'the submit form has no label ' + unknown.join(', ');
    for (const b of boxes) b.checked = v.labels.includes(Number(b.name.slice(6)));
    el('freetags').value = v.freetags;
    if (!f.checkValidity()) return 'the submit form is not valid: ' + [...f.elements].filter((e) => !e.validity.valid).map((e) => e.name).join(', ');
    return null;
  })()`);
  if (problem) fail(problem);
  await tab.submit("document.querySelector('input[name=einstellen]').click()", "the puzzle submit");
  // "Create" lands on the new puzzle's page, zeigen.php?id=<id>; any other page is a refusal.
  const url = await tab.evaluate("location.href");
  const id = new URL(url).pathname.endsWith("/zeigen.php") ? new URL(url).searchParams.get("id") : null;
  if (!id) fail(`no puzzle id after "Create": ${await pageReport(tab)}`);
  return { id, url };
}

async function main() {
  const inputs = readInputs(process.argv.slice(2));
  const out = await withTab(inputs.endpoint, inputs.timeoutMs, async (tab) => {
    const imageId = await uploadImage(tab, inputs.base, inputs.png, inputs.form.slug);
    const html = inputs.template.replaceAll(IMAGE_PLACEHOLDER, imageId);
    const puzzle = await submitPuzzle(tab, inputs.base, inputs.form, html);
    return { image_id: imageId, puzzle_id: puzzle.id, puzzle_url: puzzle.url, html };
  });
  process.stdout.write(JSON.stringify(out) + "\n");
}

main().catch((e) => {
  if (e instanceof UsageError) { process.stderr.write(`lmd_driver: ${e.message}\n`); process.exit(2); }
  process.stderr.write(`lmd_driver: ${e instanceof DriverError ? e.message : e.stack}\n`);
  process.exit(1);
});
