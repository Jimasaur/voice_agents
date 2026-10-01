# Voice Agents

A FastAPI demonstration of real-time voice interactions for healthcare operations and service-desk intake.

This repository intentionally contains only the demo experience layer from `voice.jimmys.tools`:

- Healthcare Center demo workflows
- Service desk intake demo
- Demo-only SQLite seed data/tools
- OpenAI Realtime session minting for demo routes

It intentionally does **not** include Jimmy's personal Microsoft/Google mailbox/calendar tooling, OAuth token cache, action approvals, or personal assistant routes.

## Project status and evaluation boundary

This is a demo integration, not a production healthcare or service-management system. The SQLite workflows operate on demo data and do not establish EHR integration or compliance certification. Use synthetic information only; do not enter real patient, insurance, employee, or customer data. Live voice sessions call an external API and may incur usage charges.

### Code tour

- `server.py`: FastAPI routes, Realtime session configuration, and demo tool dispatch.
- `demo_backend.py`: SQLite-backed demo workflows, appointments, service tickets, and escalation records.
- `static/`: browser voice experience and interface assets.

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

## Before any public deployment

Review authentication and authorization for admin and tool routes, rate limiting, session protection, logging and retention, and provider credentials. The local launch command binds to loopback; do not treat this demo setup as a hardened public service.
