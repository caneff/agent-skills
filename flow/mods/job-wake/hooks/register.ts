import type { Register } from 'claude-code'

// The failure signatures ADR 0003 rules a watch on a background job matches.
const SIGNATURE = 'Traceback|Error|REJECTED|bad_alloc|Killed'
const POLL_MS = 5000
// How long a launch may go without `job-run` recording its pid before the
// watch gives up and says so.
const START_GRACE_MS = 60000

// One job this session launched. `pidBefore` is the pid file as it stood before
// the launch: `job-run` reuses a name's directory, so until the file changes
// everything in it belongs to the previous run.
// `key` is where the store holds it, fixed at launch: a `/clear` changes the
// session id under a running watch.
type Watch = { name: string; key: string; pidBefore?: string; since: number; isStarted: boolean; isSignalled: boolean }

// The names a command starts runs under: `job-run --name <n> --` where a
// command can start (the head, or after a separator), as
// `wrap-background-jobs.sh` reads it. `--status` and `--wait` start nothing.
const startedNames = (command: string): string[] =>
  [...command.matchAll(/(?:^|[;&|\n])\s*job-run\s+--name\s+([A-Za-z0-9._-]+)\s+--(?=\s)/g)].map(m => m[1])

// Module state: a reload starts it over, and `session.start` refills the
// watches from the store. Launches are those seen at PreToolUse, waiting for
// their Bash call to return.
const launches = new Map<string, { watches: Watch[]; isBackground: boolean }>()
const watches = new Map<string, Watch>()
let timer: { cancel: () => void } | undefined
let isTicking = false

const jobDir = async ($: any, name: string) => `${(await $.env.get('HOME')) ?? ''}/.cache/agent-jobs/${name}`
const pidOf = async ($: any, name: string): Promise<string | undefined> => {
  const text = await $.fs.read(`${await jobDir($, name)}/pid`).catch(() => undefined)
  return typeof text === 'string' && text.trim() !== '' ? text.trim() : undefined
}
// `job-run --status`: 0 finished, 10 alive or starting, 11 killed, 12 no run.
const statusOf = async ($: any, name: string): Promise<{ code: number; line: string }> => {
  const run = await $.process.run(['job-run', '--status', name]).catch((err: unknown) => ({ exitCode: -1, stdout: String(err), stderr: '' }))
  return { code: run.exitCode, line: (run.stdout || run.stderr).trim() }
}
const failureLine = async ($: any, name: string): Promise<string | undefined> => {
  const run = await $.process.run(['grep', '-m1', '-E', SIGNATURE, `${await jobDir($, name)}/progress`]).catch(() => undefined)
  return run !== undefined && run.exitCode === 0 ? run.stdout.trim() : undefined
}

const keep = async ($: any, w: Watch) => {
  watches.set(w.name, w)
  await $.store.set(w.key, w)
}
const drop = async ($: any, w: Watch) => {
  watches.delete(w.name)
  await $.store.delete(w.key)
  if (watches.size === 0) {
    timer?.cancel()
    timer = undefined
  }
}
const wake = async ($: any, w: Watch, status: string, matched?: string) => {
  const lines = [`job-wake: job ${w.name}: ${status}`]
  if (matched !== undefined) lines.push(`matched line: ${matched}`)
  lines.push(`progress: ${await jobDir($, w.name)}/progress`)
  await $.prompt.submit({ text: lines.join('\n') })
}

const check = async ($: any, w: Watch) => {
  if (!w.isStarted) {
    const pid = await pidOf($, w.name)
    if (pid === undefined || pid === w.pidBefore) {
      if ((await $.clock.now()) - w.since < START_GRACE_MS) return
      await drop($, w)
      return wake($, w, `never recorded a start within ${START_GRACE_MS / 1000} s of its launch; no longer watched`)
    }
    await keep($, { ...w, isStarted: true })
    w = watches.get(w.name) as Watch
  }
  const { code, line } = await statusOf($, w.name)
  if (code === 10) {
    if (w.isSignalled) return
    const matched = await failureLine($, w.name)
    if (matched === undefined) return
    await keep($, { ...w, isSignalled: true })
    return wake($, w, 'still running, and its output matched a failure signature', matched)
  }
  await drop($, w)
  const matched = w.isSignalled ? undefined : await failureLine($, w.name)
  if (code === 0 || code === 11) return wake($, w, line, matched)
  return wake($, w, `its status could not be read (job-run --status exited ${code}: ${line}); no longer watched`, matched)
}

const arm = ($: any) => {
  if (timer !== undefined || watches.size === 0) return
  timer = $.clock.every(POLL_MS, () => {
    if (isTicking) return
    isTicking = true
    void (async () => {
      try {
        for (const w of [...watches.values()]) await check($, w).catch(() => undefined)
      } finally {
        isTicking = false
      }
    })()
  })
}

export const register: Register = on => {
  // A reload drops the module's timers and variables; the store keeps the
  // watches, so this session's are picked up again here.
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    const prefix = `watch:${await $.session.id()}:`
    for (const key of await $.store.keys()) {
      if (!key.startsWith(prefix)) continue
      const w = (await $.store.get(key)) as Watch | undefined
      if (w !== undefined && typeof w.name === 'string') watches.set(w.name, { ...w, key })
    }
    arm($)
    return result
  })

  // The settings hooks run beneath this one, so `next(e)` answers with the
  // rewrite `wrap-background-jobs.sh` made: the only place its job name shows.
  on('classic.PreToolUse', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    if (result.deny !== undefined) return result
    const input: any = result.updatedInput ?? e
    const names = typeof input.command === 'string' ? startedNames(input.command) : []
    if (names.length > 0) {
      const since = await $.clock.now()
      const session = await $.session.id()
      const found: Watch[] = []
      for (const name of names)
        found.push({ name, key: `watch:${session}:${name}`, pidBefore: await pidOf($, name), since, isStarted: false, isSignalled: false })
      launches.set(e.tool_use_id, { watches: found, isBackground: input.run_in_background === true })
    }
    return result
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    const launch = launches.get(e.tool_use_id)
    launches.delete(e.tool_use_id)
    if (launch === undefined || result.deny !== undefined) return result
    for (const w of launch.watches) {
      const pid = await pidOf($, w.name)
      const hasStarted = pid !== undefined && pid !== w.pidBefore
      // A call that failed before `job-run` recorded a pid (a permission
      // refusal, a settings hook's deny) started nothing to watch.
      if (result.isError === true && !hasStarted) continue
      // A foreground run that ended inside this call is in the result the
      // model is about to read; waking it again would say nothing new.
      if (!launch.isBackground && hasStarted && (await statusOf($, w.name)).code === 0) continue
      await keep($, w)
    }
    arm($)
    return result
  })
}
