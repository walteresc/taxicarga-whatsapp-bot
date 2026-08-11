# Local development commands

Use `run_local.ps1` for Django commands on Windows:

```powershell
.\run_local.ps1 check
.\run_local.ps1 test
.\run_local.ps1 run_v3_smoke --case-id s17 --case-id s54 --case-id s47
```

The launcher always uses `.venv\Scripts\python.exe`. It removes only an inherited
`OPENAI_API_KEY` from its local process before Django starts, allowing the project
`.env` to supply TaxiCarga's development credential. It does not edit Windows user
or machine variables and does not clear Meta, Chatwoot, Django, or database config.

This launcher is development-only. Django settings retain normal production
environment precedence and existing `VAR_FILE` support. Docker Compose is unchanged.

VS Code, terminals, Django `runserver`, and workers inherit environment when they
start. Restart a long-running process only when its loaded configuration differs
from the project configuration.
