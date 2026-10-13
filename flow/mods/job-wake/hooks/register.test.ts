// The cases #1371 names: clean exit, non-zero exit, kill, a failure line
// mid-run (one wake, not one per line), a job this session did not launch,
// and both ways a launch reaches the mod (an explicit `job-run --name`, and a
// background call the settings hook rewrites to one).
import { test, expect, mock } from 'claude-code/testing'

const JOBS = '/home/test/.cache/agent-jobs'
const POLL = 5000

// One job as `job-run` leaves it on disk: the pid file's text, the line and
// code `job-run --status` answers, and the progress lines.
type Job = { pid?: string; status: [number, string]; progress: string[] }

// The world beneath the mod: job directories the test edits between ticks,
// the settings hook's rewrite (`rewrite`), and the wakes that reached core.
const world = (on: any, opts: { rewrite?: (e: any) => Record<string, unknown> | undefined; session?: string; store?: Record<string, unknown>; deny?: string } = {}) => {
  const jobs: Record<string, Job> = {}
  const wakes: string[] = []
  const clock = mock.clock(on)
  mock.store(on, opts.store)
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: opts.session ?? 'S1' }))
  on('fs.read', (_$: any, e: any) => {
    const m = new RegExp(`^${JOBS}/([^/]+)/pid$`).exec(e.path)
    const pid = m === null ? undefined : jobs[m[1]]?.pid
    return pid === undefined ? { deny: `ENOENT ${e.path}` } : { value: `${pid}\n` }
  })
  on('process.run', (_$: any, e: any) => {
    const [cmd, ...args] = e.argv
    const out = (exitCode: number, stdout: string) => ({ value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } })
    if (cmd === 'job-run' && args[0] === '--status') {
      const job = jobs[args[1]]
      return job === undefined ? out(12, `unknown ${args[1]}: no run directory\n`) : out(job.status[0], `${job.status[1]}\n`)
    }
    if (cmd === 'grep') {
      const name = /agent-jobs\/([^/]+)\/progress$/.exec(args[args.length - 1])?.[1] ?? ''
      const hit = (jobs[name]?.progress ?? []).find(l => new RegExp(args[args.indexOf('-E') + 1]).test(l))
      return hit === undefined ? out(1, '') : out(0, `${hit}\n`)
    }
    return out(127, '')
  })
  on('prompt.submit', (_$: any, e: any) => {
    wakes.push(e.text)
    return { text: e.text }
  })
  on('classic.PreToolUse', { tool: 'Bash' }, (_$: any, e: any) => {
    if (opts.deny !== undefined) return { deny: opts.deny }
    const updatedInput = opts.rewrite?.(e)
    return updatedInput === undefined ? {} : { updatedInput }
  })
  // The tool itself: `tool.run` edits the job directories as the command would
  // have by the time it returned, and `tool.isError` fails the call.
  const tool: { run: () => void; isError: boolean } = { run: () => {}, isError: false }
  on('tool.call', { tool: 'Bash' }, () => {
    tool.run()
    return tool.isError ? { result: 'failed', text: 'failed', isError: true } : { result: 'ran' }
  })
  on('session.start', (_$: any, e: any) => ({ cwd: e.cwd }))
  return { jobs, wakes, clock, tool }
}

// Runs one Bash call through the mod; `during` is what the command did.
const bash = async ($: any, w: ReturnType<typeof world>, input: Record<string, unknown>, during: () => void = () => {}) => {
  w.tool.run = during
  return $.tool.call({ tool: 'Bash', ...input })
}

const START = 'job-run --name hunt -- python3 hunt.py'

test('a clean exit wakes the session once, naming the job and its status', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [10, 'alive hunt pid=100 last=x'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([])
  w.jobs.hunt.status = [0, 'finished hunt rc=0 cause=exit ended=2026-10-13T00:00:00Z']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('finished hunt rc=0 cause=exit')
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('a non-zero exit wakes with its rc', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [0, 'finished hunt rc=3 cause=exit ended=t'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('rc=3')
})

test('a killed job wakes with the killed line', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [11, 'killed hunt pid=100 gone with no exit record; last progress: step 4'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('killed hunt pid=100')
})

test('a failure line mid-run wakes once, not once per line, and the exit still wakes', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [10, 'alive hunt pid=100 last=x'], progress: ['t step 1'] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([])
  w.jobs.hunt.progress.push('t Traceback (most recent call last):', 't ValueError: bad')
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('still running')
  expect(w.wakes[0]).toContain('t Traceback (most recent call last):')
  w.jobs.hunt.progress.push('t Killed')
  await w.clock.advance(POLL * 2)
  expect(w.wakes.length).toBe(1)
  w.jobs.hunt.status = [0, 'finished hunt rc=1 cause=exit ended=t']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(2)
  expect(w.wakes[1]).toContain('finished hunt rc=1')
})

test('a job that ends with a failure line never seen mid-run names the line in the exit wake', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [0, 'finished hunt rc=1 cause=exit ended=t'], progress: ['t std::bad_alloc'] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('t std::bad_alloc')
})

test('a job this session did not launch never wakes it', async ($, on) => {
  const w = world(on)
  w.jobs.other = { pid: '7', status: [0, 'finished other rc=0 cause=exit ended=t'], progress: ['t Error'] }
  await bash($, w, { command: 'ls' })
  await bash($, w, { command: 'job-run --status other' })
  await bash($, w, { command: 'job-run --wait other', run_in_background: true })
  await bash($, w, { command: "grep -r 'job-run --name other -- x' ." })
  // Past the start grace: a watch wrongly opened on `other` would say so here.
  await w.clock.advance(60000 + POLL * 2)
  expect(w.wakes).toEqual([])
})

test('a background call the settings hook rewrites to job-run is watched under the rewritten name', async ($, on) => {
  const w = world(on, {
    rewrite: e => ({ command: `job-run --name python3-abcd1234 -- bash -c 'python3 hunt.py'`, run_in_background: true, description: e.description }),
  })
  await bash($, w, { command: 'python3 hunt.py', run_in_background: true }, () => {
    w.jobs['python3-abcd1234'] = { pid: '100', status: [0, 'finished python3-abcd1234 rc=0 cause=exit ended=t'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('finished python3-abcd1234 rc=0')
})

test('a job-run start after a separator is watched', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: 'cd /repo && job-run --name drain-skills -- drain --repo /repo', run_in_background: true }, () => {
    w.jobs['drain-skills'] = { pid: '100', status: [0, 'finished drain-skills rc=0 cause=exit ended=t'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a reused name is not read from the previous run: no wake until the new run records its pid', async ($, on) => {
  const w = world(on)
  w.jobs.hunt = { pid: '50', status: [0, 'finished hunt rc=0 cause=exit ended=yesterday'], progress: ['t Error: old'] }
  await bash($, w, { command: START, run_in_background: true })
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  w.jobs.hunt = { pid: '100', status: [0, 'finished hunt rc=0 cause=exit ended=today'], progress: [] }
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('ended=today')
})

test('a launch that never records a start wakes once saying so', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true })
  await w.clock.advance(60000 + POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('never recorded a start')
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('a foreground job-run that ended inside its own call does not wake: the model already read it', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START }, () => {
    w.jobs.hunt = { pid: '100', status: [0, 'finished hunt rc=0 cause=exit ended=t'], progress: [] }
  })
  await w.clock.advance(POLL * 3)
  expect(w.wakes).toEqual([])
})

test('a foreground job-run still alive when its call returns is watched', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START }, () => {
    w.jobs.hunt = { pid: '100', status: [10, 'alive hunt pid=100 last=x'], progress: [] }
  })
  w.jobs.hunt.status = [0, 'finished hunt rc=0 cause=exit ended=t']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a status the mod cannot read wakes with the line instead of passing for alive', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START, run_in_background: true }, () => {
    w.jobs.hunt = { pid: '100', status: [2, 'job-run: unknown flag'], progress: [] }
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('could not be read')
})

test('a denied Bash call starts no watch', async ($, on) => {
  const w = world(on, { deny: 'no' })
  await bash($, w, { command: START, run_in_background: true })
  await w.clock.advance(60000 + POLL * 2)
  expect(w.wakes).toEqual([])
})

test('a call that failed before the job recorded a start is not watched', async ($, on) => {
  const w = world(on)
  w.tool.isError = true
  await bash($, w, { command: START, run_in_background: true })
  await w.clock.advance(60000 + POLL * 2)
  expect(w.wakes).toEqual([])
})

test('a watch outlives a reload: the next session.start of the same session picks it up', async ($, on) => {
  const w = world(on, {
    store: {
      'watch:S1:hunt': { name: 'hunt', key: 'watch:S1:hunt', since: 0, isStarted: true, isSignalled: false },
      'watch:S2:theirs': { name: 'theirs', key: 'watch:S2:theirs', since: 0, isStarted: true, isSignalled: false },
    },
  })
  w.jobs.hunt = { pid: '100', status: [0, 'finished hunt rc=0 cause=exit ended=t'], progress: [] }
  w.jobs.theirs = { pid: '101', status: [0, 'finished theirs rc=0 cause=exit ended=t'], progress: [] }
  await $.session.start({ cwd: '/repo', surface: null, isInteractive: false })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('finished hunt')
})
