import os
import subprocess
import sys


def test_tls_saturation_recovery_dryrun():
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dryrun_tls_saturation_recovery.py")
    result = subprocess.run(
        [sys.executable, script], check=False, capture_output=True, text=True,
        timeout=180)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "=== TLS SATURATION RECOVERY DRY RUN COMPLETED ===" in result.stdout
