// Shared plumbing for page-shot and page-eval: find Playwright wherever it
// lives on this machine, turn a bare path into a file:// URL, and open a page
// with console/page errors collected. Nothing here is Orca-specific — these
// two scripts are what replaced Orca's embedded browser (#691).
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { existsSync } from 'node:fs'

// Playwright is usually a global npm install, sometimes a repo-local one, and
// the global root differs per node version — so resolve at runtime rather than
// baking a path in at write time. PLAYWRIGHT_PACKAGE_ROOT overrides everything.
export function loadPlaywright() {
  const roots = [
    process.env.PLAYWRIGHT_PACKAGE_ROOT,
    process.cwd() + '/',
    import.meta.url,
  ].filter(Boolean)
  for (const root of roots) {
    try {
      return createRequire(root.endsWith('/') || root.startsWith('file:') ? root : root + '/')('playwright')
    } catch { /* try the next root */ }
  }
  try {
    const global = execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim()
    return createRequire(global + '/')('playwright')
  } catch (e) {
    console.error('browser.mjs: cannot find the playwright package.')
    console.error('  install it (`npm i -g playwright`) or set PLAYWRIGHT_PACKAGE_ROOT')
    console.error(`  last error: ${e.message}`)
    process.exit(3)
  }
}

// A bare path is the common case, so accept one; http(s) and file URLs pass
// through. A missing file is a usage error, not a blank screenshot.
export function toUrl(target) {
  if (/^https?:|^file:/.test(target)) return target
  if (!existsSync(target)) {
    console.error(`no such file: ${target}`)
    process.exit(2)
  }
  return 'file://' + resolve(target)
}

export const arg = argv => ({
  // --flag VALUE, repeatable
  all: name => argv.flatMap((a, i) => (a === name ? [argv[i + 1]] : [])),
  // --flag VALUE, last one wins
  one: (name, fallback) => {
    const i = argv.lastIndexOf(name)
    return i === -1 ? fallback : argv[i + 1]
  },
  has: name => argv.includes(name),
})

export async function openPage(target, { width = 1280, height = 900 } = {}) {
  const { chromium } = loadPlaywright()
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: +width, height: +height } })
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => m.type() === 'error' && errors.push(m.text()))
  const url = toUrl(target)
  let response
  try {
    response = await page.goto(url, { waitUntil: 'networkidle' })
  } catch (e) {
    await browser.close()
    console.error(e.message)
    process.exit(1)
  }
  return { browser, page, errors, response, url }
}
