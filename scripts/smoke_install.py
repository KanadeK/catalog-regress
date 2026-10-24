"""Build first, then prove the wheel works away from the checkout."""

import json
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = sorted((root / "dist").glob("*.whl"))
if len(wheels) != 1:
    raise SystemExit("Build exactly one wheel in dist before this check.")
with tempfile.TemporaryDirectory(prefix="catalog-regress-smoke-") as directory:
    work = Path(directory)
    venv.EnvBuilder(with_pip=True).create(work / "env")
    binary = work / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    subprocess.run(
        [str(binary), "-m", "pip", "install", str(wheels[0])], cwd=work, env=environment, check=True
    )
    shutil.copytree(root / "examples", work / "examples")
    for candidate, code in [("after.po", 1), ("fixed.po", 0)]:
        run = subprocess.run(
            [
                str(binary),
                "-m",
                "catalog_regress",
                "examples/before.po",
                f"examples/{candidate}",
                "--json",
            ],
            cwd=work,
            env=environment,
            capture_output=True,
            text=True,
        )
        if run.returncode != code:
            raise SystemExit(f"Unexpected smoke result: {run.returncode}, {run.stderr}")
        receipt = json.loads(run.stdout)
        if receipt["protected"] != 2 or receipt["regression_count"] != int(code == 1):
            raise SystemExit("Smoke receipt does not match the real fixture contract.")
    subprocess.run(
        [str(binary), "-m", "pip", "uninstall", "-y", "catalog-regress", "polib"],
        cwd=work,
        env=environment,
        check=True,
    )
print("Isolated wheel install, regression/pass examples and uninstall: PASS")
