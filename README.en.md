<p align="center">
  <img src="https://raw.githubusercontent.com/mindie-agent/mindie-agent/v0.1.18/assets/brand/mindie-agent-logo.png" alt="MindIE Agent" width="112" height="112">
</p>

# MindIE Agent for oh-my-pi

[![Release v1.3.0](https://img.shields.io/badge/Release-v1.3.0-blue)](https://github.com/mindie-agent/mindie-agent-omp/releases) · [简体中文](README.md)

Ascend knowledge search, remote NPU development tools, and performance diagnostics for oh-my-pi. The runtime is provided by [MindIE Agent](https://github.com/mindie-agent/mindie-agent).

## Install

You can ask oh-my-pi to install this plugin.

```text
Install this plugin by following its README https://github.com/mindie-agent/mindie-agent-omp
```

On Linux or WSL, install `omp`, `uv`, `python3` (3.10 or newer), and `git`. Clone the repository or extract the source archive, then run this command from the source directory.

```sh
uv run scripts/setup.py
```

Default setup requires a stable MindIE Agent release that supports `--host omp`. It installs the OMP runtime and registers the source directory as a plugin. Keep the source directory in place and rerun setup after updating it. [Download the MindIE Agent installer](https://github.com/mindie-agent/mindie-agent/releases/latest/download/install.py)

For a source install, pass a local installer that supports `--host omp`. Use `--channel-base-url` to select a wheelhouse.

```sh
uv run scripts/setup.py --install-script /path/to/install.py \
  --channel-base-url /path/to/wheelhouse
```

## Use

Open a new `omp` session and run `/mcp list` to see `mindie-tools` and `mindie-remote-dev`. For a new public knowledge domain, run `knowledge_sync` to download its corpus, then search it with `knowledge_query`. Knowledge services on Linux and WSL require `systemd --user`.

Session capture is off by default. Run `/mindie-capture on` in a project directory to save completed exchanges locally after Gitleaks redaction. Search them with `mindie_local_search`. Run `/mindie-capture status` to inspect the active scope or `/mindie-capture off` to stop capture and retain existing records.
