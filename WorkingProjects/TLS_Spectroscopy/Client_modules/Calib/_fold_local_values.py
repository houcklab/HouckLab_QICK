import ast
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = os.path.join(HERE, "initialize.py")
OV = os.path.join(HERE, "local_overrides.py")


def _literal(node):
    try:
        return ast.literal_eval(node), True
    except (ValueError, TypeError):
        return None, False


def main():
    if not os.path.exists(OV):
        raise SystemExit("no local_overrides.py next to initialize.py -- nothing to fold")
    ns = {}
    with open(OV, encoding="utf-8") as f:
        exec(f.read(), ns)
    overrides = dict(ns.get("OVERRIDES", {}) or {})
    ov_folder = ns.get("outerFolder", None)

    with open(INIT, encoding="utf-8") as f:
        src = f.read()

    tree = ast.parse(src)
    lo = hi = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "BaseConfig":
                    lo, hi = node.lineno, node.end_lineno
    if lo is None:
        raise SystemExit("BaseConfig assignment not found in initialize.py")

    lines = src.splitlines(keepends=True)
    changed = []
    unchanged = []
    reference = []
    missing = []
    for key, val in overrides.items():
        pat = re.compile(r'^(\s*"' + re.escape(key) + r'"\s*:\s*)([^,#\n]+?)(\s*,)')
        matched = False
        for i in range(lo - 1, hi):
            m = pat.match(lines[i])
            if not m:
                continue
            matched = True
            cur, ok = _literal(m.group(2).strip())
            if not ok:
                reference.append(key)
                break
            if type(cur) is type(val) and cur == val:
                unchanged.append(key)
                break
            lines[i] = pat.sub(lambda mm: mm.group(1) + repr(val) + mm.group(3),
                               lines[i], count=1)
            changed.append((key, m.group(2).strip(), repr(val)))
            break
        if not matched:
            missing.append(key)

    if missing:
        raise SystemExit(
            "ABORT -- these local_overrides keys were not found as literal lines in "
            "BaseConfig, so folding would silently drop them. Nothing was written and "
            "local_overrides.py is untouched. Keys: %s" % ", ".join(sorted(missing)))

    out = "".join(lines)
    folder_written = None
    if isinstance(ov_folder, str) and ov_folder:
        m = re.search(r'^outerFolder\s*=\s*.*$', out, flags=re.M)
        if m is None:
            raise SystemExit("ABORT -- outerFolder assignment not found; nothing written")
        out = out[:m.start()] + "outerFolder = " + repr(ov_folder) + out[m.end():]
        folder_written = ov_folder

    try:
        reparsed = ast.parse(out)
    except SyntaxError as exc:
        raise SystemExit("ABORT -- rewrite produced invalid Python (%s); nothing written" % exc)

    check = {}
    checked_folder = None
    for node in reparsed.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "BaseConfig" in names:
                for k, v in zip(node.value.keys, node.value.values):
                    lval, ok = _literal(v)
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) and ok:
                        check[k.value] = lval
            if "outerFolder" in names:
                fval, ok = _literal(node.value)
                checked_folder = fval if ok else None
    for key, _o, _n in changed:
        got = check.get(key)
        if got != overrides[key] or type(got) is not type(overrides[key]):
            raise SystemExit("verification failed for %r: wanted %r, got %r"
                             % (key, overrides[key], got))
    if folder_written is not None and checked_folder != folder_written:
        raise SystemExit("verification failed for outerFolder: wanted %r, got %r"
                         % (folder_written, checked_folder))

    with open(INIT, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    print("folded %d values into initialize.py:" % len(changed))
    for k, o, n in sorted(changed):
        print("   %-22s %s -> %s" % (k, o, n))
    if folder_written is not None:
        print("   outerFolder -> %r" % folder_written)
    if unchanged:
        print("already matched (%d): %s" % (len(unchanged), ", ".join(sorted(unchanged))))
    if reference:
        print("left as symbolic reference (%d): %s" % (len(reference), ", ".join(sorted(reference))))
    print("OK -- every local_overrides key accounted for; safe to delete local_overrides.py")


main()
