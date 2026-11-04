// The cases #1371 names: clean exit, non-zero exit, kill, a failure line
// mid-run (one wake, not one per line), and a job this session did not
// launch. A launch reaches the mod through the `session` file `job-run`
// writes, so no test depends on how the command was spelled.
import { test, expect, mock } from 'claude-code/testing'

const JOBS = '/home/test/.cache/agent-jobs'
const POLL = 5000
const ME = 'S1'

// One run as `job-run` leaves it on disk: who started it, the pid file's
// text, the code and line `job-run --status` answers, the progress lines and
// the mod's own markers.
type Job = { session: string; pid: string; status: [number, string]; progress: string[]; markers: Record<string, string>; group?: string }
const job = (pid: string, status: [number, string], more: Partial<Job> = {}): Job => ({ session: ME, pid, status, progress: [], markers: {}, ...more })

const ALIVE: [number, string] = [10, 'alive hunt pid=100 last=x']
const DONE: [number, string] = [0, 'finished hunt rc=0 cause=exit ended=2026-10-13T00:00:00Z']

// The world beneath the mod: job directories the test edits between ticks,
// the wakes that reached core, the lines the mod logged, and switches that
// make one of its calls fail.
const world = (on: any) => {
  const jobs: Record<string, Job> = {}
  // A job the test never made is a test bug, so reading one throws.
  const at = (name: string): Job => jobs[name] ?? (() => { throw new Error(`no job ${name}`) })()
  const wakes: string[] = []
  const logs: string[] = []
  const faults = { statusThrows: false, progressGrepCode: undefined as number | undefined, drop: undefined as string | undefined }
  const tool: { run: () => void; deny?: string } = { run: () => {} }
  const clock = mock.clock(on)
  mock.env(on, { HOME: '/home/test' })
  on('session.id', () => ({ value: ME }))
  on('session.start', (_$: any, e: any) => ({ cwd: e.cwd }))
  on('ui.log', (_$: any, e: any) => {
    logs.push(e.text)
    return { value: undefined }
  })
  const file = (path: string) => new RegExp(`^${JOBS}/([^/]+)/([^/]+)$`).exec(path)
  on('fs.read', (_$: any, e: any) => {
    const m = file(e.path)
    const j = m === null ? undefined : jobs[m[1]!]
    const text = j === undefined ? undefined : m![2] === 'pid' ? j.pid : m![2] === 'group' ? j.group : j.markers[m![2]!]
    return text === undefined ? { deny: `ENOENT ${e.path}` } : { value: `${text}\n` }
  })
  on('fs.write', (_$: any, e: any) => {
    const m = file(e.path)
    const j = m === null ? undefined : jobs[m[1]!]
    if (j === undefined) return { deny: `ENOENT ${e.path}` }
    j.markers[m![2]!] = e.text.trim()
    return { value: undefined }
  })
  on('process.run', (_$: any, e: any) => {
    const [cmd, ...args] = e.argv
    const out = (exitCode: number, stdout: string, stderr = '') => ({ value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } })
    if (cmd === 'job-run' && args[0] === '--status') {
      if (faults.statusThrows) return { deny: 'spawn job-run ENOENT' }
      const j = jobs[args[1]]
      return j === undefined ? out(12, `unknown ${args[1]}: no run directory\n`) : out(j.status[0], `${j.status[1]}\n`)
    }
    if (cmd === 'grep' && args[0] === '-rlx') {
      const id = args[args.indexOf('-e') + 1]
      const hits = Object.keys(jobs).filter(n => jobs[n]!.session === id).map(n => `${JOBS}/${n}/session`)
      return hits.length === 0 ? out(1, '') : out(0, `${hits.join('\n')}\n`)
    }
    if (cmd === 'grep' && args[0] === '-m1') {
      if (faults.progressGrepCode !== undefined) return out(faults.progressGrepCode, '', 'grep: progress: Permission denied\n')
      const name = /agent-jobs\/([^/]+)\/progress$/.exec(args[args.length - 1])?.[1] ?? ''
      const hit = (jobs[name]?.progress ?? []).find(l => new RegExp(args[args.indexOf('-E') + 1]).test(l))
      return hit === undefined ? out(1, '') : out(0, `${hit}\n`)
    }
    return out(127, '')
  })
  on('prompt.submit', (_$: any, e: any) => {
    if (faults.drop !== undefined) return { drop: faults.drop }
    wakes.push(e.text)
    return { text: e.text }
  })
  on('tool.call', { tool: 'Bash' }, () => {
    tool.run()
    return tool.deny === undefined ? { result: 'ran' } : { deny: tool.deny }
  })
  return { jobs, at, wakes, logs, faults, clock, tool }
}

// Runs one Bash call through the mod; `during` is what the command did to the
// job directories by the time it returned. The mod's short look for a new run
// sleeps on the mocked clock, so the clock moves one second while it runs.
const bash = async ($: any, w: ReturnType<typeof world>, input: Record<string, unknown>, during: () => void = () => {}) => {
  w.tool.run = during
  const answer = $.tool.call({ tool: 'Bash', ...input })
  await w.clock.advance(1000)
  return answer
}

const START = { command: 'job-run --name hunt -- python3 hunt.py', run_in_background: true }

test('a clean exit wakes the session once, naming the job, its status and its progress file', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([])
  w.at('hunt').status = DONE
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([`job-wake: job hunt: ${DONE[1]}\nprogress: ${JOBS}/hunt/progress`])
  expect(w.at('hunt').markers['woken-end']).toBe('100')
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('the Bash result that started a run says the run is watched', async ($, on) => {
  const w = world(on)
  const answer = await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  expect(answer.context.length).toBe(1)
  expect(answer.context[0]).toContain('job-wake: watching hunt')
  const plain = await bash($, w, { command: 'ls' })
  expect(plain.context).toBe(undefined)
})

test('a non-zero exit wakes with its rc', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', [0, 'finished hunt rc=3 cause=exit ended=t'])
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('rc=3')
})

test('a killed job wakes with the killed line', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', [11, 'killed hunt pid=100 gone with no exit record; last progress: step 4'])
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('killed hunt pid=100')
})

test('a failure line mid-run wakes once, not once per line, and the exit still wakes', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE, { progress: ['t step 1'] })
  })
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([])
  w.at('hunt').progress.push('t Traceback (most recent call last):', 't ValueError: bad')
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('still running')
  expect(w.wakes[0]).toContain('matched line: t Traceback (most recent call last):')
  w.at('hunt').progress.push('t Killed')
  await w.clock.advance(POLL * 2)
  expect(w.wakes.length).toBe(1)
  w.at('hunt').status = [0, 'finished hunt rc=1 cause=exit ended=t']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(2)
  expect(w.wakes[1]).toContain('finished hunt rc=1')
  expect(w.wakes[1]).not.toContain('matched line')
})

test('a job that ends with a failure line never seen mid-run names the line in the exit wake', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', [0, 'finished hunt rc=1 cause=exit ended=t'], { progress: ['t std::bad_alloc'] })
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('matched line: t std::bad_alloc')
})

test('a job another session started never wakes this one', async ($, on) => {
  const w = world(on)
  w.jobs.theirs = job('7', [0, 'finished theirs rc=1 cause=exit ended=t'], { session: 'S2', progress: ['t Error'] })
  w.jobs.nobody = job('8', [0, 'finished nobody rc=1 cause=exit ended=t'], { session: '', progress: ['t Error'] })
  await bash($, w, { command: 'job-run --status theirs' })
  await bash($, w, { command: 'job-run --name theirs -- true', run_in_background: true })
  await w.clock.advance(POLL * 4)
  expect(w.wakes).toEqual([])
})

test('a launch is watched however the command spelled it', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: 'FOO=1 nohup /usr/bin/job-run --name "hunt-$(date +%s)" -- x >/dev/null 2>&1 &' }, () => {
    w.jobs['hunt-1'] = job('100', ALIVE)
  })
  w.at('hunt-1').status = [0, 'finished hunt-1 rc=0 cause=exit ended=t']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('job hunt-1: finished hunt-1 rc=0')
})

test('a background call whose job name never appears in the command is watched', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: 'python3 hunt.py', run_in_background: true }, () => {
    w.jobs['python3-abcd1234'] = job('100', [0, 'finished python3-abcd1234 rc=0 cause=exit ended=t'])
  })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a run that records itself after its Bash call returned is still found', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: 'sleep 30; job-run --name hunt -- x', run_in_background: true })
  await w.clock.advance(POLL * 6)
  w.jobs.hunt = job('100', DONE)
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a rerun under a name is a new run: the old end is not sent again, the new one is', async ($, on) => {
  const w = world(on)
  w.jobs.hunt = job('50', [0, 'finished hunt rc=0 cause=exit ended=yesterday'], { markers: { 'woken-end': '50', 'woken-line': '50' }, progress: ['t Error: old'] })
  await bash($, w, START)
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  w.jobs.hunt = job('100', [0, 'finished hunt rc=1 cause=exit ended=today'], { markers: { 'woken-end': '50', 'woken-line': '50' }, progress: ['t Error: new'] })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('ended=today')
  expect(w.wakes[0]).toContain('matched line: t Error: new')
})

test('a second launch job-run refuses leaves the watch on the running job', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  await bash($, w, START)
  await w.clock.advance(POLL * 14)
  expect(w.wakes).toEqual([])
  w.at('hunt').status = DONE
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a foreground job-run that ended inside its own call does not wake: the model already read it', async ($, on) => {
  const w = world(on)
  const answer = await bash($, w, { command: START.command }, () => {
    w.jobs.hunt = job('100', DONE)
  })
  await w.clock.advance(POLL * 3)
  expect(w.wakes).toEqual([])
  expect(answer.context).toBe(undefined)
})

test('a foreground job-run still alive when its call returns is watched', async ($, on) => {
  const w = world(on)
  await bash($, w, { command: START.command }, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  w.at('hunt').status = DONE
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a status the mod cannot read is logged once and the run stays watched', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', [2, 'job-run: unknown flag'])
  })
  await w.clock.advance(POLL * 3)
  expect(w.wakes).toEqual([])
  expect(w.logs).toEqual(['job-wake: job-run --status hunt exited 2: job-run: unknown flag'])
  w.at('hunt').status = DONE
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a job-run that cannot be run is logged as that, not as an exit code, and the run stays watched', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', DONE)
  })
  w.faults.statusThrows = true
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  expect(w.logs.length).toBe(1)
  expect(w.logs[0]).toContain('spawn job-run ENOENT')
  expect(w.logs[0]).not.toContain('exited')
  w.faults.statusThrows = false
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

test('a progress file that cannot be searched is logged, not read as no failure line', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE, { progress: ['t Error'] })
  })
  w.faults.progressGrepCode = 2
  await w.clock.advance(POLL)
  expect(w.wakes).toEqual([])
  expect(w.logs.length).toBe(1)
  expect(w.logs[0]).toContain("could not search hunt's progress")
})

test('a wake that does not enter the session is sent again, and marked only once it has', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', DONE)
  })
  w.faults.drop = 'blocked by a hook'
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  expect(w.at('hunt').markers['woken-end']).toBe(undefined)
  expect(w.logs.length).toBe(1)
  expect(w.logs[0]).toContain('blocked by a hook')
  w.faults.drop = undefined
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.at('hunt').markers['woken-end']).toBe('100')
})

test('after a reload the session is woken for an end it was never told, and not for one it was', async ($, on) => {
  const w = world(on)
  w.jobs.told = job('100', [0, 'finished told rc=0 cause=exit ended=t'], { markers: { 'woken-end': '100' } })
  w.jobs.untold = job('101', [0, 'finished untold rc=0 cause=exit ended=t'])
  await $.session.start({ cwd: '/repo', surface: null, isInteractive: false })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('finished untold')
})

test('a run replaced by a rerun before its end was seen is forgotten, and the rerun wakes once', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  w.jobs.hunt = job('200', [0, 'finished hunt rc=0 cause=exit ended=second'])
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('ended=second')
  expect(w.at('hunt').markers['woken-end']).toBe('200')
})

test('a watched run whose directory is gone is dropped without a wake or a log', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.hunt = job('100', ALIVE)
  })
  // The pid file still answers; `job-run --status` says the run is unknown.
  w.at('hunt').status = [12, 'unknown hunt: no run directory']
  await w.clock.advance(POLL * 3)
  expect(w.wakes).toEqual([])
  expect(w.logs).toEqual([])
})

test('a refused Bash call is handed back as refused, and a run found beside it is still watched', async ($, on) => {
  const w = world(on)
  w.tool.deny = 'withheld'
  const answer = await bash($, w, START, () => {
    w.jobs.hunt = job('100', DONE)
  })
  expect(answer.deny).toBe('withheld')
  expect(answer.context).toBe(undefined)
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
})

// A sharded run: several `job-run --group` members of one session, one wake.
const shard = ($: any, w: ReturnType<typeof world>, names: string[], group = 'shards') =>
  bash($, w, { command: 'for i in 0 1 2; do job-run --group shards -- hb & done', run_in_background: true }, () => {
    names.forEach((n, i) => {
      w.jobs[n] = job(String(100 + i), ALIVE, { group })
    })
  })
const ended = (n: string, rc = 0): [number, string] => [0, `finished ${n} rc=${rc} cause=exit ended=t`]

test('a group wakes once, when its last member ends, naming the group and every member', async ($, on) => {
  const w = world(on)
  await shard($, w, ['hb0', 'hb1', 'hb2'])
  w.at('hb0').status = ended('hb0')
  w.at('hb1').status = ended('hb1')
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  w.at('hb2').status = ended('hb2')
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('job-wake: group shards: all 3 jobs ended')
  for (const n of ['hb0', 'hb1', 'hb2']) expect(w.wakes[0]).toContain(`finished ${n} rc=0`)
  for (const n of ['hb0', 'hb1', 'hb2']) expect(w.at(n).markers['woken-end']).toBe(w.at(n).pid)
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('the first member to fail wakes the group at once, and the rest ending adds no wake', async ($, on) => {
  const w = world(on)
  await shard($, w, ['hb0', 'hb1', 'hb2'])
  w.at('hb1').status = ended('hb1', 3)
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('job-wake: group shards: hb1 failed (1 of 3 jobs ended)')
  expect(w.wakes[0]).toContain('finished hb1 rc=3')
  expect(w.wakes[0]).toContain(`progress: ${JOBS}/hb1/progress`)
  expect(w.at('hb0').markers['woken-end']).toBe('100')
  w.at('hb0').status = ended('hb0')
  w.at('hb2').status = ended('hb2', 1)
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('a killed member wakes the group', async ($, on) => {
  const w = world(on)
  await shard($, w, ['hb0', 'hb1'])
  w.at('hb0').status = [11, 'killed hb0 pid=100 gone with no exit record; last progress: x']
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('hb0 failed')
  expect(w.wakes[0]).toContain('killed hb0')
})

test('a failure line in one member wakes the group once, naming the line', async ($, on) => {
  const w = world(on)
  await shard($, w, ['hb0', 'hb1'])
  w.at('hb1').progress.push('t Traceback (most recent call last):')
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('hb1 failed')
  expect(w.wakes[0]).toContain('matched line: t Traceback (most recent call last):')
  w.at('hb0').status = ended('hb0')
  w.at('hb1').status = ended('hb1', 1)
  await w.clock.advance(POLL * 3)
  expect(w.wakes.length).toBe(1)
})

test('two groups, and a run with no group, each wake on their own', async ($, on) => {
  const w = world(on)
  await bash($, w, START, () => {
    w.jobs.a0 = job('100', ALIVE, { group: 'A' })
    w.jobs.a1 = job('101', ALIVE, { group: 'A' })
    w.jobs.b0 = job('102', ALIVE, { group: 'B' })
    w.jobs.hunt = job('103', ALIVE)
  })
  w.at('a0').status = ended('a0')
  w.at('b0').status = ended('b0')
  w.at('hunt').status = DONE
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(2)
  expect(w.wakes.some(t => t.startsWith('job-wake: group B: all 1 jobs ended'))).toBe(true)
  expect(w.wakes.some(t => t.startsWith('job-wake: job hunt:'))).toBe(true)
  w.at('a1').status = ended('a1')
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(3)
  expect(w.wakes[2]).toContain('group A: all 2 jobs ended')
})

test('a group wake that does not enter the session is sent again, and marks no member until it has', async ($, on) => {
  const w = world(on)
  await shard($, w, ['hb0', 'hb1'])
  w.at('hb0').status = ended('hb0', 2)
  w.faults.drop = 'blocked by a hook'
  await w.clock.advance(POLL * 2)
  expect(w.wakes).toEqual([])
  expect(w.at('hb0').markers['woken-end']).toBe(undefined)
  expect(w.at('hb1').markers['woken-end']).toBe(undefined)
  w.faults.drop = undefined
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.at('hb1').markers['woken-end']).toBe('101')
})

test('after a reload a group whose wake was sent stays quiet, and one never sent wakes once', async ($, on) => {
  const w = world(on)
  w.jobs.told0 = job('100', ended('told0'), { group: 'T', markers: { 'woken-end': '100' } })
  w.jobs.told1 = job('101', ALIVE, { group: 'T', markers: { 'woken-end': '101' } })
  w.jobs.new0 = job('102', ended('new0'), { group: 'N' })
  w.jobs.new1 = job('103', ended('new1'), { group: 'N' })
  await $.session.start({ cwd: '/repo', surface: null, isInteractive: false })
  await w.clock.advance(POLL)
  expect(w.wakes.length).toBe(1)
  expect(w.wakes[0]).toContain('group N: all 2 jobs ended')
})
