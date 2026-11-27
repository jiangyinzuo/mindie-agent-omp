<p align="center">
  <img src="https://raw.githubusercontent.com/mindie-agent/mindie-agent/v0.1.18/assets/brand/mindie-agent-logo.png" alt="MindIE Agent" width="112" height="112">
</p>

# MindIE Agent for oh-my-pi

为 oh-my-pi 提供昇腾知识检索、远端 NPU 开发工具和性能诊断。运行时来自 [MindIE Agent](https://github.com/mindie-agent/mindie-agent)。

## 安装

在 Linux 或 WSL 上准备 `omp`、`uv`、`python3` 和 `git`。已在 omp 19.1.0 上验证。克隆本仓库或解压源码包，进入源码目录后运行：

```sh
uv run scripts/setup.py
```

安装器会复用本机已有的 MindIE Codex 运行时，或从 MindIE 的 `v0.1.18` 发布包安装独立运行时。源码目录是插件的安装位置，请保留。更新源码后可以再次运行同一命令。

## 使用

新开一个 `omp` 会话，用 `/mcp list` 查看 `mindie-tools` 和 `mindie-remote-dev`。首次使用某个公开知识域时，可调用 `knowledge_sync` 下载语料，再用 `knowledge_query` 检索。Linux 和 WSL 上的知识服务需要 `systemd --user`。

会话采集默认关闭。在项目目录运行 `/mindie-capture on` 后，完成回合的问答会经 Gitleaks 脱敏并保存在本机。用 `mindie_local_search` 查询记录。`/mindie-capture status` 查看授权范围，`/mindie-capture off` 停止采集并保留已有记录。
