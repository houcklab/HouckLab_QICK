"""Full structural diff of two goldens; classify every leaf diff by field."""
import json, math, sys, collections, re
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
def diff(e, x, path):
    if isinstance(e, dict) and isinstance(x, dict):
        for k in sorted(set(e)|set(x)):
            if k == "traceback": continue
            if k not in x: yield f"{path}.{k}: missing"
            elif k not in e: yield f"{path}.{k}: unexpected"
            else: yield from diff(e[k], x[k], f"{path}.{k}")
    elif isinstance(e, list) and isinstance(x, list):
        if len(e)!=len(x): yield f"{path}: length {len(e)} -> {len(x)}"
        for i,(p,q) in enumerate(zip(e,x)): yield from diff(p,q,f"{path}[{i}]")
    elif isinstance(e,float) and isinstance(x,float):
        if not (math.isclose(e,x,rel_tol=1e-9,abs_tol=1e-12) or (math.isnan(e) and math.isnan(x))):
            yield f"{path}: {e!r} -> {x!r}"
    elif e != x or type(e) is not type(x):
        yield f"{path}: {json.dumps(e)[:80]} -> {json.dumps(x)[:80]}"
print("meta:", a.get("__meta__"), "->", b.get("__meta__"))
lines = []
added, removed = [], []
for v in ("A","B"):
    for lab in sorted(set(a[v])|set(b[v])):
        if lab not in a[v]: added.append(f"{v}:{lab}"); continue
        if lab not in b[v]: removed.append(f"{v}:{lab}"); continue
        lines += list(diff(a[v][lab], b[v][lab], f"{v}:{lab}"))
print("labels added:", added, "| labels removed:", removed)
print("total leaf diffs:", len(lines))
cat = collections.Counter(); per_label = collections.defaultdict(collections.Counter); other=[]
for l in lines:
    p = l.split(": ",1)[0]
    lab = p.split(".",1)[0]
    if ".data_digest." in p: k="data_digest"
    elif ".sets." in p: k="sets"
    elif re.search(r"\.methods\[\d+\]\.cfg_digest", p): k="methods.cfg_digest"
    elif re.search(r"\.methods\[\d+\]\.cfg_delta", p): k="methods.cfg_delta"
    elif ".hw." in p: k="hw"
    elif ".cfg." in p: k="cfg"
    elif ".outcome" in p: k="outcome"
    elif ".yoko_writes" in p: k="yoko_writes"
    elif ".cfg_access" in p: k="cfg_access"
    elif ".skipped" in p: k="skipped"
    else: k="OTHER"
    cat[k]+=1; per_label[lab][k]+=1
    if k not in ("data_digest","sets"): other.append(l)
print(cat)
print("\nper label:")
for lab in sorted(per_label): print(f"  {lab:70} {dict(per_label[lab])}")
print("\nnon-digest/sets diffs:")
for l in other: print("  ", l)
