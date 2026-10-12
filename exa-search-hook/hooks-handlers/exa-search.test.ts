// WebFetch goes to crawl4ai first and must end in the built-in fetch's result
// whenever crawl4ai has no markdown to give (#1543).
import { test, expect } from 'claude-code/testing'

const URL = 'https://example.com/page'
const BUILTIN = { result: 'built-in fetch result' }

// Runs one WebFetch through the mod. `crawl` is what the crawl4ai service
// answers; `builtin` records whether the call reached the engine beneath.
const fetchWith = async ($: any, on: any, crawl: () => any) => {
  on('http.fetch', () => ({ value: crawl() }))
  let builtin = 0
  on('tool.call', { tool: 'WebFetch' }, () => {
    builtin += 1
    return BUILTIN
  })
  const answer = await $.tool.call({ tool: 'WebFetch', url: URL, prompt: 'summarize' })
  return { answer, builtin }
}

test('crawl4ai markdown is returned without touching the built-in fetch', async ($, on) => {
  const { answer, builtin } = await fetchWith($, on, () => ({ ok: true, status: 200, text: JSON.stringify({ markdown: '# hi' }) }))
  expect(builtin).toBe(0)
  expect(JSON.stringify(answer)).toContain('# hi')
})

test('a non-OK crawl4ai answer ends in the built-in fetch result', async ($, on) => {
  const { answer, builtin } = await fetchWith($, on, () => ({ ok: false, status: 500, text: 'boom' }))
  expect(builtin).toBe(1)
  expect(answer).toEqual(BUILTIN)
})

test('empty markdown ends in the built-in fetch result', async ($, on) => {
  const { answer, builtin } = await fetchWith($, on, () => ({ ok: true, status: 200, text: JSON.stringify({ markdown: '' }) }))
  expect(builtin).toBe(1)
  expect(answer).toEqual(BUILTIN)
})

test('an unparseable crawl4ai body ends in the built-in fetch result', async ($, on) => {
  const { answer, builtin } = await fetchWith($, on, () => ({ ok: true, status: 200, text: '<html>not json' }))
  expect(builtin).toBe(1)
  expect(answer).toEqual(BUILTIN)
})
