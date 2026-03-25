# Security

## Reporting a vulnerability

Please report security issues **privately** so we can address them before public disclosure.

- **Preferred:** Use [GitHub Security Advisories](https://github.com/RimmonXIA/Prompt_Polisher/security/advisories/new) for this repository (if enabled for the repo).
- **Alternative:** Open a draft security advisory or contact the maintainers through a private channel they publish on their GitHub profile.

Include:

- A short description of the issue and its impact
- Steps to reproduce (proof of concept if possible)
- Affected versions or commits if known

We aim to acknowledge reports within a few business days. Please do not open public issues for undisclosed vulnerabilities.

## Scope notes

This tool calls external LLM APIs and processes user-supplied text. Treat API keys and `.env` files as secrets. Reports about model-level jailbreaks or third-party API behavior may be out of scope for this codebase; we still welcome reports that involve **this project’s** handling of input, configuration, or dependencies.

**Defense expectations:** Hardened prompts, XML-ish sections, heuristics, and the optional process score before the Critic are **one layer** of depth defense. They do **not** replace system architecture isolation, monitoring, or organization policy, and they are **not** a guarantee against adaptive attacks or all prompt-injection scenarios. See `docs/THEORY.zh.md` (limitations and adversarial discussion) for the epistemic framing.
