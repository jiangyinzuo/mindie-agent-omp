"""Select the MindIE runtime and replace this process with the requested entrypoint."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HOST = "omp"
USAGE = "Usage: mindie_launch.py tools|remote|session-start|experience"


def mindie_home(override: str, xdg: str, default: Path) -> Path:
    base = os.environ.get(override) or Path(os.environ.get(xdg) or default) / "mindie-agent"
    return Path(base).expanduser().absolute()


def runtime_python(config: Path) -> Path | None:
    if config.is_file():
        value = json.loads(config.read_text(encoding="utf-8-sig")).get("python")
        if isinstance(value, str):
            path = Path(value)
            if path.is_absolute() and path.is_file() and os.access(path, os.X_OK):
                return path
    return None


    if len(sys.argv) < 2:
        raise SystemExit(USAGE)
    operation, *args = sys.argv[1:]
    if operation == "hook" and args == ["stop"]:
        pass
    elif operation != "experience" and (operation not in {"tools", "remote", "session-start"} or args):
        raise SystemExit(USAGE)

    config_home = mindie_home("MINDIE_CONFIG_HOME", "XDG_CONFIG_HOME", Path.home() / ".config")
    data_home = mindie_home("MINDIE_DATA_HOME", "XDG_DATA_HOME", Path.home() / ".local/share")
    config = config_home / f"{HOST}.json"
    python = runtime_python(config)
    if python is None:
        raise SystemExit(f"MindIE runtime is unavailable at {config}. Run `uv run scripts/setup.py` from the plugin directory.")

    env = {
        **os.environ,
        "MINDIE_AGENT_CONFIG": str(config),
        "MINDIE_CONFIG_HOME": str(config_home),
        "MINDIE_DATA_HOME": str(data_home),
    }
    if operation == "experience":
        command.extend([str(ROOT / "scripts" / "experience.py"), *args])
    else:
        command.extend([
            "-m", "mindie_harness.cli", "--host", HOST, "--plugin-root", str(ROOT),
            "--config", str(config), "--data-dir", str(data_home),
        ])
        if operation == "hook":
            command.extend(["hook", "stop"])
        elif operation == "session-start":
            command.extend(["maintain", "--enqueue-check", "--reason", "omp_session_start"])
        else:
            command.extend(["mcp", operation])
    os.execve(python, command, env)


if __name__ == "__main__":
    main()
