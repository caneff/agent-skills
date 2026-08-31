#!/usr/bin/env python3
"""Render recent commits across every workspace repo into one local HTML page.

Usage: generate.py [RANGE]
  RANGE: a count (20), a duration (3d, 2w), or a git rev range (abc..main).
  Default: 7d. Output: ~/.claude/landed.html — one tab per repo with commits.
"""
import subprocess, html, re, sys, datetime, collections
from pathlib import Path

HOME = Path.home()
OUT = HOME / ".claude" / "landed.html"
ROOTS = sorted(p for p in HOME.glob("src/*") if (p / ".git").exists())
ROOTS.append(HOME / ".agents" / "skills")
CAP = 50


def git(repo, *a):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def log_args(range_arg):
    if re.fullmatch(r"\d+", range_arg):
        return [f"-{range_arg}"]
    m = re.fullmatch(r"(\d+)([dw])", range_arg)
    if m:
        n, unit = int(m.group(1)), {"d": "days", "w": "weeks"}[m.group(2)]
        return [f"-{CAP}", f"--since={n} {unit} ago"]
    return [range_arg]  # rev range, verbatim


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD").strip()
    if ref:
        return ref  # e.g. origin/main
    for cand in ("main", "master"):
        if git(repo, "show-ref", "--verify", f"refs/heads/{cand}"):
            return cand
    return "HEAD"


def github_base(repo):
    url = git(repo, "remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
    return f"https://github.com/{m.group(1)}" if m else None


def collect(repo, range_arg):
    branch = default_branch(repo)
    raw = git(repo, "log", *log_args(range_arg), "--date=format:%Y-%m-%d %H:%M",
              "--pretty=format:%x1e%H%x1f%h%x1f%ad%x1f%an%x1f%s%x1f%b", branch)
    commits = []
    for rec in raw.split("\x1e"):
        if not rec.strip():
            continue
        H, h, ad, an, s, b = (rec.split("\x1f") + [""] * 6)[:6]
        files, add, rem = [], 0, 0
        for line in git(repo, "show", "--numstat", "--format=", H).splitlines():
            m = line.split("\t")
            if len(m) == 3:
                a = 0 if m[0] == "-" else int(m[0])
                r = 0 if m[1] == "-" else int(m[1])
                add += a; rem += r; files.append((m[2], a, r))
        commits.append(dict(
            H=H, h=h, date=ad, an=an, s=s,
            body=re.sub(r"(Closes #\d+|Co-Authored-By:.*)", "", b).strip(),
            closes=sorted(set(re.findall(r"Closes #(\d+)", b))),
            agent="Co-Authored-By: Claude" in b,
            files=files, add=add, rem=rem,
            diff=git(repo, "show", "--format=", H) if add + rem <= 400 else None))
    return commits


def esc(x):
    return html.escape(x)


def diff_html(d):
    out = []
    for line in d.splitlines():
        c = esc(line)
        if line.startswith(("+++", "---")):
            out.append(f'<span class="df">{c}</span>')
        elif line.startswith("@@"):
            out.append(f'<span class="dh">{c}</span>')
        elif line.startswith("diff --git"):
            out.append(f'<span class="dg">{c}</span>')
        elif line.startswith("+"):
            out.append(f'<span class="da">{c}</span>')
        elif line.startswith("-"):
            out.append(f'<span class="dr">{c}</span>')
        else:
            out.append(c)
    return "\n".join(out)


def render_repo(commits, gh):
    maxtotal = max(c["add"] + c["rem"] for c in commits) or 1
    days = collections.OrderedDict()
    for c in commits:
        days.setdefault(c["date"][:10], []).append(c)
    parts = []
    for day, cs in days.items():
        parts.append(f'<h2 class="day" data-day="{day}">{datetime.date.fromisoformat(day).strftime("%A, %B %-d")}</h2>')
        for c in cs:
            w = max(2, round(56 * (c["add"] + c["rem"]) / maxtotal))
            aw = round(w * c["add"] / (c["add"] + c["rem"])) if c["add"] + c["rem"] else 0
            hash_ = (f'<a class="hash" href="{gh}/commit/{c["H"]}">{c["h"]}</a>' if gh
                     else f'<span class="hash">{c["h"]}</span>')
            badge = '<span class="badge">agent-built</span>' if c["agent"] else ''
            closes = " ".join(
                f'<a class="issue" href="{gh}/issues/{n}">#{n}</a>' if gh else f'<span class="issue">#{n}</span>'
                for n in c["closes"])
            flist = "".join(
                f'<tr><td class="fp">{esc(f)}</td><td class="fa">+{a}</td><td class="fr">−{r}</td></tr>'
                for f, a, r in c["files"])
            if c["diff"]:
                dsec = f'<pre class="diff">{diff_html(c["diff"])}</pre>'
            else:
                where = f' — <a href="{gh}/commit/{c["H"]}">read it on GitHub</a>' if gh else ''
                dsec = f'<p class="skip">Diff skipped for size ({c["add"] + c["rem"]} changed lines){where}.</p>'
            bodyp = (f'<p class="cbody">{esc(c["body"]).replace(chr(10)+chr(10), "</p><p class=cbody>").replace(chr(10), " ")}</p>'
                     if c["body"] else '')
            preview = (f'<span class="preview">{esc(c["body"])}</span>' if c["body"]
                       else '<span class="preview nobody">(no description)</span>')
            parts.append(f'''<details class="commit" data-dt="{c["date"]}" data-day="{c["date"][:10]}"><summary>
<span class="lhs"><span class="subj">{esc(c["s"])}</span>
<span class="meta">{hash_} <span class="when">{c["date"]}</span>{badge}{closes}
<span class="bar"><i class="ba" style="width:{aw}px"></i><i class="br" style="width:{w-aw}px"></i></span>
<span class="counts">+{c["add"]} −{c["rem"]}</span></span></span>
{preview}</summary>
{bodyp}<table class="files">{flist}</table>{dsec}</details>''')
    return "".join(parts)


def main():
    range_arg = sys.argv[1] if len(sys.argv) > 1 else "7d"
    tabs, panes = [], []
    for repo in ROOTS:
        commits = collect(repo, range_arg)
        if not commits:
            continue
        name = repo.name
        nagent = sum(1 for c in commits if c["agent"])
        tabs.append(f'<button class="tab" data-pane="{name}">{name} '
                    f'<span class="tn">{len(commits)}</span></button>')
        panes.append(f'<section class="pane" id="pane-{name}" hidden>'
                     f'<p class="sub">{len(commits)} commits, <b>{nagent} agent-built</b> · '
                     f'+{sum(c["add"] for c in commits)} −{sum(c["rem"] for c in commits)} lines</p>'
                     f'{render_repo(commits, github_base(repo))}</section>')
    if not tabs:
        print(f"no commits in range '{range_arg}' in any workspace repo; page not written")
        return 1
    page = f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Landed</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Dracula Theme Soft — the user's VS Code theme (dark-only, so no light mode). */
:root {{ --bg:#191A21; --card:#282A36; --ink:#F6F6F4; --mut:#7B7F8B; --line:#44475A;
  --accent:#BF9EEE; --add:#62E884; --rem:#EE6666; --chip:#343746; --dhbg:#21222C; }}
body {{ background:var(--bg); color:var(--ink); font:15px/1.55 "IBM Plex Sans",system-ui,sans-serif;
  max-width:1400px; margin:0 auto; padding:2.5rem 1.25rem 5rem; }}
h1 {{ font:600 1.7rem/1.2 "IBM Plex Mono",monospace; margin:0; }}
.range {{ color:var(--mut); margin:.4rem 0 1.2rem; }}
.tabs {{ display:flex; gap:.4rem; flex-wrap:wrap; border-bottom:1px solid var(--line); padding-bottom:.6rem; }}
.tab {{ font:500 .82rem/1 "IBM Plex Mono",monospace; color:var(--mut); background:var(--chip);
  border:1px solid var(--line); border-radius:99px; padding:.45rem .8rem; cursor:pointer; }}
.tab.on {{ color:var(--bg); background:var(--accent); border-color:var(--accent); }}
.tab.on .tn {{ color:var(--bg); }}
.tab.zero {{ opacity:.4; }}
.age {{ font:500 .75rem/1 "IBM Plex Mono",monospace; color:var(--mut); background:var(--chip);
  border:1px solid var(--line); border-radius:4px; padding:.25rem .5rem; cursor:pointer; margin-left:.25rem; }}
.age.on {{ color:var(--bg); background:var(--accent); border-color:var(--accent); }}
.tn {{ color:var(--accent); }}
.sub {{ color:var(--mut); margin:1rem 0 0; }} .sub b {{ color:var(--accent); font-weight:600; }}
h2 {{ font:500 .85rem/1 "IBM Plex Mono",monospace; text-transform:uppercase; letter-spacing:.08em;
  color:var(--mut); border-bottom:1px solid var(--line); padding-bottom:.5rem; margin:2.4rem 0 1rem; }}
.commit {{ background:var(--card); border:1px solid var(--line); border-radius:6px; margin:0 0 .6rem; }}
.commit summary {{ cursor:pointer; padding:.7rem .9rem; list-style:none;
  display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:.3rem 1.5rem; align-items:start; }}
.commit summary::-webkit-details-marker {{ display:none; }}
.preview {{ color:var(--mut); font-size:.85rem; line-height:1.45; white-space:pre-line;
  display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }}
.nobody {{ font-style:italic; opacity:.6; }}
@media (max-width:900px) {{ .commit summary {{ grid-template-columns:1fr; }} }}
.commit[open] summary {{ border-bottom:1px solid var(--line); }}
.subj {{ font-weight:500; display:block; }}
.meta {{ display:flex; align-items:center; gap:.6rem; margin-top:.35rem; flex-wrap:wrap;
  font:400 .78rem/1 "IBM Plex Mono",monospace; color:var(--mut); }}
.hash {{ color:var(--accent); text-decoration:none; background:var(--chip); padding:.2rem .4rem; border-radius:4px; }}
.hash:hover, .issue:hover {{ text-decoration:underline; }}
.badge {{ color:var(--accent); border:1px solid var(--accent); border-radius:99px; padding:.15rem .5rem; }}
.issue {{ color:var(--mut); text-decoration:none; }}
.bar {{ display:inline-flex; height:8px; border-radius:2px; overflow:hidden; }}
.ba {{ background:var(--add); }} .br {{ background:var(--rem); }}
.counts {{ font-variant-numeric:tabular-nums; }}
.cbody {{ color:var(--mut); margin:.8rem .9rem 0; max-width:65ch; }}
.files {{ margin:.8rem .9rem; border-collapse:collapse; font:400 .78rem/1.6 "IBM Plex Mono",monospace; }}
.files td {{ padding:0 .9rem 0 0; }} .fa {{ color:var(--add); }} .fr {{ color:var(--rem); }}
.fp {{ color:var(--ink); }}
.diff {{ margin:0; padding:.8rem .9rem; overflow-x:auto; background:var(--dhbg);
  font:400 .75rem/1.5 "IBM Plex Mono",monospace; border-radius:0 0 6px 6px; }}
.da {{ color:var(--add); }} .dr {{ color:var(--rem); }} .dh {{ color:var(--accent); }}
.dg,.df {{ color:var(--mut); font-weight:600; }}
.skip {{ color:var(--mut); margin:.8rem .9rem; }} .skip a {{ color:var(--accent); }}
a {{ color:var(--accent); }}
[hidden] {{ display:none !important; }}
</style></head><body>
<h1>Landed</h1>
<p class="range">range: {esc(range_arg)} · generated {datetime.datetime.now():%Y-%m-%d %H:%M} ·
show last <span class="ages"><button class="age" data-days="1">24h</button><button
class="age" data-days="2">2d</button><button class="age" data-days="3">3d</button><button
class="age" data-days="0">all</button></span></p>
<nav class="tabs">{"".join(tabs)}</nav>
{"".join(panes)}
<script>
const tabs = document.querySelectorAll(".tab");
function show(name) {{
  tabs.forEach(t => t.classList.toggle("on", t.dataset.pane === name));
  document.querySelectorAll(".pane").forEach(p => p.hidden = p.id !== "pane-" + name);
  try {{ localStorage.setItem("landed-tab", name); }} catch (e) {{}}
}}
tabs.forEach(t => t.addEventListener("click", () => show(t.dataset.pane)));
let last = null;
try {{ last = localStorage.getItem("landed-tab"); }} catch (e) {{}}
show([...tabs].some(t => t.dataset.pane === last) ? last : tabs[0].dataset.pane);

const ages = document.querySelectorAll(".age");
function applyAge(days) {{
  const cutoff = days > 0 ? Date.now() - days * 864e5 : 0;
  ages.forEach(b => b.classList.toggle("on", +b.dataset.days === days));
  document.querySelectorAll(".commit").forEach(c => {{
    c.hidden = cutoff > 0 && new Date(c.dataset.dt.replace(" ", "T")) < cutoff;
  }});
  document.querySelectorAll("h2.day").forEach(h => {{
    h.hidden = !h.parentElement.querySelector(
      `.commit[data-day="${{h.dataset.day}}"]:not([hidden])`);
  }});
  tabs.forEach(t => {{
    const pane = document.getElementById("pane-" + t.dataset.pane);
    const n = pane.querySelectorAll(".commit:not([hidden])").length;
    t.querySelector(".tn").textContent = n;
    t.classList.toggle("zero", n === 0);
  }});
  try {{ localStorage.setItem("landed-age", days); }} catch (e) {{}}
}}
ages.forEach(b => b.addEventListener("click", () => applyAge(+b.dataset.days)));
let age = 0;
try {{ age = +localStorage.getItem("landed-age") || 0; }} catch (e) {{}}
applyAge(age);
</script></body></html>'''
    OUT.write_text(page)
    print(f"{OUT} · {len(tabs)} repo tabs · {len(page)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
