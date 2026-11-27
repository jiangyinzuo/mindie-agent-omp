<p align="center">
  <img src="https://raw.githubusercontent.com/mindie-agent/mindie-agent/v0.1.18/assets/brand/mindie-agent-logo.png" alt="MindIE Agent" width="112" height="112">
</p>

# MindIE Agent for oh-my-pi

[![Release v1.3.0](https://img.shields.io/badge/Release-v1.3.0-blue)](https://github.com/mindie-agent/mindie-agent-omp/releases) · [English](README.en.md)

为 oh-my-pi 提供昇腾知识检索、远端 NPU 开发工具和性能诊断。运行时来自 [MindIE Agent](https://github.com/mindie-agent/mindie-agent)。

## 安装

在 oh-my-pi 中可以直接发送下面这句话。

```text
帮我按 README 安装这个插件 https://github.com/mindie-agent/mindie-agent-omp
```

在 Linux 或 WSL 上准备 `omp`、`uv`、`python3`（3.10 或更新版本）和 `git`。克隆本仓库或解压源码包，进入源码目录后运行：

```sh
uv run scripts/setup.py
```

默认安装需要支持 `--host omp` 的最新正式发布版。安装器会安装 OMP 运行时，并将源码目录注册为插件。请保留源码目录，更新后可重新运行。[下载 MindIE Agent 安装器](https://github.com/mindie-agent/mindie-agent/releases/latest/download/install.py)

源码安装可指定支持 `--host omp` 的本地安装器。配合 `--channel-base-url` 可使用指定的 wheelhouse：

```sh
uv run scripts/setup.py --install-script /path/to/install.py \
  --channel-base-url /path/to/wheelhouse
```

## 使用

新开一个 `omp` 会话，用 `/mcp list` 查看 `mindie-tools` 和 `mindie-remote-dev`。首次使用某个公开知识域时，可调用 `knowledge_sync` 下载语料，再用 `knowledge_query` 检索。Linux 和 WSL 上的知识服务需要 `systemd --user`。

会话采集默认关闭。在项目目录运行 `/mindie-capture on` 后，完成回合的问答会经 Gitleaks 脱敏并保存在本机。用 `mindie_local_search` 查询记录。`/mindie-capture status` 查看授权范围，`/mindie-capture off` 停止采集并保留已有记录。
