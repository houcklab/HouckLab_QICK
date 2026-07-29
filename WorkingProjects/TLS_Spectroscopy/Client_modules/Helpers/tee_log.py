import contextlib
import datetime
import os
import re
import sys

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class _Tee:

    def __init__(self, stream, handle):
        self.stream = stream
        self.handle = handle
        self.buf = ""

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.handle.write(_ANSI.sub("", line.split("\r")[-1]).rstrip() + "\n")
        if "\r" in self.buf:
            self.buf = self.buf.rsplit("\r", 1)[-1]
        if len(self.buf) > 8192:
            self.buf = self.buf[-2048:]

    def flush(self):
        for target in (self.stream, self.handle):
            try:
                target.flush()
            except Exception:
                pass

    def isatty(self):
        try:
            return self.stream.isatty()
        except Exception:
            return False

    def __getattr__(self, name):
        return getattr(self.stream, name)


def log_path(name, folder=None):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{stamp}.txt"
    for base in (folder, os.getcwd()):
        if not base:
            continue
        try:
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, fname)
            with open(path, "a"):
                pass
            return path
        except Exception:
            continue
    return fname


@contextlib.contextmanager
def tee(name, folder=None, header=None):
    path = log_path(name, folder)
    handle = open(path, "w", encoding="utf-8", buffering=1)
    out, err = sys.stdout, sys.stderr
    sys.stdout = _Tee(out, handle)
    sys.stderr = _Tee(err, handle)
    try:
        print(f"[log] writing a copy of this console to:\n[log]   {path}")
        print("[log] progress bars are collapsed to one line each in the file.")
        if header:
            print(f"[log] {header}")
        print()
        yield path
    except BaseException:
        import traceback
        print("\n[log] the run ended with an exception; traceback follows so it "
              "lands IN this file rather than only on the console:")
        traceback.print_exc()
        raise
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        sys.stdout, sys.stderr = out, err
        try:
            handle.close()
        except Exception:
            pass
        print(f"\n[log] full log written to:\n[log]   {path}")
        print("[log] send me that file rather than the console.")
