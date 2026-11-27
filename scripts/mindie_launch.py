"""Select the MindIE runtime and replace this process with the requested entrypoint."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = "https://github.com/mindie-agent/mindie-agent/releases/download/v0.1.18"
# The shared harness does not register an omp host yet. Use its Codex tool profile.
HOST = "codex"


def mindie_home(override: str, xdg: str, default: Path) -> Path:
    base = os.environ.get(override) or Path(os.environ.get(xdg) or default) / "mindie-agent"
    return Path(base).expanduser().absolute()


@dataclass(frozen=True)
class Runtime:
    config: Path
    data: Path
    shared: bool

    def read(self) -> dict:
        if self.config.is_file():
            return json.loads(self.config.read_text(encoding="utf-8-sig"))
        return {}

    def python(self) -> Path | None:
        value = self.read().get("python")
        if isinstance(value, str):
            path = Path(value)
            if path.is_absolute() and path.is_file() and os.access(path, os.X_OK):
                return path
        return None

    def flags(self) -> list[str]:
        return ["--host", HOST, "--plugin-root", str(ROOT), "--config", str(self.config), "--data-dir", str(self.data)]


def runtime() -> Runtime:
    configs = mindie_home("MINDIE_CONFIG_HOME", "XDG_CONFIG_HOME", Path.home() / ".config")
    data = mindie_home("MINDIE_DATA_HOME", "XDG_DATA_HOME", Path.home() / ".local/share")
    private = Runtime(configs / "omp" / "harness.json", data / "omp" / "runtime", shared=False)
    if override := os.environ.get("MINDIE_AGENT_CONFIG"):
        config = Path(override).expanduser().absolute()
        return private if config == private.config else Runtime(config, data, shared=True)
    shared = configs / "codex.json"
    if private.config.is_file() or not shared.is_file():
        return private
    return Runtime(shared, data, shared=True)


def codex_launcher() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser()
    launcher = codex_home / "plugins" / "data" / "mindie-agent-mindie-agent" / "hook_launcher.py"
    if not launcher.is_file():
        raise SystemExit(f"MindIE Codex launcher is missing at {launcher}")
    return launcher


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: mindie_launch.py tools|remote|session-start|experience")
    operation, *args = sys.argv[1:]
    selected = runtime()
    python = selected.python()
    if python is None:
        raise SystemExit(f"MindIE runtime is unavailable at {selected.config}. Run `uv run scripts/setup.py` from the plugin directory.")

    if operation == "experience":
        os.execv(python, [str(python), "-IB", str(ROOT / "scripts" / "experience.py"), *args])
    if operation not in {"tools", "remote", "session-start"} or args:
        raise SystemExit("Usage: mindie_launch.py tools|remote|session-start")

    env = {**os.environ, "MINDIE_AGENT_CONFIG": str(selected.config)}
    if selected.shared:
        launcher = codex_launcher()
        role = operation if operation == "session-start" else f"{operation}-mcp"
        os.execve(sys.executable, [sys.executable, "-IB", str(launcher), role], env)

    env["MINDIE_CHANNEL_BASE_URL"] = CHANNEL
    env["MINDIE_CONFIG_HOME"] = str(selected.config.parent)
    env["MINDIE_DATA_HOME"] = str(selected.data)
    env.setdefault("REMOTE_DEV_STATE_DIR", str(selected.data / "state" / HOST / "remote"))
    command = (
        ["maintain", "--enqueue-check", "--reason", "omp_session_start"]
        if operation == "session-start"
        else ["mcp", operation]
    )
    os.execve(python, [str(python), "-IB", "-m", "mindie_harness.cli", *selected.flags(), *command], env)


if __name__ == "__main__":
    main()
