---
name: mindie-agent
description: Use MindIE knowledge and tools for Ascend NPU engineering, including vLLM-Ascend, xLLM, MindIE-SD, AscendC and Triton development, remote NPU verification, profiling, and diagnosis.
---

# MindIE Agent

- Use `mindie-tools` for knowledge retrieval, local runtime status (`mindie_status`), environment diagnosis (`mindie_doctor`), profiling, simulation, device coordination, and debugging. Use the tool names exposed by the current session.
- Query `knowledge_query` with concise technical terms, the relevant `domain`, and observed `conditions` such as the Ascend model, CANN and framework versions, dtype, and workload shape. Read relevant revision-bound `mindie://` references with `knowledge_explain`. Verify missing conditions before applying a result. Cite the reference and its applicable conditions in engineering conclusions.
- Use `mindie-remote-dev` for authorized SSH and container work. Verify the target host, user, container, and work directory before making changes. Inspect existing remote jobs or coordinator executions before starting another run.
- Verify an existing reservation or acquire an exclusive `coordinator` lease before running an NPU benchmark, profiling capture, or workload. Keep measured timing, simulation estimates, and hardware bounds distinct.
- Treat a failed tool call as a concrete diagnostic. Check the outcome of an interrupted write or remote job before issuing another. Use `knowledge_feedback` or `knowledge_distill` when the user requests recording or distillation of specific evidence.
- `/mindie-capture on` authorizes local capture for the current working directory and its descendants. `/mindie-capture status` shows the effective scope, and `/mindie-capture off` disables capture at the current directory. Capture is disabled by default and saves redacted, completed user/assistant text in `mindie-agent/omp/experience.sqlite3` under the XDG data directory. Disabling capture retains prior records.
- Use `mindie_local_search` with a concrete keyword to retrieve captured experience for the current workspace. Its results are separate from the public MindIE knowledge feeds.
