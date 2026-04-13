# CLI invocation flow (`uv run prompt-polisher`)

Mermaid views of the **default compile path** in [`cli.py`](../src/prompt_polisher/cli.py) (`main`): raw prompt → sanitizer → [`run_compiler_async`](../src/prompt_polisher/graph.py) → stdout. For product context see [README](../README.md); for theory see [`THEORY.en.md`](THEORY.en.md) / [`THEORY.zh.md`](THEORY.zh.md). **Keep this file aligned with code** when the CLI, graph, [`prompts/`](../src/prompt_polisher/prompts/), or [`GraphState`](../src/prompt_polisher/state.py) change. Other CLI exits (`--version`, `--serve`, `--agent-card`) are out of scope here.

---

## Diagram 1 — Sequence (CLI → graph → API → stdout)

```mermaid
sequenceDiagram
  participant User
  participant Uv as uv
  participant Entry as prompt_polisher.cli_main
  participant Settings as get_settings
  participant Text as sanitize_user_input
  participant Client as build_llm_client
  participant Runner as run_compiler_async
  participant Graph as LangGraph_compiled
  participant API as LLM_HTTP_API

  User->>Uv: uv run prompt-polisher RAW_PROMPT
  Uv->>Entry: console_script main(argv)
  Entry->>Entry: argparse resolve raw text
  Entry->>Settings: get_settings configure_logging apply_langchain_env
  Entry->>Text: strip and escape sandbox tags
  Entry->>Client: OpenAICompatibleClient
  Entry->>Runner: asyncio.run(...)
  Runner->>Graph: ainvoke or astream(initial_state)
  loop each_graph_node
    Graph->>API: AsyncOpenAI chat completions
    API-->>Graph: assistant text JSON_or_text
  end
  Graph-->>Runner: merged GraphState
  Runner-->>Entry: GraphState
  Entry->>User: stdout plain_or_markdown_or_envelope
  Note over Entry,User: stderr logs UX spinner when interactive
```

Entry: [`pyproject.toml`](../pyproject.toml) → `prompt_polisher.cli:main`. Installed `prompt-polisher` on `PATH` is the same entrypoint.

---

## Diagram 2 — LangGraph control flow

```mermaid
flowchart TD
  startNode([START])
  intent_sniffer[intent_sniffer_LLM]
  gate{should_abort_after_intent_sniffer}
  safetyAbortGate[safety_abort_gate_deterministic]
  compute_aware_router[compute_aware_router_LLM]
  structured_compiler[structured_compiler_LLM]
  red_team_critic[red_team_critic_LLM]
  afterCritic{red_team_critic_passed_or_max_iters}
  artifact_dispatcher[artifact_dispatcher_LLM]
  endNode([END])

  startNode --> intent_sniffer
  intent_sniffer --> gate
  gate -->|abort_true| safetyAbortGate
  gate -->|abort_false| compute_aware_router
  compute_aware_router --> structured_compiler
  structured_compiler --> red_team_critic
  red_team_critic --> afterCritic
  afterCritic -->|retry_compile| structured_compiler
  afterCritic -->|to_dispatcher| artifact_dispatcher
  artifact_dispatcher --> endNode
  safetyAbortGate --> endNode
```

[`should_abort_after_intent_sniffer`](../src/prompt_polisher/gate.py) drives `gate` (heuristic injection, threats, alignment flags). `afterCritic`: `red_team_critic_passed` or max iterations → `artifact_dispatcher`, else → `structured_compiler`. `safety_abort_gate` sets `compilation_aborted` and gate copy from [`prompts_bundle`](../src/prompt_polisher/prompts_bundle.py); no further LLM calls.

### Diagram 2b — `prompts/*.txt` per node

[`PromptBundle`](../src/prompt_polisher/prompts_bundle.py) (LRU key = resolved `PROMPTS_DIR`, else package data via `importlib.resources`). **System** / **user** are chat roles: **system** is the instruction stack from `*_system_*.txt`; **user** is the per-call payload (templates or JSON in [`nodes.py`](../src/prompt_polisher/nodes.py)). `_system_user` in that file appends the Pydantic JSON schema to **system** when the node expects structured output.

```mermaid
flowchart TB
  subgraph src [prompt_txt_sources]
    bundled[importlib_resources_package_data]
    local[PROMPTS_DIR_optional_override]
  end

  bundled --> loadFn[_load_text_per_filename]
  local --> loadFn
  loadFn --> PB[PromptBundle]

  subgraph llm [LLM_nodes_in_nodes_py]
    PB --> nSniffer[intent_sniffer]
    PB --> nRouter[compute_aware_router]
    PB --> nCompiler[structured_compiler]
    PB --> nCritic[red_team_critic]
    PB --> nDispatcher[artifact_dispatcher]

    nSniffer --> sR[system_base_plus_trust_slice]
    nSniffer --> uR[intent_sniffer_user_Template]
    nRouter --> sRt[system_base_plus_trust_slice]
    nRouter --> uRt[routing_user_Template]
    nCompiler --> sC[system_base_plus_trust_slice]
    nCompiler --> uC[JSON_user_assembled_in_code]
    nCritic --> sCr[system_base_plus_trust_slice]
    nCritic --> uCr[critic_user_Template]
    nDispatcher --> sRo[system_base_plus_trust_slice]
    nDispatcher --> uRo[JSON_user_assembled_in_code]
    nDispatcher --> fb[router_fallback_workflow_and_dspy]
  end

  subgraph det [safety_abort_gate_in_gate_py]
    PB --> nGate[gate_abort_helpers]
    nGate --> gUser[gate_abort_user_message_Template]
    nGate --> gWf[gate_abort_workflow_blueprint_static]
  end
```

| Step | System | User | Extras |
| --- | --- | --- | --- |
| `intent_sniffer` | `intent_sniffer_system_*` | `intent_sniffer_user.txt` | — |
| `compute_aware_router` | `routing_system_*` | `routing_user.txt` | — |
| `structured_compiler` | `compile_system_*` | JSON in [`nodes.py`](../src/prompt_polisher/nodes.py) | — |
| `red_team_critic` | `critic_system_*` | `critic_user.txt` | PRM optional |
| `artifact_dispatcher` | `router_system_*` | JSON in `nodes.py` | Fallback: `router_fallback_workflow.txt`, `router_fallback_dspy.txt` |
| `safety_abort_gate` | — | `gate_abort_user_message.txt` | `gate_abort_workflow_blueprint.txt` |

`*_system_*` = `*_system_base.txt` + `*_system_trusted.txt` or `*_system_untrusted.txt`. Template fields for `*_user.txt` match the `PromptBundle` methods in [`prompts_bundle.py`](../src/prompt_polisher/prompts_bundle.py).

---

## Diagram 3 — Stdout format, exit code, stderr UX

```mermaid
flowchart TD
  state[GraphState_after_graph]
  aborted{compilation_aborted}

  state --> aborted
  aborted -->|yes| code2[exit_code_2]
  aborted -->|no| code0[exit_code_0]

  code0 --> fmt{output_format}
  code2 --> fmt

  fmt -->|args.markdown| outMd[stdout_Markdown_report]
  fmt -->|args.envelope_or_AGENT_env| outEnv[stdout_JSON_envelope]
  fmt -->|default| outText[stdout_final_prompt_only]

  tty{stderr_is_TTY_and_not_machine_JSON}
  tty -->|yes| ux[SessionRenderer_spinner_and_panels]
  tty -->|no| quietStderr[stderr_logs_only_if_configured]

  outMd --> tty
  outEnv --> tty
  outText --> tty
```

Rich session on stderr is off when `_machine_json_stdout` is true (`--envelope` or `PROMPT_POLISHER_AGENT=1`, and not `--markdown`); see `_interactive` in `cli.py`.

---

## Diagram 4 — `GraphState` fields by node

```mermaid
flowchart TD
  subgraph initial [Initial_from_CLI]
    raw[raw_prompt]
  end

  subgraph node_intent_sniffer [Node_intent_sniffer]
    ra[intent_sniffer_result]
  end

  subgraph node_abort [Node_safety_abort_gate]
    ab[compilation_aborted abort_reason abort_detail]
    abOut[final_prompt workflow_blueprint dspy_sketch output_route compiler_draft red_team_critic_fields]
  end

  subgraph path_main [Happy_path_nodes]
    subgraph node_compute_aware_router [Node_compute_aware_router]
      rd[compute_aware_routing_decision]
    end
    subgraph node_structured_compiler [Node_structured_compiler]
      dr[compiler_draft]
    end
    subgraph node_red_team_critic [Node_red_team_critic]
      cr[red_team_critic_passed red_team_critic_feedback red_team_critic_iterations]
      prm[prm_score]
    end
    subgraph node_artifact_dispatcher [Node_artifact_dispatcher]
      ro[output_route final_prompt workflow_blueprint dspy_sketch red_team_critic_halted_max]
    end
  end

  initial --> node_intent_sniffer
  node_intent_sniffer -->|should_abort| node_abort
  node_intent_sniffer -->|continue| path_main
  node_compute_aware_router --> node_structured_compiler
  node_structured_compiler --> node_red_team_critic
  node_red_team_critic -->|retry| node_structured_compiler
  node_red_team_critic -->|to_dispatcher| node_artifact_dispatcher
```

| Stage | Keys |
| --- | --- |
| initial | `raw_prompt` |
| `intent_sniffer` | `intent_sniffer_analysis` |
| `safety_abort_gate` | abort fields, deliverables, `output_route`; clears draft/critic fields |
| `compute_aware_router` | `compute_aware_routing_decision` |
| `structured_compiler` | `compiler_draft` |
| `red_team_critic` | `red_team_critic_passed`, `red_team_critic_feedback`, `red_team_critic_iterations`; optional `prm_score` |
| `artifact_dispatcher` | `output_route`, `final_prompt`, `workflow_blueprint`, `dspy_sketch`, `red_team_critic_halted_max` |

`node_red_team_critic` may log `_critic_steps`; not in the typed `GraphState` ([`state.py`](../src/prompt_polisher/state.py)).
