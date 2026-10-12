// WebFetch goes to crawl4ai first and, when crawl4ai has no markdown to give,
// hands the call to the built-in fetch with `next(e)` instead of throwing (#1543).
//
// The handler is called directly rather than through the engine: the engine
// already skips a hook that throws and runs the built-in fetch, so an engine
// level test passes for the throwing handler too (it only logs the notice
// "tool.call hook skipped: threw HooksError: crawl4ai 500"). Whether the
// handler itself threw is what these tests pin.
import { test, expect } from 'claude-code/testing'
import { register } from './exa-search'

const URL = 'https://example.com/page'
const EVENT = { url: URL, prompt: 'summarize' }
const NEXT_RESULT = { result: 'built-in fetch result' }

// The WebFetch handler `register` installs, picked out by its tool filter.
const webFetchHandler = (): any => {
  const handlers: Record<string, any> = {}
  ;(register as any)((_event: string, filter: any, fn: any) => { handlers[filter.tool] = fn }, {})
  return handlers.WebFetch
}

// Runs the handler against a crawl4ai stand-in. `crawl` returns the fetch
// answer or throws. Returns what the handler returned and the events `next`
// received; a thrown handler rejects, which fails the test.
const run = async (crawl: () => any) => {
  const nexted: any[] = []
  const $ = { http: { fetch: async () => crawl() } }
  const answer = await webFetchHandler()($, EVENT, async (e: any) => { nexted.push(e); return NEXT_RESULT })
  return { answer, nexted }
}

test('crawl4ai markdown is returned without calling next', async () => {
  const { answer, nexted } = await run(() => ({ ok: true, status: 200, text: JSON.stringify({ markdown: '# hi' }) }))
  expect(nexted.length).toBe(0)
  expect(answer.result.result).toContain('# hi')
})

test('a non-OK crawl4ai answer calls next(e) and returns its result', async () => {
  const { answer, nexted } = await run(() => ({ ok: false, status: 500, text: 'boom' }))
  expect(nexted).toEqual([EVENT])
  expect(answer).toEqual(NEXT_RESULT)
})

test('empty markdown calls next(e) and returns its result', async () => {
  const { answer, nexted } = await run(() => ({ ok: true, status: 200, text: JSON.stringify({ markdown: '' }) }))
  expect(nexted).toEqual([EVENT])
  expect(answer).toEqual(NEXT_RESULT)
})

test('an unparseable crawl4ai body calls next(e) and returns its result', async () => {
  const { answer, nexted } = await run(() => ({ ok: true, status: 200, text: '<html>not json' }))
  expect(nexted).toEqual([EVENT])
  expect(answer).toEqual(NEXT_RESULT)
})

test('an unreachable crawl4ai service calls next(e) and returns its result', async () => {
  const { answer, nexted } = await run(() => { throw new Error('ECONNREFUSED') })
  expect(nexted).toEqual([EVENT])
  expect(answer).toEqual(NEXT_RESULT)
})
