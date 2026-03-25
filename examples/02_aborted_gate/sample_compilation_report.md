# Prompt Polisher compilation report

## Summary

- **Compilation aborted:** yes
- **Abort reason:** heuristic_injection
- **Abort detail:** Input matched untrusted-author injection heuristics (sample).
- **Output route:** (none)
- **Critic passed:** (none)
- **Critic iterations:** (none)
- **PRM score (if used):** (none)
- **Stopped at max critic iterations:** (none)

## Radar analysis

### Structured fields

```json
{
  "task_type": "unknown",
  "alignment_risk": "high",
  "threats": ["prompt_injection_pattern"],
  "positive_reframe": "(not applied — pipeline aborted at gate)",
  "notes": "Synthetic abort example."
}
```

## Routing and anchoring

### Structured fields

```json
{}
```

## Critic loop

- **Passed:** (none)
- **Iterations:** (none)
- **PRM score:** (none)
- **Halted at cap:** (none)

### Latest feedback

```
(none)
```

### Last draft (pre-router)

```
(none)
```

## Deliverables

- **Output route:** (none)

### Final prompt

```
Compilation was aborted before a final prompt was produced. See Summary.abort_reason (sample).
```

### Workflow blueprint

```
(none)
```

### DSPy sketch

```
(none)
```
