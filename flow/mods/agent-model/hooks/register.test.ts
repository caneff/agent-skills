// Cases ported from flow/claude/hooks/require-agent-model.test.sh (deleted in
// the same change). One case per old case; Explore without a usable model is
// now a rewrite to sonnet, not a deny. Mapping in the PR body.
import { test, expect, mock } from 'claude-code/testing'

const AGENTS = '/home/test/.claude/agents'

// Runs one Agent call through the mod and returns what reached the engine
// beneath it (`seen`, undefined if the call was denied) and the answer.
const call = async ($: any, on: any, input: Record<string, unknown>, files: Record<string, string> = {}) => {
  mock.env(on, { HOME: '/home/test' })
  on('fs.read', ($$: any, e: any) => {
    // A relative path reaches the hook resolved against the working directory.
    // An exact key wins, so `/home/test/.claude/agents/x.md` is never taken
    // for the project-relative `.claude/agents/x.md` it ends with.
    const keys = Object.keys(files)
    const key = keys.find(k => e.path === k) ??
      (e.path.startsWith('/home/test/') ? undefined : keys.find(k => !k.startsWith('/') && e.path.endsWith(`/${k}`)))
    const text = key === undefined ? undefined : files[key]
    if (text === undefined) return { deny: `ENOENT ${e.path}` }
    return { value: text }
  })
  let seen: any
  on('tool.call', { tool: 'Agent' }, (_$: any, e: any) => {
    seen = e
    return { result: 'ran' }
  })
  const answer = await $.tool.call({ tool: 'Agent', description: 'x', prompt: 'p', ...input })
  return { seen, answer }
}

test('Agent call without model is denied, names the rubric', async ($, on) => {
  const { seen, answer } = await call($, on, {})
  expect(seen).toBe(undefined)
  expect(String(answer.text ?? answer.deny)).toContain('explore/lookup')
})

test('Agent call with model set proceeds', async ($, on) => {
  const { seen } = await call($, on, { model: 'sonnet' })
  expect(seen.model).toBe('sonnet')
})

test('fork call without model proceeds untouched', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'fork' })
  expect(seen.model).toBe(undefined)
})

test('Explore with opus is rewritten to sonnet', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'Explore', model: 'opus' })
  expect(seen.model).toBe('sonnet')
})

test('Explore with fable is rewritten to sonnet', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'Explore', model: 'fable' })
  expect(seen.model).toBe('sonnet')
})

test('Explore with sonnet proceeds', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'Explore', model: 'sonnet' })
  expect(seen.model).toBe('sonnet')
})

test('Explore with haiku proceeds, kept haiku', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'Explore', model: 'haiku' })
  expect(seen.model).toBe('haiku')
})

test('Explore with no model is rewritten to sonnet', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'Explore' })
  expect(seen.model).toBe('sonnet')
})

test('an agent type whose definition sets its own model passes untouched', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'diff-reviewer' }, {
    [`${AGENTS}/diff-reviewer.md`]: '---\nname: diff-reviewer\nmodel: opus\n---\nbody',
  })
  expect(seen.model).toBe(undefined)
})

test('an agent type whose definition sets no model is denied when bare', async ($, on) => {
  const { seen, answer } = await call($, on, { subagent_type: 'helper' }, {
    [`${AGENTS}/helper.md`]: '---\nname: helper\n---\nmodel: opus in the body only',
  })
  expect(seen).toBe(undefined)
  expect(String(answer.text ?? answer.deny)).toContain('explore/lookup')
})

test('model: inherit does not count as the definition setting its own model', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'inh' }, {
    [`${AGENTS}/inh.md`]: '---\nname: inh\nmodel: inherit\n---\nbody',
  })
  expect(seen).toBe(undefined)
})

test('an empty model key does not borrow the next key as its value', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'emp' }, {
    [`${AGENTS}/emp.md`]: '---\nname: emp\nmodel:\ntools: Read\n---\nbody',
  })
  expect(seen).toBe(undefined)
})

test('a project definition without a model is not overridden by a user one that sets it', async ($, on) => {
  const { seen } = await call($, on, { subagent_type: 'dup' }, {
    ['.claude/agents/dup.md']: '---\nname: dup\n---\nbody',
    [`${AGENTS}/dup.md`]: '---\nname: dup\nmodel: opus\n---\nbody',
  })
  expect(seen).toBe(undefined)
})
