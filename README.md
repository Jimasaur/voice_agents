# voice_agents

Standalone demo voice-agent app for JimsBots.

This repository intentionally contains only the demo experience layer from `voice.jimmys.tools`:

- Healthcare Center demo workflows
- Service desk intake demo
- Demo-only SQLite seed data/tools
- OpenAI Realtime session minting for demo routes

It intentionally does **not** include Jimmy's personal Microsoft/Google mailbox/calendar tooling, OAuth token cache, action approvals, or personal assistant routes.

## Local run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn server:app --host 127.0.0.1 --port 8031
```

Open: http://127.0.0.1:8031/demo

## Environment

Required:

- `OPENAI_API_KEY`

Optional:

- `SESSION_SECRET`
- `REALTIME_MODEL` (default `gpt-realtime-2`)
- `PUBLIC_BASE_URL` (default `https://voice.jimsbots.com`)
- `DEMO_HEALTHCARE_DB`
- `DEMO_AGENT_SETTINGS_PATH`

## Production target

- Domain: `https://voice.jimsbots.com`
- Service: `voice-agents.service`
- App dir: `/home/ubuntu/voice-agents`
- Local port: `127.0.0.1:8031`
