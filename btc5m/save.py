"""Commit data/_btc5m without ever losing it to a concurrent push.
Copies our data aside, resets to origin/main, merges file by file, commits and pushes (retries).
markets.jsonl: union by 'start' (closed rows win). JSON lists (trades, spot_1s): union by first field.
Everything else (live recordings): ours wins."""
import json, os, shutil, subprocess, sys, tempfile, time

D = "data/_btc5m"
MSG = sys.argv[1] if len(sys.argv) > 1 else "BTC5m data"


def sh(*a, check=True):
    print("+", " ".join(a)); return subprocess.run(a, check=check).returncode


def merge_jsonl(ours, theirs):
    rows = {}
    for f in (theirs, ours):
        if os.path.exists(f):
            for l in open(f):
                if l.strip():
                    r = json.loads(l); k = r.get("start")
                    if k not in rows or r.get("closed") or not rows[k].get("closed"): rows[k] = r
    return "".join(json.dumps(rows[k]) + "\n" for k in sorted(rows))


def merge_list(ours, theirs):
    try:
        a = json.load(open(theirs)) if os.path.exists(theirs) else []
        b = json.load(open(ours))
        if isinstance(a, list) and isinstance(b, list) and all(isinstance(x, list) for x in a + b):
            m = {json.dumps(x[0]): x for x in a}; m.update({json.dumps(x[0]): x for x in b})
            return json.dumps([m[k] for k in sorted(m, key=lambda k: json.loads(k))])
    except Exception as e:
        print("merge fallback", ours, e)
    return open(ours).read()


tmp = tempfile.mkdtemp(); shutil.copytree(D, f"{tmp}/d")
for attempt in range(6):
    sh("git", "fetch", "-q", "origin", "main")
    sh("git", "reset", "-q", "--hard", "origin/main")
    for root, _, files in os.walk(f"{tmp}/d"):
        for fn in files:
            src = os.path.join(root, fn); dst = os.path.join(D, os.path.relpath(src, f"{tmp}/d"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if fn == "markets.jsonl": out = merge_jsonl(src, dst)
            elif fn.endswith(".json"): out = merge_list(src, dst)
            else: shutil.copy(src, dst); continue
            open(dst, "w").write(out)
    sh("git", "add", D)
    if sh("git", "diff", "--cached", "--quiet", check=False) == 0: print("nothing to commit"); break
    sh("git", "commit", "-q", "-m", MSG)
    if sh("git", "push", "origin", "HEAD:main", check=False) == 0: print("pushed"); break
    time.sleep(10 + 10 * attempt)
else:
    sys.exit("push failed after retries")
