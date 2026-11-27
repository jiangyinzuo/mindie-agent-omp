# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Prepare the MindIE runtime, then register the plugin through omp."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from mindie_launch import HOST, ROOT

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
INSTALL_URL = "https://github.com/mindie-agent/mindie-agent/releases/latest/download/install.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-script", type=Path, help="Path to a local MindIE Agent install.py")
    parser.add_argument("--channel-base-url", help="MindIE release wheelhouse directory or URL passed to install.py")
    args = parser.parse_args()

    omp = shutil.which("omp")
    if omp is None:
        raise SystemExit("Install oh-my-pi and put `omp` on PATH before running setup.")

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("Install uv and put `uv` on PATH before running setup.")

    install_script = str(args.install_script.expanduser().resolve()) if args.install_script else INSTALL_URL
    install = [uv, "run", "--no-project", "--script", install_script, "--host", HOST, "--json"]
    if args.channel_base_url is not None:
        install.extend(["--channel-base-url", args.channel_base_url])
    env = os.environ.copy()
    # Do not let an inherited profile override the bootstrap's host selection.
    env.pop("MINDIE_AGENT_CONFIG", None)
    result = subprocess.run(install, env=env, stdout=subprocess.PIPE, check=False, creationflags=_CREATE_NO_WINDOW)
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.flush()
    code = result.returncode
    if code == 0:
        try:
            report = json.loads(result.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise SystemExit("MindIE installer did not return a valid JSON report.") from None
        configured = report.get("configured_hosts") if isinstance(report, dict) else None
        if not isinstance(configured, list) or HOST not in configured:
            raise SystemExit("MindIE installer did not configure OMP. Use an installer that supports --host omp.")
        code = subprocess.run([omp, "plugin", "link", str(ROOT)], env=env, check=False, creationflags=_CREATE_NO_WINDOW).returncode
    return 128 - code if code < 0 else code


if __name__ == "__main__":
    raise SystemExit(main())
