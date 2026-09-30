# Implicit Env Keys

These variables may appear in compose without explicit declaration in version `data.yml` `formFields`.

- `CONTAINER_NAME`

Notes:

- Keep this whitelist minimal.
- Any new implicit key should be justified by 1Panel runtime behavior.

`PANEL_DB_PORT` is a **conditional service-derived value**, not a global
whitelist entry. The validator recognizes only the required, known database
selector shapes in [panel-compatibility.md](panel-compatibility.md). Both v1
and v2 inject it only after `PANEL_DB_HOST` resolves to a database record.
Prove that resolution and the selected port on each target panel before
delivery; static selector eligibility is not runtime evidence. Keep unknown
variables and manual-host configurations subject to normal form closure.
