# Agent notes

Authoritative user and automation docs live in the **README**; this file only points there so tooling can find a stable entry.

- **CLI as tool protocol** (stdout vs stderr, `--envelope`, `PROMPT_POLISHER_AGENT`, exit codes, envelope shape): [README — Agents and automation](https://github.com/RimmonXIA/Prompt_Polisher#cli-as-tool-protocol)
- **Theory vs implementation** (pipeline, non-claims, node → code table): [README — Theory and architecture](https://github.com/RimmonXIA/Prompt_Polisher#deep-dives--theory) and the implementation mapping table under [开发者指南](https://github.com/RimmonXIA/Prompt_Polisher#implementation-mapping-theory--code).
- **CLI invocation (Mermaid, code-accurate)** (sequence, LangGraph, `prompts/` map, stdout/stderr, `GraphState`): [docs/CLI_INVOCATION_FLOW.md](https://github.com/RimmonXIA/Prompt_Polisher/blob/main/docs/CLI_INVOCATION_FLOW.md)
- **A2A Compliance (Live Service)**: [README — A2A Integration](https://github.com/RimmonXIA/Prompt_Polisher#a2a-integration)
- **Curated link map:** [llms.txt](https://github.com/RimmonXIA/Prompt_Polisher/blob/main/llms.txt)

When changing behavior, update **README**, and if claims or theory scope shift, **docs/THEORY.zh.md** (and **docs/THEORY.en.md** when the English bridge should stay aligned).
