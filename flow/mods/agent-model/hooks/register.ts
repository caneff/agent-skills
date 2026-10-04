import type { Register } from 'claude-code'

const DENY =
  "agent-model: this Agent call has no 'model'. Pass one — explore/lookup work uses sonnet, review/diagnosis work uses opus. (subagent_type: \"fork\" is exempt: it always inherits the parent model.)"

// True when an agent file's frontmatter (the block between the first two
// `---` lines) carries a `model:` key; the body is never read.
const setsOwnModel = (text: string): boolean => {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)
  return match !== null && /^model:[ \t]*(?!["']?inherit\b)\S/m.test(match[1])
}

export const register: Register = on => {
  on('tool.call', { tool: 'Agent' }, async ($, e, next) => {
    const type = e.subagent_type ?? ''
    if (type === 'fork') return next(e)

    if (type === 'Explore') {
      const isTier = e.model === 'sonnet' || e.model === 'haiku'
      return next(isTier ? e : { ...e, model: 'sonnet' })
    }

    if (e.model !== undefined) return next(e)

    // A type's own definition may set the model; look where agent files live.
    if (/^[\w.-]+$/.test(type)) {
      const home = await $.env.get('HOME')
      const paths = [`.claude/agents/${type}.md`]
      if (home !== undefined) paths.push(`${home}/.claude/agents/${type}.md`)
      for (const path of paths) {
        const text = await $.fs.read(path).catch(() => undefined)
        // The first definition found is the one the engine spawns.
        if (typeof text === 'string') {
          if (setsOwnModel(text)) return next(e)
          break
        }
      }
    }
    return { deny: DENY }
  })
}
