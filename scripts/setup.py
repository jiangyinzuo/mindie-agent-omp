# /// script
# requires-python = "==3.13.*"
# dependencies = [
#   "mindie-harness @ https://github.com/mindie-agent/harness/releases/download/v0.1.8/mindie_harness-0.1.8-py3-none-any.whl#sha256=e333a567170b6530f4c83b67920ef8024158c69a2ba2d10fc746b7a3f57449ee",
# ]
# ///
"""Prepare the MindIE runtime, then register the plugin through omp."""

import json
from pathlib import Path
import shutil
import subprocess

from mindie_harness.paths import ProfileRef
from mindie_harness.runtime.knowledge_binding import ensure_knowledge_binding
from mindie_harness.runtime.wheelhouse import update_runtime

from mindie_launch import CHANNEL, HOST, ROOT, Runtime, codex_launcher, runtime


def prepare(selected: Runtime) -> None:
    profile = ProfileRef.resolve(HOST, plugin_root=ROOT, config_path=selected.config, data_dir=selected.data)
    if selected.python() is None:
        print("Installing the MindIE runtime from the pinned release channel.", flush=True)
        result = update_runtime(profile, channel_base_url=CHANNEL)
        if result.get("status") not in {"active", "up_to_date"}:
            raise SystemExit(f"MindIE runtime setup failed ({result.get('status')}, {result.get('reason')})")

    python = selected.python()
    if python is None:
        raise SystemExit(f"MindIE installation did not provide an executable interpreter at {selected.config}")
    config = selected.read()
    engine = Path(config["engine_config"])
    if not json.loads(engine.read_text(encoding="utf-8")).get("feeds"):
        binding = ensure_knowledge_binding(profile, python_executable=python, include_default_feed=True, retire_previous=True)
        if binding.get("status") != "configured":
            raise SystemExit(f"MindIE public knowledge setup failed ({binding.get('reason')})")


def main() -> None:
    omp = shutil.which("omp")
    if omp is None:
        raise SystemExit("Install oh-my-pi and put `omp` on PATH before running setup.")

    selected = runtime()
    if selected.shared:
        if selected.python() is None:
            raise SystemExit(f"Repair the existing MindIE runtime at {selected.config} before running setup.")
        codex_launcher()
        print(f"Using the existing MindIE runtime at {selected.config}.", flush=True)
    else:
        prepare(selected)
        print(f"MindIE runtime ready at {selected.config}.", flush=True)
    subprocess.run([omp, "plugin", "link", str(ROOT)], check=True)


if __name__ == "__main__":
    main()
