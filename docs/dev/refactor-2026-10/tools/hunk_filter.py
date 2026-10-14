"""usage: hunk_filter.py <regex> <file>...  -> prints a patch of `git diff HEAD -- files` keeping only hunks whose +/- lines match regex."""
import re, subprocess, sys
args=[a for a in sys.argv[1:] if a!="--invert"]; invert="--invert" in sys.argv
rx = re.compile(args[0]); files = args[1:]
out = []
for f in files:
    d = subprocess.run(["git", "diff", "HEAD", "--", f], capture_output=True, text=True).stdout
    if not d: continue
    lines = d.splitlines(keepends=True)
    hdr_end = next(i for i, l in enumerate(lines) if l.startswith("@@"))
    header, body = lines[:hdr_end], lines[hdr_end:]
    hunks, cur = [], []
    for l in body:
        if l.startswith("@@") and cur: hunks.append(cur); cur = []
        cur.append(l)
    if cur: hunks.append(cur)
    match = lambda h: any(rx.search(l[1:]) for l in h if l[0] in "+-" and not l.startswith(("+++", "---")))
    kept = [h for h in hunks if (not match(h)) if invert] if invert else [h for h in hunks if match(h)]
    if kept: out += header + [l for h in kept for l in h]
sys.stdout.write("".join(out))
