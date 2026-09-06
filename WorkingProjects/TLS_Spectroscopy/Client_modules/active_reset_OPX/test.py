import runpy
from pathlib import Path


path = Path(__file__).with_name("test.local.py")
if not path.exists():
    raise FileNotFoundError(
        "Run Client_modules/bootstrap_local_settings.py once to create test.local.py"
    )
runpy.run_path(str(path), run_name="__main__")
