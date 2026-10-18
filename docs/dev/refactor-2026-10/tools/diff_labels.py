"""Capture the given run labels in memory with the current code and classify every difference vs the golden.

usage: python docs/dev/refactor-2026-10/tools/diff_labels.py RunT1 SingleShot [--variants A] [--driver plan]
(--driver plan: capture through tests/regression/driver_plan.py, the Session/PLAN driver; default driver_qicklab)
Run from the repo root with the venv active. Prints one line per differing leaf (path: old -> new) grouped
by (variant, label) and a per-label summary by field class (cfg / hw / methods.* / data_digest / sets / ...).
"""
import json, math, os, re, sys, collections
os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, os.getcwd())
driver = sys.argv[sys.argv.index("--driver") + 1] if "--driver" in sys.argv else "qicklab"
args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--variants", "--driver")]
variants = ("A",) if "--variants" in sys.argv and "A" in sys.argv[sys.argv.index("--variants") + 1] else ("A", "B")
if "--variants" in sys.argv:
    variants = tuple(sys.argv[sys.argv.index("--variants") + 1].split(","))
from tests.regression import capture as core
import importlib
drv = importlib.import_module(f"tests.regression.driver_{driver}")
golden = json.load(open("tests/regression/golden_cstq03.json", encoding="utf-8"))
res = core.capture_variants(drv.capture_all, args or None, variants)
def diff(e, x, path):
    if isinstance(e, dict) and isinstance(x, dict):
        for k in sorted(set(e) | set(x)):
            if k == "traceback": continue
            if k not in x: yield f"{path}.{k}: missing (golden={json.dumps(e[k])[:80]})"
            elif k not in e: yield f"{path}.{k}: unexpected (new={json.dumps(x[k])[:80]})"
            else: yield from diff(e[k], x[k], f"{path}.{k}")
    elif isinstance(e, list) and isinstance(x, list):
        if len(e) != len(x): yield f"{path}: length {len(e)} -> {len(x)}"
        for i, (p, q) in enumerate(zip(e, x)): yield from diff(p, q, f"{path}[{i}]")
    elif isinstance(e, float) and isinstance(x, float):
        if not (math.isclose(e, x, rel_tol=1e-9, abs_tol=1e-12) or (math.isnan(e) and math.isnan(x))): yield f"{path}: {e!r} -> {x!r}"
    elif e != x or type(e) is not type(x): yield f"{path}: {json.dumps(e)[:80]} -> {json.dumps(x)[:80]}"
def klass(p):
    if ".data_digest." in p: return "data_digest"
    if ".sets." in p: return "sets"
    if re.search(r"\.methods\[\d+\]\.(cfg_digest|cfg_delta)", p): return "methods.cfg_digest/delta"
    if re.search(r"\.methods\[\d+\]\.", p): return "methods.call"
    if ".hw." in p: return "hw"
    if ".cfg." in p: return "cfg"
    for k in ("outcome", "yoko_writes", "cfg_access", "skipped", "hw_outside"):
        if "." + k in p: return k
    return "other"
total = 0
for v in variants:
    for lab in sorted(res[v]):
        lines = list(diff(golden[v][lab], res[v][lab], f"{v}:{lab}"))
        total += len(lines)
        if not lines: print(f"== {v}:{lab}: identical"); continue
        c = collections.Counter(klass(l.split(": ", 1)[0]) for l in lines)
        print(f"== {v}:{lab}: {len(lines)} diffs {dict(c)}")
        for l in lines[:60]: print("   ", l[:220])
        if len(lines) > 60: print(f"    ... {len(lines) - 60} more")
print(f"TOTAL {total} differing leaves")
