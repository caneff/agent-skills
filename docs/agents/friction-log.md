# Friction log

One line per friction point a controller or worker hits, instead of a prevention ticket (ADR 0005). Format: date, repo, what happened, what it cost. Read at retro; a point promoted from here becomes a ticket only on its second occurrence.


Commit each line on its own with the subject `friction: <what happened>`; a
burn's closing report counts them by that subject (`burndown/SKILL.md` § The
friction log).
