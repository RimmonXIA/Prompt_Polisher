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
  radar[radar_LLM]
  gate{should_abort_after_radar}
  earlyAbort[early_abort_deterministic]
  routing[routing_LLM]
  compile[compile_LLM]
  critic[critic_LLM]
  afterCritic{critic_passed_or_max_iters}
  router[router_LLM]
  endNode([END])

  startNode --> radar
  radar --> gate
  gate -->|abort_true| earlyAbort
  gate -->|abort_false| routing
  routing --> compile
  compile --> critic
  critic --> afterCritic
  afterCritic -->|retry_compile| compile
  afterCritic -->|to_router| router
  router --> endNode
  earlyAbort --> endNode
```

[`should_abort_after_radar`](../src/prompt_polisher/gate.py) drives `gate` (heuristic injection, radar threats, alignment flags). `afterCritic`: `critic_passed` or max iterations → `router`, else → `compile`. `early_abort` sets `compilation_aborted` and gate copy from [`prompts_bundle`](../src/prompt_polisher/prompts_bundle.py); no further LLM calls.

### Diagram 2b — `prompts/*.txt` per node

[`PromptBundle`](../src/prompt_polisher/prompts_bundle.py) (LRU key = resolved `PROMPTS_DIR`, else package data via `importlib.resources`). **System** message = `*_system_base.txt` + trusted or untrusted slice per `author_trust_mode`.

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
    PB --> nRadar[radar]
    PB --> nRoute[routing]
    PB --> nCompile[compile]
    PB --> nCritic[critic]
    PB --> nRouter[router]

    nRadar --> sR[system_base_plus_trust_slice]
    nRadar --> uR[radar_user_Template]
    nRoute --> sRt[system_base_plus_trust_slice]
    nRoute --> uRt[routing_user_Template]
    nCompile --> sC[system_base_plus_trust_slice]
    nCompile --> uC[JSON_user_assembled_in_code]
    nCritic --> sCr[system_base_plus_trust_slice]
    nCritic --> uCr[critic_user_Template]
    nRouter --> sRo[system_base_plus_trust_slice]
    nRouter --> uRo[JSON_user_assembled_in_code]
    nRouter --> fb[router_fallback_workflow_and_dspy]
  end

  subgraph det [early_abort_in_gate_py]
    PB --> nGate[gate_abort_helpers]
    nGate --> gUser[gate_abort_user_message_Template]
    nGate --> gWf[gate_abort_workflow_blueprint_static]
  end
```

| Step | System | User | Extras |
| --- | --- | --- | --- |
| `radar` | `radar_system_*` | `radar_user.txt` | — |
| `routing` | `routing_system_*` | `routing_user.txt` | — |
| `compile` | `compile_system_*` | JSON in [`nodes.py`](../src/prompt_polisher/nodes.py) | — |
| `critic` | `critic_system_*` | `critic_user.txt` | PRM optional in code |
| `router` | `router_system_*` | JSON in `nodes.py` | Fallback: `router_fallback_workflow.txt`, `router_fallback_dspy.txt` |
| `early_abort` | — | `gate_abort_user_message.txt` | `gate_abort_workflow_blueprint.txt` |

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

  subgraph node_radar [Node_radar]
    ra[radar_analysis]
  end

  subgraph node_abort [Node_early_abort]
    ab[compilation_aborted abort_reason abort_detail]
    abOut[final_prompt workflow_blueprint dspy_sketch output_route draft critic_fields]
  end

  subgraph path_main [Happy_path_nodes]
    subgraph node_routing [Node_routing]
      rd[routing_decision]
    end
    subgraph node_compile [Node_compile]
      dr[draft]
    end
    subgraph node_critic [Node_critic]
      cr[critic_passed critic_feedback critic_iterations]
      prm[prm_score_optional]
    end
    subgraph node_router [Node_router]
      ro[output_route final_prompt workflow_blueprint dspy_sketch critic_halted_max]
    end
  end

  initial --> node_radar
  node_radar -->|should_abort| node_abort
  node_radar -->|continue| path_main
  node_routing --> node_compile
  node_compile --> node_critic
  node_critic -->|retry| node_compile
  node_critic -->|to_router| node_router
```

| Stage | Keys |
| --- | --- |
| initial | `raw_prompt` |
| `radar` | `radar_analysis` |
| `early_abort` | abort fields, deliverables, `output_route`; clears draft/critic fields ([`gate.py`](../src/prompt_polisher/gate.py)) |
| `routing` | `routing_decision` |
| `compile` | `draft` |
| `critic` | `critic_passed`, `critic_feedback`, `critic_iterations`; optional `prm_score` |
| `router` | `output_route`, `final_prompt`, `workflow_blueprint`, `dspy_sketch`, `critic_halted_max` |

`node_critic` may log `_critic_steps`; not in the typed `GraphState` ([`state.py`](../src/prompt_polisher/state.py)).
