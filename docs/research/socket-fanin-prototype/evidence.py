#!/usr/bin/env python3
# PROTOTYPE: print the timeline of peer messages received by the controller and SendMessage calls made by workers.
import json,glob,sys,os
base=os.path.expanduser("~/.claude/projects")
def load(sid):
    fs=glob.glob(f"{base}/*/{sid}.jsonl")
    return [json.loads(l) for f in fs for l in open(f) if l.strip()]
ctl="47640fb9-eb51-42af-9617-8091738c86e5"
workers={"W1":"2e14b9a9-910f-4d1d-b095-a5ffa144db78","W2":"50ca949b-1ca5-417e-9477-d30c7d5ac828","W3":"90ddbb3d-1cdc-4816-b3c9-51223b670bdb"}
ev=[]
for w,sid in workers.items():
    for r in load(sid):
        m=r.get("message",{})
        if r.get("type")=="assistant" and isinstance(m.get("content"),list):
            for c in m["content"]:
                if c.get("type")=="tool_use" and c.get("name")=="SendMessage":
                    ev.append((r["timestamp"],f"{w} SendMessage -> {c['input'].get('to')}: {str(c['input'].get('message'))[:60]}"))
        if r.get("type")=="user" and isinstance(m.get("content"),list):
            for c in m["content"]:
                if c.get("type")=="tool_result":
                    t=c.get("content"); t=t if isinstance(t,str) else json.dumps(t)
                    if "message" in t.lower() or "deliver" in t.lower(): ev.append((r["timestamp"],f"{w} tool_result: {t[:100]}"))
for r in load(ctl):
    a=r.get("attachment") or {}
    if a.get("origin",{}).get("kind")=="peer":
        ev.append((r["timestamp"],f"CTL peer-msg from {a['origin'].get('name')} body={a['origin'].get('body','')[:50]!r} rendered={r.get('rendered',[{}])[0].get('content','')[:60]!r}"))
    m=r.get("message",{})
    if r.get("type")=="assistant" and isinstance(m.get("content"),list):
        for c in m["content"]:
            if c.get("type")=="text": ev.append((r["timestamp"],f"CTL says: {c['text'][:80]!r}"))
    if r.get("type")=="user" and isinstance(m.get("content"),str):
        ev.append((r["timestamp"],f"CTL user-turn: {m['content'][:80]!r}"))
for t,e in sorted(ev): print(t,e)
