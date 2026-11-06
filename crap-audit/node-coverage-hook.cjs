// Preload for crap-audit's plain `node --test` path: instruments the repo's own
// source as Node loads it (files on disk untouched), then dumps Istanbul's hit
// counters when the process exits. Run as `NODE_OPTIONS=--require <this file>`.
//
// Env: CRAP_TOOLS (dir holding node_modules/istanbul-lib-instrument), CRAP_ROOT
// (repo root), CRAP_FILES (newline list of root-relative source files to
// instrument), CRAP_HITS (dir the per-process dumps go to).
//
// `esModules` follows the format Node itself resolved for the file
// (`result.format === 'module'`), never the extension: an ES module saved as
// `.js` under `"type": "module"` is a module. Guessing from `.mjs` made Babel
// throw on `.js` modules, and that repo's suite then grew to 4 GB in 8 s.
const { registerHooks } = require('node:module')
const { fileURLToPath } = require('node:url')
const path = require('node:path')
const fs = require('node:fs')
const die = (msg) => { throw new Error(`crap-audit hook: ${msg}`) }
// registerHooks needs Node 22.15+ (or 23.5+); an older Node would otherwise fail with an unrelated error.
if (typeof registerHooks !== 'function') die(`needs Node 22.15+ for module.registerHooks, running ${process.version}`)
for (const v of ['CRAP_TOOLS', 'CRAP_ROOT', 'CRAP_FILES', 'CRAP_HITS']) {
  if (!process.env[v]) die(`${v} is not set (is it passed through to this process?)`)
}
const { createInstrumenter } = require(path.join(process.env.CRAP_TOOLS, 'node_modules/istanbul-lib-instrument'))
// Node reports real paths, so compare against real paths: a relative or symlinked
// CRAP_ROOT, or a CRLF list, would otherwise match nothing and score every file 0%.
const ROOT = fs.realpathSync(process.env.CRAP_ROOT)
const listed = fs.readFileSync(process.env.CRAP_FILES, 'utf8').split(/\r?\n/).filter(Boolean)
if (listed.length === 0) die(`${process.env.CRAP_FILES} lists no source files`)
const SOURCES = new Set(listed.map(r => {
  try { return fs.realpathSync(path.resolve(ROOT, r)) } catch { return die(`listed file ${r} does not exist under ${ROOT}`) }
}))
registerHooks({
  load (url, context, nextLoad) {
    const result = nextLoad(url, context)
    if (!url.startsWith('file:')) return result
    const file = fileURLToPath(url)
    if (!SOURCES.has(file) || result.source == null) return result
    const inst = createInstrumenter({ esModules: result.format === 'module', compact: false, coverageGlobalScopeFunc: false, coverageGlobalScope: 'globalThis' })
    try {
      return { ...result, source: inst.instrumentSync(result.source.toString(), file) }
    } catch (err) {
      // Fail loud: a file left uninstrumented would score as uncovered, and a
      // swallowed error here is how a runaway suite hid its cause.
      throw new Error(`crap-audit: cannot instrument ${file}: ${err.message}`, { cause: err })
    }
  }
})
const dump = () => {
  if (!globalThis.__coverage__) return
  fs.writeFileSync(path.join(process.env.CRAP_HITS, `${process.pid}-${Date.now()}.json`), JSON.stringify(globalThis.__coverage__))
}
process.on('exit', dump)
// Dump on a signal without changing what the signal does: when ours is the only
// listener, step aside and re-raise so the default termination still happens.
for (const s of ['SIGTERM', 'SIGINT']) {
  process.on(s, function onSignal () {
    dump()
    if (process.listenerCount(s) === 1) { process.removeListener(s, onSignal); process.kill(process.pid, s) }
  })
}
