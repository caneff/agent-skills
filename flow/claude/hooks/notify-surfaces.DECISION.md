# Notify surfaces — what the prototypes settled

Eight rounds of throwaway prototypes, `notify-surfaces*.prototype.html` on
branch `prototype/notify-surfaces`. This file is the answer; the pages are the
working.

**The question:** what should tell Chris that a background job wants him again?

**The complaint that started it:** the Windows toast was wrong twice over — it
printed the raw event name instead of the message, and titled every toast with
the coordinator session's directory. Both are fixed and landed on main. But the
deeper complaint stood: one toast per event, arriving as soon as possible, is
the wrong shape.

## The design

**Surface — a rail of dots down the right screen edge.** One dot per job,
coloured by state, in fleet order so a job keeps its place. It updates silently
and continuously. It never interrupts. (Rounds 1–3: beat the toast, the panel,
the corner cluster, the taskbar pips and the single dot.)

**Alert — a beat every N minutes, N = 5.** Events are held and delivered on the
clock, not on arrival. Nothing jumps the beat. This is the whole point: not as
soon as possible, but on a rhythm you can predict. (Round 5, V3 at N = 5.)

**Standing state — the tab.** After the beat, any job that still wants Chris
keeps a tab: its dot stretches into a small bar that pokes out of the rail into
the screen. It stays until he clicks the rail. A missed beat is therefore not a
missed alert. (Round 6, S5.)

**Arrival — one slide, then stillness.** The tab grows out of its dot over
0.42s and never moves again. Grab comes from change, annoyance comes from
repeated change; a single slide buys the first without the second. It costs
about five seconds of movement per hour at N = 5. (Round 7, T2.)

**The card — the question first.** On the beat, a card opens for four seconds
and leads with what is being asked — `approve the push?` — in the job's colour,
with the job name as a subtitle. It arrives uninvited and must survive being
half-read, so the first four words carry it. (Round 8, C3.)

**The hover — deep.** Hovering the rail lists everything waiting, each with how
long it ran, how long it has waited, and its last line of output. Hovering one
tab shows just that job. This is the surface Chris went looking for, so it can
be as long as it is useful. (Round 8, C4.)

**Reserved:** a single flash of the whole screen edge, for a failure only.
Round 7 (T5) showed it works and showed why it must not fire on every beat.

## What this needs that does not exist yet

Three real gaps, in rising order of work:

1. **The hook is a one-shot.** `notify.sh` runs per notification and exits. A
   beat needs state that survives between runs — a held-events file and a timer
   that fires on the clock.
2. **The last line of output is not recorded.** The Notification payload
   carries `message`, `title` and `notification_type`, nothing more. The deep
   hover needs each job's last output line kept somewhere as it runs.
3. **The rail is a window.** Nothing in the current setup draws persistent
   always-on-top chrome on the Windows side. That is a small app, not a hook —
   the largest single piece of this.

Gap 3 is the one that decides whether this gets built. Everything above it is
cheap; the rail is not.

## Rejected, and why

- **One toast per event** — the interruption rate, not the toast, was the
  problem.
- **A full always-on panel** — a wall at twenty jobs, and you stop reading
  walls.
- **A silent tray badge** — zero interruption also means a failure can sit for
  an hour.
- **Sound and a spoken line** — cheapest of all and reaches you across the
  room, but unrepeatable: miss it and it is gone.
- **A persistent pulse** — the only mechanism here that keeps moving, and the
  one that gets resented.
- **Escalation by creeping size** — solves the wrong half; it grabs you
  eventually, which is what the old surface already did.
