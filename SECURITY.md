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
