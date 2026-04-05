# Custom harnesses

During `sponte init` you can pick a **built-in** harness or enter a **custom** definition (executable and fixed arguments).

## Headless model

Sponte runs the executable as a **subprocess**, passes the prompt as the final argument, and sets **`SPONTE_MODEL`** in the environment to the effective model name. Validation is **best-effort** for custom entries: if you supply a probe command, Sponte can run it; otherwise you confirm limitations at save time.

## Scope

Custom harness support stays **thin** on purpose: Sponte orchestrates CLI invocation; it does not become a second agent runtime. Prefer official harness CLIs when available.

See built-in strategies under `ralph_focus/strategies/` for how named harnesses map to binaries and flags.
