// One-off read of LMD's upload and submit forms in the stream browser (#1660).
// Opens one new tab, navigates, reads, closes the tab. Submits nothing.
import { writeFileSync } from "node:fs";
import path from "node:path";

const base = "http://127.0.0.1:9334";
const outDir = process.argv[2];
const pages = {
  upload: "https://logic-masters.de/Dateien/",
  submit: "https://logic-masters.de/Raetselportal/Eigene/einstellen.php",
};

const tab = await (await fetch(`${base}/json/new?about:blank`, { method: "PUT" })).json();
const ws = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((ok, bad) => { ws.onopen = ok; ws.onerror = bad; });
let next = 1;
const waiting = new Map();
const events = [];
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data);
  if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); }
  else events.push(msg);
};
const send = (method, params = {}) => new Promise((ok) => {
  const id = next++; waiting.set(id, ok); ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails));
  return r.result.result.value;
};

const formsJs = `JSON.stringify([...document.forms].map(f => ({
  action: f.getAttribute('action'), method: f.method, enctype: f.enctype,
  fields: [...f.elements].map(e => {
    const lab = e.labels && e.labels[0] ? e.labels[0].innerText.trim()
      : (e.closest('tr') ? e.closest('tr').innerText.trim().slice(0, 120) : '');
    const o = { tag: e.tagName.toLowerCase(), type: e.type, name: e.name, id: e.id, label: lab, required: e.required };
    if (e.type === 'checkbox' || e.type === 'radio') { o.value = e.value; o.checked = e.checked; }
    if (e.type === 'submit') o.value = e.value;
    if (e.tagName === 'SELECT') o.options = [...e.options].map(x => [x.value, x.text.trim()]);
    return o;
  })
})), null, 2)`;

try {
  await send("Page.enable");
  for (const [key, url] of Object.entries(pages)) {
    events.length = 0;
    await send("Page.navigate", { url });
    for (let i = 0; i < 100 && !events.some((e) => e.method === "Page.loadEventFired"); i++) {
      await new Promise((r) => setTimeout(r, 100));
    }
    const html = await evaluate("document.documentElement.outerHTML");
    const forms = await evaluate(formsJs);
    const title = await evaluate("document.title");
    const loggedOut = await evaluate("!!document.querySelector('input[name=pwd]')");
    writeFileSync(path.join(outDir, `${key}.html`), html);
    writeFileSync(path.join(outDir, `${key}.forms.json`), forms);
    console.log(`${key}: title=${JSON.stringify(title)} loggedOut=${loggedOut} html=${html.length} forms=${JSON.parse(forms).length}`);
  }
} finally {
  ws.close();
  await fetch(`${base}/json/close/${tab.id}`);
  console.log(`closed tab ${tab.id}`);
}
