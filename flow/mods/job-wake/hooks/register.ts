import type { EngineInterface, Register } from 'claude-code'

// The failure signatures ADR 0003 rules a watch on a background job matches.
const SIGNATURE = 'Traceback|Error|REJECTED|bad_alloc|Killed'
const POLL_MS = 5000
// How long after a Bash call the mod keeps looking for a run that call
// started: a job launched behind a slow step records itself late.
const SCAN_WINDOW_MS = 120000
// The post-call look for a new run, so the Bash result can say it is watched:
// a background launch returns before `job-run` has written its pid.
const ANNOUNCE_TRIES = 4
const ANNOUNCE_GAP_MS = 250

// `job-run --status` exit codes (flow/bin/job-run).
const FINISHED = 0
const ALIVE = 10
const KILLED = 11
const NO_RUN = 12

// One run of a job this session started: `job-run` wrote this session's id to
// the run directory's `session` file. A rerun under the same name has another
// pid, so it is another run.
type Run = { name: string; pid: string }

// Module state: a reload starts it over, and the next scan refills it from
// the job directories, where the `woken-*` markers say what was already sent.
const runs = new Map<string, Run>()
const logged = new Set<string>()
let timer: { cancel: () => void } | undefined
let scanUntil = 0
let isTicking = false

const jobsDir = async ($: EngineInterface) => `${(await $.env.get('HOME')) ?? ''}/.cache/agent-jobs`

// Says a failure once: a tick repeats every few seconds.
const logOnce = async ($: EngineInterface, text: string) => {
  if (logged.has(text)) return
  logged.add(text)
  await $.ui.log(`job-wake: ${text}`)
}

const firstLine = async ($: EngineInterface, path: string): Promise<string | undefined> => {
  const text = await $.fs.read(path).catch(() => undefined)
  return typeof text === 'string' && text.trim() !== '' ? text.trim().split('\n')[0] : undefined
}

// A marker holds the pid of the run it was written for, so one left by an
// earlier run under the same name does not count.
const isMarked = async ($: EngineInterface, run: Run, marker: string) =>
  (await firstLine($, `${await jobsDir($)}/${run.name}/${marker}`)) === run.pid
const mark = async ($: EngineInterface, run: Run, marker: string) =>
  $.fs.write(`${await jobsDir($)}/${run.name}/${marker}`, `${run.pid}\n`)

// Finds this session's runs that have not had their end reported, and returns
// the ones it had not seen before.
const scan = async ($: EngineInterface): Promise<Run[]> => {
  const dir = await jobsDir($)
  const found = await $.process.run(['grep', '-rlx', '--include=session', '-e', await $.session.id(), dir])
  // grep answers 1 for no match; anything else is a search that did not run.
  if (found.exitCode !== 0 && found.exitCode !== 1) throw new Error(`could not list ${dir}: ${found.stderr.trim()}`)
  const fresh: Run[] = []
  for (const path of found.stdout.split('\n')) {
    const name = /\/([^/]+)\/session$/.exec(path)?.[1]
    if (name === undefined) continue
    const pid = await firstLine($, `${dir}/${name}/pid`)
    if (pid === undefined || runs.has(`${name}:${pid}`)) continue
    const run = { name, pid }
    if (await isMarked($, run, 'woken-end')) continue
    runs.set(`${name}:${pid}`, run)
    fresh.push(run)
  }
  return fresh
}

const statusOf = async ($: EngineInterface, run: Run): Promise<{ code: number; line: string }> => {
  const out = await $.process.run(['job-run', '--status', run.name])
  return { code: out.exitCode, line: (out.stdout || out.stderr).trim() }
}

const failureLine = async ($: EngineInterface, run: Run): Promise<string | undefined> => {
  const out = await $.process.run(['grep', '-m1', '-E', SIGNATURE, `${await jobsDir($)}/${run.name}/progress`])
  if (out.exitCode === 0) return out.stdout.trim()
  if (out.exitCode === 1) return undefined
  throw new Error(`could not search ${run.name}'s progress: ${out.stderr.trim()}`)
}

// True when the prompt entered the session. A wake that did not is left
// unmarked, so the next tick sends it again.
const wake = async ($: EngineInterface, run: Run, status: string, matched?: string): Promise<boolean> => {
  const lines = [`job-wake: job ${run.name}: ${status}`]
  if (matched !== undefined) lines.push(`matched line: ${matched}`)
  lines.push(`progress: ${await jobsDir($)}/${run.name}/progress`)
  const sent = await $.prompt.submit({ text: lines.join('\n') })
  if (sent.drop === undefined) return true
  await logOnce($, `the wake for ${run.name} did not enter the session (${sent.drop}); it will be sent again`)
  return false
}

const check = async ($: EngineInterface, run: Run) => {
  const key = `${run.name}:${run.pid}`
  // A rerun under this name replaced the run: its end can no longer be read.
  if ((await firstLine($, `${await jobsDir($)}/${run.name}/pid`)) !== run.pid) return runs.delete(key)
  const { code, line } = await statusOf($, run)
  const hasEnded = code === FINISHED || code === KILLED
  if (code === NO_RUN) return runs.delete(key)
  if (!hasEnded && code !== ALIVE) throw new Error(`job-run --status ${run.name} exited ${code}: ${line}`)
  const matched = (await isMarked($, run, 'woken-line')) ? undefined : await failureLine($, run)
  if (!hasEnded && matched === undefined) return
  const status = hasEnded ? line : 'still running, and its output matched a failure signature'
  if (!(await wake($, run, status, matched))) return
  if (matched !== undefined) await mark($, run, 'woken-line')
  if (!hasEnded) return
  await mark($, run, 'woken-end')
  runs.delete(key)
}

const tick = async ($: EngineInterface) => {
  if (isTicking) return
  isTicking = true
  try {
    const now = await $.clock.now()
    if (now < scanUntil) await scan($).catch(err => logOnce($, String((err as Error)?.message ?? err)))
    for (const run of [...runs.values()]) await check($, run).catch(err => logOnce($, String((err as Error)?.message ?? err)))
    if (runs.size === 0 && now >= scanUntil) {
      timer?.cancel()
      timer = undefined
    }
  } finally {
    isTicking = false
  }
}

const arm = ($: EngineInterface) => {
  if (timer === undefined) timer = $.clock.every(POLL_MS, () => void tick($))
}

export const register: Register = on => {
  // A reload, or a session picked up again, finds its unreported runs here.
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    scanUntil = (await $.clock.now()) + SCAN_WINDOW_MS
    arm($)
    return result
  })

  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const result = await next(e)
    scanUntil = (await $.clock.now()) + SCAN_WINDOW_MS
    arm($)
    // Only a call that can have started a run is worth the short wait.
    const mayLaunch = e.run_in_background === true || /job-run/.test(e.command)
    let fresh: Run[] = []
    for (let i = 0; i < (mayLaunch ? ANNOUNCE_TRIES : 1) && fresh.length === 0; i++) {
      if (i > 0) await $.clock.sleep(ANNOUNCE_GAP_MS)
      fresh = await scan($).catch(async err => {
        await logOnce($, String((err as Error)?.message ?? err))
        return []
      })
    }
    const watched: string[] = []
    for (const run of fresh) {
      // A foreground run that ended inside this call is in the result the
      // model is about to read; waking it again would say nothing new.
      const hasEndedHere =
        e.run_in_background !== true && [FINISHED, KILLED].includes((await statusOf($, run).catch(() => ({ code: ALIVE }))).code)
      if (hasEndedHere) {
        await mark($, run, 'woken-end')
        runs.delete(`${run.name}:${run.pid}`)
      } else watched.push(run.name)
    }
    // A refused call has no result to add the note to; its runs are watched all the same.
    if (watched.length === 0 || result.deny !== undefined) return result
    const note = `job-wake: watching ${watched.join(', ')}; end the turn, and a prompt arrives when it ends or prints a failure line.`
    return { ...result, context: [...(result.context ?? []), note] }
  })
}
