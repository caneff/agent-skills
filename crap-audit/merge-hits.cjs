// Merge the per-process Istanbul dumps the coverage hook wrote into one
// coverage-final.json on stdout. `node --test` runs each test file in its own
// process, so one source file appears in several dumps: statement (`s`),
// function (`f`) and branch (`b`) counters are summed, never overwritten.
// Usage: node merge-hits.cjs <hits-dir>
const fs = require('node:fs')
const path = require('node:path')
const dir = process.argv[2]
if (!dir) { console.error('usage: merge-hits.cjs <hits-dir>'); process.exit(2) }
const dumps = fs.readdirSync(dir).filter(f => f.endsWith('.json'))
// No dumps means the hook never ran; an empty merge would score every function 0%.
if (dumps.length === 0) { console.error(`merge-hits: no coverage dumps in ${dir}`); process.exit(1) }
const add = (a, b) => a.map((n, i) => n + b[i])
const out = {}
for (const f of dumps) {
  for (const [file, cov] of Object.entries(JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')))) {
    const seen = out[file]
    if (!seen) { out[file] = cov; continue }
    for (const k of Object.keys(cov.s)) seen.s[k] += cov.s[k]
    for (const k of Object.keys(cov.f)) seen.f[k] += cov.f[k]
    for (const k of Object.keys(cov.b)) seen.b[k] = add(seen.b[k], cov.b[k])
  }
}
process.stdout.write(JSON.stringify(out))
