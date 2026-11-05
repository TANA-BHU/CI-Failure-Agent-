# CI Triage Agent

An AI agent that triages failed CI runs (GitHub Actions), proposes ONE action, and executes it only after policy checks and human approval.

```
fetch logs -> redact + truncate -> LLM diagnosis (structured) -> policy check
           -> [human approval gate] -> execute (rerun / open issue) -> metrics
```

Built with LangChain (model + structured output), LangGraph (state machine + interrupt for human-in-the-loop), FastAPI, Docker, Terraform (Azure Container Apps), GitHub Actions.

## Governance (what makes this safe to run in a pipeline)
- **Allowlist**: only actions in `allowed_actions` can be proposed; anything else becomes `none`.
- **Confidence floor**: below `min_confidence`, no action is proposed.
- **Human-in-the-loop**: actions in `require_approval` pause the graph (`interrupt`) until `/approve` or the CLI prompt says yes. No approver = not approved.
- **Dry-run by default**: approved actions are only logged until `dry_run: false`.
- **Secret redaction** before logs reach the LLM or the metrics file.
- **Prompt-injection stance**: logs are wrapped as untrusted data, and the agent has no tools beyond the two allowlisted actions.

## Efficiency metrics
Every run appends to `metrics/runs.jsonl` (latency, LLM latency, tokens, cost, approved/rejected/downgraded). `ci-triage stats` summarizes. Set real prices in `config.yaml` for accurate cost.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                   # uses a stub LLM, no keys needed

# Azure OpenAI (or set llm.provider: openai and OPENAI_API_KEY)
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=...
ci-triage triage tests/fixtures/flaky_timeout.log      # prompts for approval
ci-triage triage tests/fixtures/build_error.log
ci-triage stats
```

## Run as a service
```bash
docker build -t ci-triage-agent .
docker run -p 8000:8000 -e AZURE_OPENAI_ENDPOINT=... -e AZURE_OPENAI_API_KEY=... ci-triage-agent
curl -X POST localhost:8000/triage  -H 'content-type: application/json' -d '{"ref":"/app/x.log","run_id":"1"}'
curl -X POST localhost:8000/approve -H 'content-type: application/json' -d '{"run_id":"1","approve":true}'
```

## Deploy to Azure
1. Create an Azure OpenAI deployment; put its name in `llm.model`.
2. Create a service principal with a federated credential for GitHub OIDC; add repo secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `TRIAGE_GITHUB_TOKEN` (needs `actions:write`, `issues:write`, `actions:read`).
3. First run: `terraform -chdir=infra apply` once locally to create the ACR, then use the `deploy` workflow.
4. Add `TRIAGE_AGENT_URL` (the `app_url` output) as a secret so `triage-on-failure.yml` can call it.

## Known limitations (be upfront about these in interviews)
- Pending approvals are held in memory (LangGraph `MemorySaver`), so the service is pinned to 1 replica and loses pending runs on restart. Production fix: a persistent checkpointer (Postgres/Redis) and an approval UI or Teams/Slack message.
- `/triage` and `/approve` have no authentication. Put Entra ID / API-key auth in front before exposing it.
- The runbook retriever is keyword-based; swap in a vector store (you already have ChromaDB experience) if runbooks grow.
- ACR admin credentials are used for simplicity; switch to a managed identity with `AcrPull`.
