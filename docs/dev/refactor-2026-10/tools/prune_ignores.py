"""Drop pyproject per-file-ignores entries whose file no longer triggers the ignored codes."""
import re, subprocess, sys, pathlib
p = pathlib.Path("pyproject.toml"); s = p.read_text()
block = re.search(r"\[tool\.ruff\.lint\.per-file-ignores\]\n(.*?)\n\n", s, re.S)
kept, dropped = [], []
for line in block.group(1).splitlines():
    m = re.match(r'"([^"]+)"\s*=\s*\[([^\]]*)\]', line)
    if not m: kept.append(line); continue
    f, codes = m.group(1), [c.strip().strip('"') for c in m.group(2).split(",")]
    if not pathlib.Path(f).exists(): dropped.append(f); continue
    r = subprocess.run(["ruff","check","--isolated","--select",",".join(codes),"--output-format","concise",f],capture_output=True,text=True)
    (kept if r.returncode else dropped).append(line if r.returncode else f)
new = s.replace(block.group(1), "\n".join(kept))
p.write_text(new); print("pruned:", dropped)
