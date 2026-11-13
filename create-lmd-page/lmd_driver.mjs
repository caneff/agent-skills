#!/usr/bin/env node
// Posts one puzzle to Logic Masters Deutschland through a Chrome it drives over CDP (#1659, #1661).
//
//   node lmd_driver.mjs --endpoint http://127.0.0.1:9334 --png <board.png> --template <page.html> \
//     --values <values.json> [--image-id <id>] [--base-url https://logic-masters.de] [--timeout-ms 30000]
//
// In real use Windows `node.exe` runs it against the stream browser on 9334 (WSL cannot reach a Windows
// loopback port); the caller checks the stream gate first. In one new tab it uploads the PNG on LMD's
// file page ("author created", "others may use" unchecked) and reads the new image id, fills the page
// template's {{IMAGE_ID}}, fills the English-only submit form and clicks "Create", which saves the
// puzzle inactive, then reads the new puzzle id off the saved notice's puzzle-page link. It never clicks
// "Aktivieren". It closes its tab and prints one JSON line: {"image_id", "puzzle_id", "puzzle_url", "html"}.
// --image-id names an image already on LMD (an earlier run's upload) and skips the upload; --png is still
// required and still checked.
//
// Edit mode (#1720) changes a puzzle that is already on LMD:
//
//   node lmd_driver.mjs --endpoint http://127.0.0.1:9334 --edit <puzzle-id> --template <page.html> \
//     [--values <values.json>] [--base-url ...] [--timeout-ms ...]
//
// It opens that puzzle's edit form (Raetselportal/Eigene/einstellen.php?id=<id>), replaces the English page
// HTML with the --template file's text as it stands (a literal page: no {{IMAGE_ID}} is filled, and one left in
// is refused), sets only the fields --values names and clicks "Change". Every other field, the activation
// choice and its date fields included, goes back as the form served it; it never visits the puzzle page, so
// it never activates. --values holds any of "title", "code", "difficulty", "labels", "freetags",
// "codedescr_en", checked as for a create; "slug" and "sudoku" are refused, as the edit form has neither.
// --png and --image-id are refused. It prints {"puzzle_id", "puzzle_url", "html"}. A failure after "Change"
// was clicked prints {"failed", "uploaded": false, "image_id": null, "submitted": true} on stdout as well.
// The caller re-archives the puzzle afterwards (create-lmd-page/SKILL.md § Edit a live page).
//
// values.json, every key required: {"slug", "title", "code", "difficulty" (1-5), "sudoku" ("Ja" | "Nein"),
//   "labels" ([<n> of label_<n>]), "freetags" (string), "codedescr_en" (string, may be empty)}.
//
// Any failure exits 1 with "lmd_driver: <error>" on stderr; a usage error exits 2. A failure once an image
// is on LMD also prints one JSON line on stdout, {"failed", "uploaded", "image_id", "submitted"}: what already
// reached LMD, so a rerun can see an image or puzzle no id records. "uploaded" is true once the upload was
// sent, "image_id" is null until it is read (or is --image-id's), "submitted" true once "Create" was clicked.
// Every CDP request, the
// connection to Chrome and each page load has the --timeout-ms deadline; a JavaScript dialog on the page is
// dismissed and is a failure; the tab is closed on every exit. Field names and where the ids appear:
// docs/research/2026-11-06-lmd-upload-and-submit-forms.md.
import { readFileSync, statSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";

const IMAGE_PLACEHOLDER = "{{IMAGE_ID}}";
const UPLOAD_DESCRIPTION = "author created";
const SAVED_NOTICE = "The puzzle has been saved.";
const CHANGED_NOTICE = "The puzzle has been changed.";
const PUZZLE_PAGE = "/Raetselportal/Raetsel/zeigen.php";
const MAX_UPLOAD_BYTES = 4194304; // the upload form's MAX_FILE_SIZE
// LMD strips any other character from a solution code silently (its help page and the form's hint:
// "Letters, numbers and ()<>~+-*= /\|!#$%&"). Letters are uppercased, so lowercase is kept.
const CODE_ALLOWED = /^[A-Za-z0-9()<>~+\-*= /\\|!#$%&]*$/;
const GERMAN_TEXT = ["htmlcode", "codedescr"];
const DATE_FIELDS = ["day", "month", "year", "hour", "min", "sec"];
const EDIT_KEYS = ["title", "code", "difficulty", "labels", "freetags", "codedescr_en"];
const VALUE_KEYS = ["slug", "title", "code", "difficulty", "sudoku", "labels", "freetags", "codedescr_en"];

class DriverError extends Error {}
class UsageError extends Error {}
const fail = (msg) => { throw new DriverError(msg); };

function readText(file, what) {
  try { return readFileSync(file, "utf8"); } catch (e) { fail(`cannot read the ${what} ${file}: ${e.message}`); }
}

// The checks both modes share on one values key, each refusing what LMD would silently alter or reject.
function checkValue(v, k) {
  switch (k) {
    case "slug": case "title": case "code":
      if (typeof v[k] !== "string" || !v[k].trim()) fail(`values.${k} must be a non-empty string`);
      if (k === "code" && !CODE_ALLOWED.test(v.code)) {
        const bad = [...new Set([...v.code].filter((c) => !CODE_ALLOWED.test(c)))].join("");
        fail(`the solution code ${JSON.stringify(v.code)} has characters LMD would strip: ${JSON.stringify(bad)}`);
      }
      break;
    case "codedescr_en": case "freetags":
      if (typeof v[k] !== "string") fail(`values.${k} must be a string`);
      break;
    case "difficulty":
      if (!Number.isInteger(v.difficulty) || v.difficulty < 1 || v.difficulty > 5) fail(`values.difficulty must be 1-5, got ${JSON.stringify(v.difficulty)}`);
      break;
    case "sudoku":
      if (v.sudoku !== "Ja" && v.sudoku !== "Nein") fail(`values.sudoku must be "Ja" or "Nein", got ${JSON.stringify(v.sudoku)}`);
      break;
    case "labels":
      if (!Array.isArray(v.labels) || !v.labels.every(Number.isInteger)) fail("values.labels must be a list of label numbers");
      break;
  }
}

function readValues(file) {
  let v;
  try { v = JSON.parse(readText(file, "values file")); } catch (e) { if (e instanceof DriverError) throw e; fail(`the values file ${file} is not JSON: ${e.message}`); }
  if (v === null || typeof v !== "object" || Array.isArray(v)) fail(`the values file ${file} is not a JSON object`);
  return v;
}

function readInputs(argv) {
  const { values: a } = parseArgs({
    args: argv,
    options: {
      endpoint: { type: "string" }, png: { type: "string" }, template: { type: "string" }, edit: { type: "string" },
      values: { type: "string" }, "image-id": { type: "string" }, "base-url": { type: "string", default: "https://logic-masters.de" },
      "timeout-ms": { type: "string", default: "30000" },
    },
  });
  const edit = a.edit !== undefined;
  for (const k of edit ? ["endpoint", "template"] : ["endpoint", "png", "template", "values"]) if (!a[k]) throw new UsageError(`--${k} is required`);
  // LMD's ids are digits and capital letters ("001626", "0015HL"); anything else would corrupt <img:ID>.
  if (a["image-id"] !== undefined && !/^[0-9A-Z]+$/.test(a["image-id"])) {
    throw new UsageError(`--image-id must be an LMD image id (digits and capital letters), got ${JSON.stringify(a["image-id"])}`);
  }
  if (edit) {
    if (!/^[0-9A-Z]+$/.test(a.edit)) throw new UsageError(`--edit must be an LMD puzzle id (digits and capital letters), got ${JSON.stringify(a.edit)}`);
    for (const k of ["png", "image-id"]) if (a[k] !== undefined) throw new UsageError(`--${k} does not go with --edit: edit mode uploads nothing`);
  }
  const timeoutMs = Number(a["timeout-ms"]);
  if (!(timeoutMs > 0)) throw new UsageError(`--timeout-ms must be a positive number, got ${a["timeout-ms"]}`);
  const common = { endpoint: a.endpoint.replace(/\/+$/, ""), base: a["base-url"].replace(/\/+$/, ""), timeoutMs };
  const template = readText(a.template, edit ? "page file" : "page template");
  if (edit) {
    if (template.includes(IMAGE_PLACEHOLDER)) fail(`the page file still has a ${IMAGE_PLACEHOLDER} placeholder: edit mode posts the page as it is`);
    const v = a.values === undefined ? {} : readValues(a.values);
    // The edit form has no Sudoku question, and a slug names an upload: a key it would ignore is refused.
    for (const k of Object.keys(v)) if (!EDIT_KEYS.includes(k)) fail(`values.${k} does not apply to an edit (it takes ${EDIT_KEYS.join(", ")})`);
    for (const k of Object.keys(v)) checkValue(v, k);
    return { ...common, edit: a.edit, template, form: v };
  }
  const png = path.resolve(a.png);
  let size;
  try { size = statSync(png).size; } catch (e) { fail(`cannot read the PNG ${png}: ${e.message}`); }
  if (size > MAX_UPLOAD_BYTES) fail(`the PNG is ${size} bytes, over LMD's upload limit of ${MAX_UPLOAD_BYTES}`);
  if (!template.includes(IMAGE_PLACEHOLDER)) fail(`the page template has no ${IMAGE_PLACEHOLDER} placeholder`);
  const v = readValues(a.values);
  // A missing key is refused, never defaulted: each value is one the user confirmed.
  for (const k of VALUE_KEYS) if (!Object.hasOwn(v, k)) fail(`the values file has no "${k}"`);
  for (const k of VALUE_KEYS) checkValue(v, k);
  return { ...common, png, template, imageId: a["image-id"] ?? null, form: Object.fromEntries(VALUE_KEYS.map((k) => [k, v[k]])) };
}

// One HTTP call to Chrome's CDP endpoint, with the deadline; the body is read inside it too.
async function cdpHttp(endpoint, url, timeoutMs, init = {}) {
  try {
    const r = await fetch(url, { ...init, signal: AbortSignal.timeout(timeoutMs) });
    return { ok: r.ok, status: r.status, body: await r.text() };
  } catch (e) {
    if (e.name === "TimeoutError") fail(`CDP ${url} did not answer within ${timeoutMs} ms`);
    fail(`no CDP endpoint at ${endpoint}: ${e.cause?.message ?? e.message}`);
  }
}

// Opens a new tab, runs `run` on it and closes it, whatever happened.
async function withTab(endpoint, timeoutMs, run) {
  const created = await cdpHttp(endpoint, `${endpoint}/json/new?about:blank`, timeoutMs, { method: "PUT" });
  if (!created.ok) fail(`CDP ${endpoint}/json/new answered ${created.status} ${created.body}`);
  let tab;
  try { tab = JSON.parse(created.body); } catch { fail(`CDP ${endpoint}/json/new answered with a body that is not JSON: ${created.body.slice(0, 300)}`); }
  try {
    if (typeof tab?.webSocketDebuggerUrl !== "string") fail(`CDP ${endpoint}/json/new answered with no webSocketDebuggerUrl: ${created.body.slice(0, 300)}`);
    return await withSession(tab.webSocketDebuggerUrl, timeoutMs, run);
  } finally {
    if (tab?.id) {
      await cdpHttp(endpoint, `${endpoint}/json/close/${tab.id}`, timeoutMs)
        .catch((e) => process.stderr.write(`lmd_driver: could not close tab ${tab.id}: ${e.message}\n`));
    }
  }
}

// One CDP session on a tab's websocket, hand-rolled on Node's global WebSocket like twitch-rules-scroller's
// e2e client (e2e/chrome-windows.mjs withCdp): no dependency. Every wait has a deadline, and every wait ends
// at once when the session ends: the socket closed, or the page opened a dialog.
async function withSession(url, timeoutMs, run) {
  let ws;
  try { ws = new WebSocket(url); } catch (e) { fail(`CDP gave a websocket URL that cannot be opened, ${url}: ${e.message}`); }
  const pending = new Map();
  const listeners = new Set();
  let nextId = 0;
  let endSession;
  const ended = new Promise((_, rej) => { endSession = rej; });
  ended.catch(() => {});
  // Waits for `start` to settle its promise, for at most timeoutMs; `start` returns its own cleanup.
  const bounded = (start, late) => {
    let timer, cleanup;
    return Promise.race([
      new Promise((res, rej) => {
        timer = setTimeout(() => rej(new DriverError(late)), timeoutMs);
        cleanup = start(res, rej);
      }),
      ended,
    ]).finally(() => { clearTimeout(timer); cleanup?.(); });
  };
  const send = (method, params = {}) => bounded((res, rej) => {
    const id = ++nextId;
    pending.set(id, { res, rej, method });
    ws.send(JSON.stringify({ id, method, params }));
    return () => pending.delete(id);
  }, `CDP ${method} got no answer within ${timeoutMs} ms`);
  const waitFor = (method, what) => bounded((res) => {
    const listener = (msg) => { if (msg.method === method) res(msg.params); };
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, `${what} did not finish loading within ${timeoutMs} ms`);
  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.method === "Page.javascriptDialogOpening") {
      // A dialog blocks the page's script, so no evaluate would answer: dismiss it and stop.
      ws.send(JSON.stringify({ id: ++nextId, method: "Page.handleJavaScriptDialog", params: { accept: false } }));
      const { type, message, url: at } = msg.params;
      endSession(new DriverError(`the page opened a ${type} dialog, dismissed unanswered, at ${at}: ${JSON.stringify(message)}`));
      return;
    }
    if (msg.id === undefined) { for (const l of listeners) l(msg); return; }
    const p = pending.get(msg.id);
    if (!p) return;
    if (msg.error) p.rej(new DriverError(`CDP ${p.method}: ${msg.error.message}`));
    else p.res(msg.result);
  };
  ws.onclose = () => endSession(new DriverError(`the CDP socket at ${url} closed`));
  const evaluate = async (expression) => {
    const { result, exceptionDetails } = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (exceptionDetails) fail(`the page threw: ${exceptionDetails.exception?.description ?? exceptionDetails.text}`);
    return result?.value;
  };
  const navigate = async (to) => {
    const loaded = waitFor("Page.loadEventFired", to);
    const { errorText } = await send("Page.navigate", { url: to });
    if (errorText) fail(`cannot open ${to}: ${errorText}`);
    await loaded;
  };
  // Runs `expression`, which submits a form, and waits for the page it leads to.
  const submit = async (expression, what) => {
    const loaded = waitFor("Page.loadEventFired", what);
    await evaluate(expression);
    await loaded;
  };
  try {
    await bounded((res, rej) => {
      ws.onopen = res;
      ws.onerror = () => rej(new DriverError(`CDP websocket unreachable at ${url}`));
    }, `the CDP websocket at ${url} did not open within ${timeoutMs} ms`);
    await send("Page.enable");
    return await run({ send, evaluate, navigate, submit });
  } finally {
    ws.close();
  }
}

// What the page says, for an error report: its URL and its visible text.
const pageReport = async (tab) => {
  const { url, text } = await tab.evaluate("({ url: location.href, text: (document.body?.innerText ?? '').replace(/\\s+/g, ' ').trim().slice(0, 4000) })");
  return `${url}: ${text}`;
};

// Refuses a page without `selector`; a login form there means the browser is logged out.
async function requirePage(tab, selector, what) {
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
  await requirePage(tab, "input[name=datei]", "upload form");
  // An id already listed under this name is an earlier upload's: the new one must be an id not seen here.
  const before = new Set(await uploadRows(tab, name));
  const { result } = await tab.send("Runtime.evaluate", { expression: "document.querySelector('input[name=datei]')" });
  await tab.send("DOM.setFileInputFiles", { files: [png], objectId: result.objectId });
  // From the submit on, an image may be on LMD whatever happens next.
  posted.uploaded = true;
  await tab.submit(`(() => {
    const form = document.querySelector('input[name=datei]').form;
    form.elements.name.value = ${JSON.stringify(name)};
    form.elements.anmerkung.value = ${JSON.stringify(UPLOAD_DESCRIPTION)};
    form.elements.offen.checked = false;
    form.querySelector('[name=dateiupload]').click();
  })()`, "the image upload");
  // The id is read from a fresh copy of the list; the POST's answer is kept for the error report, as it
  // carries LMD's reason for a refused upload. Right after an upload LMD serves /Dateien/ with the file list
  // and no upload form (#1659's closing check), so the reload needs the list, not the form.
  const answer = await pageReport(tab);
  await tab.navigate(page);
  await requirePage(tab, "table.upload_list_gross", "upload list");
  const [newest] = await uploadRows(tab, name);
  if (!newest || before.has(newest)) fail(`no new image named ${JSON.stringify(name)} on the upload page after the upload; LMD answered the upload with ${answer}`);
  return newest;
}

async function submitPuzzle(tab, base, form, html) {
  await tab.navigate(`${base}/Raetselportal/Eigene/einstellen.php`);
  await requirePage(tab, "input[name=einstellen]", "puzzle submit form");
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
  posted.submitted = true;
  await tab.submit("document.querySelector('input[name=einstellen]').click()", "the puzzle submit");
  // Live LMD answers "Create" on einstellen.php itself: "The puzzle has been saved. Edit Puzzle <id> To the
  // puzzle page", with the form shown again, emptied (#1659's closing check). The id is read from the
  // "To the puzzle page" link (the site menu's own zeigen.php link has no id); a page without the notice, or
  // without exactly one such id, is a refusal.
  const { saved, ids } = await tab.evaluate(`({
    saved: (document.body?.innerText ?? '').includes(${JSON.stringify(SAVED_NOTICE)}),
    ids: [...new Set([...document.querySelectorAll('a[href]')].map((a) => new URL(a.href))
      .filter((u) => u.pathname.endsWith(${JSON.stringify(PUZZLE_PAGE)}) && u.searchParams.get('id'))
      .map((u) => u.searchParams.get('id')))],
  })`);
  const [id] = ids;
  if (!saved || ids.length !== 1 || !/^[0-9A-Z]+$/.test(id ?? "")) fail(`no puzzle id after "Create": ${await pageReport(tab)}`);
  return { id, url: `${base}${PUZZLE_PAGE}?id=${id}` };
}

// Edit mode: the puzzle's edit form, its page HTML replaced and the fields `form` names set; the rest is
// submitted as served, activation included (research note, "Edit form").
async function editPuzzle(tab, base, id, form, html) {
  await tab.navigate(`${base}/Raetselportal/Eigene/einstellen.php?id=${encodeURIComponent(id)}`);
  await requirePage(tab, "input[name=einstellen]", "puzzle edit form");
  const problem = await tab.evaluate(`(() => {
    const v = ${JSON.stringify({ form, html })};
    const f = document.querySelector('input[name=einstellen]').form;
    const el = (name) => f.elements[name] ?? (() => { throw new Error('the edit form has no field ' + name); })();
    el('htmlcode_en').value = v.html;
    if ('title' in v.form) el('name').value = v.form.title;
    if ('code' in v.form) el('code').value = v.form.code;
    if ('codedescr_en' in v.form) el('codedescr_en').value = v.form.codedescr_en;
    if ('freetags' in v.form) el('freetags').value = v.form.freetags;
    if ('difficulty' in v.form) {
      if (![...el('dif').options].some((o) => o.value === String(v.form.difficulty))) return 'the edit form has no difficulty ' + v.form.difficulty;
      el('dif').value = String(v.form.difficulty);
    }
    if ('labels' in v.form) {
      const boxes = [...f.querySelectorAll('input[type=checkbox][name^=label_]')];
      const unknown = v.form.labels.filter((n) => !boxes.some((b) => b.name === 'label_' + n));
      if (unknown.length) return 'the edit form has no label ' + unknown.join(', ');
      for (const b of boxes) b.checked = v.form.labels.includes(Number(b.name.slice(6)));
    }
    if (!f.checkValidity()) return 'the edit form is not valid: ' + [...f.elements].filter((e) => !e.validity.valid).map((e) => e.name).join(', ');
    return null;
  })()`);
  if (problem) fail(problem);
  posted.submitted = true;
  await tab.submit("document.querySelector('input[name=einstellen]').click()", "the puzzle edit");
  // Live LMD answers on the edit page: "The puzzle has been changed. Edit Puzzle <id> To the puzzle page".
  // Anything else, or a link to another puzzle, is a refusal.
  const { changed, ids } = await tab.evaluate(`({
    changed: (document.body?.innerText ?? '').includes(${JSON.stringify(CHANGED_NOTICE)}),
    ids: [...new Set([...document.querySelectorAll('a[href]')].map((a) => new URL(a.href))
      .filter((u) => u.pathname.endsWith(${JSON.stringify(PUZZLE_PAGE)}) && u.searchParams.get('id'))
      .map((u) => u.searchParams.get('id')))],
  })`);
  if (!changed || ids.length !== 1 || ids[0] !== id) fail(`no "changed" notice for puzzle ${id} after "Change": ${await pageReport(tab)}`);
  return `${base}${PUZZLE_PAGE}?id=${id}`;
}

// What reached LMD so far, printed on a failure after the upload.
const posted = { uploaded: false, image_id: null, submitted: false };

async function main() {
  const inputs = readInputs(process.argv.slice(2));
  if (inputs.edit !== undefined) {
    const url = await withTab(inputs.endpoint, inputs.timeoutMs, (tab) => editPuzzle(tab, inputs.base, inputs.edit, inputs.form, inputs.template));
    return JSON.stringify({ puzzle_id: inputs.edit, puzzle_url: url, html: inputs.template }) + "\n";
  }
  const out = await withTab(inputs.endpoint, inputs.timeoutMs, async (tab) => {
    const imageId = posted.image_id = inputs.imageId ?? await uploadImage(tab, inputs.base, inputs.png, inputs.form.slug);
    const html = inputs.template.replaceAll(IMAGE_PLACEHOLDER, imageId);
    const puzzle = await submitPuzzle(tab, inputs.base, inputs.form, html);
    return { image_id: imageId, puzzle_id: puzzle.id, puzzle_url: puzzle.url, html };
  });
  return JSON.stringify(out) + "\n";
}

// Exits once the line is written: a socket whose peer never acknowledges the close must not hold the process.
const finish = (stream, text, code) => stream.write(text, () => process.exit(code));
main().then((line) => finish(process.stdout, line, 0), (e) => {
  if (e instanceof UsageError) return finish(process.stderr, `lmd_driver: ${e.message}\n`, 2);
  const message = e instanceof DriverError ? e.message : e.stack;
  const report = () => finish(process.stderr, `lmd_driver: ${message}\n`, 1);
  if (!posted.uploaded && !posted.image_id && !posted.submitted) return report();
  process.stdout.write(JSON.stringify({ failed: message, ...posted }) + "\n", report);
});
