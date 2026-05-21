"""
Standalone JimsBots demo voice-agent server.

This app is intentionally demo-only. It does not import or expose Jimmy's
personal Outlook/Gmail/calendar tools, OAuth login, token caches, or approval
state from voice.jimmys.tools.
"""
from __future__ import annotations

import html
import json
import logging
import os
import time
from collections import deque
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from demo_backend import (
    DEMO_AGENTS,
    DEMO_TOOL_DEFINITIONS,
    DEMO_TOOL_HANDLERS,
    init_demo_db,
    render_admin_html,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("voice-agents-demo")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEMO_AGENT_SETTINGS_PATH = Path(os.environ.get("DEMO_AGENT_SETTINGS_PATH", BASE_DIR / "demo_agent_settings.json"))
DEFAULT_REALTIME_MODEL = os.environ.get("REALTIME_MODEL", "gpt-realtime-2")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://voice.jimsbots.com")

REALTIME_MODEL_OPTIONS = [
    ("gpt-realtime-2", "GPT Realtime 2.0"),
]

RATE_LIMIT_SESSION = int(os.environ.get("RATE_LIMIT_SESSION", "20"))
RATE_WINDOW_SESSION_SECONDS = int(os.environ.get("RATE_WINDOW_SESSION_SECONDS", "30"))
RATE_LIMIT_TOOL = int(os.environ.get("RATE_LIMIT_TOOL", "120"))
RATE_WINDOW_TOOL_SECONDS = int(os.environ.get("RATE_WINDOW_TOOL_SECONDS", "60"))
_RATE_LIMIT_BUCKETS: dict[tuple[str, str], deque[float]] = {}

app = FastAPI(title="JimsBots Voice Agents Demo")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-change-me"),
    same_site="lax",
    https_only=os.environ.get("SESSION_HTTPS_ONLY", "true").lower() != "false",
    max_age=int(os.environ.get("VOICE_SESSION_MAX_AGE_SECONDS", str(8 * 60 * 60))),
)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _html_no_cache_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _require_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    bucket_key = (scope, key)
    bucket = _RATE_LIMIT_BUCKETS.setdefault(bucket_key, deque())
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded for {scope}; retry in a moment")
    bucket.append(now)


def _demo_agent_options() -> list[dict]:
    descriptions = {
        "medical_scheduler": "Find and book a preferred-facility or sooner nearby appointment.",
        "medical_appt_reminder": "Confirm, reschedule, or cancel a seeded upcoming appointment.",
        "medical_benefits_confirmation": "Collect insurance details for benefits verification intake.",
        "medical_discharge_followup": "Post-visit follow-up to catch barriers, worsening symptoms, and readmit risk.",
        "medical_rx_refill": "Request a prescription refill and escalate medication safety concerns.",
        "medical_general_care": "Route general care questions quickly to follow-up care or human nurse triage.",
        "medical_hypertension_checkup": "Outbound blood pressure check-in with risk capture.",
        "medical_annual_wellness": "Annual wellness reminder with a Thursday 8 AM Duluth scheduling offer.",
        "service_desk": "Collect IT incidents and service requests into demo service desk tickets.",
    }
    return [
        {
            "id": demo_id,
            "title": config.get("shortTitle") or config.get("title") or demo_id,
            "fullTitle": config.get("title") or demo_id,
            "status": config.get("status") or "Ready",
            "description": descriptions.get(demo_id, config.get("starter", "Demo workflow.")),
            "href": f"/demo/{demo_id}",
        }
        for demo_id, config in DEMO_AGENTS.items()
        if demo_id.startswith("medical_") or demo_id == "service_desk"
    ]


def _default_agent_settings() -> dict:
    return {"model": DEFAULT_REALTIME_MODEL, "voice": "alloy", "silenceMs": 700, "extraInstructions": "", "prompts": {}}


def _load_demo_agent_settings() -> dict:
    settings = _default_agent_settings()
    try:
        if DEMO_AGENT_SETTINGS_PATH.exists():
            raw = json.loads(DEMO_AGENT_SETTINGS_PATH.read_text(encoding="utf-8")) or {}
            settings.update({k: raw.get(k, v) for k, v in settings.items() if k != "prompts"})
            if isinstance(raw.get("prompts"), dict):
                settings["prompts"] = raw["prompts"]
    except Exception as exc:
        log.warning("Failed to load demo agent settings: %s", exc)
    return settings


def _save_demo_agent_settings(settings: dict) -> None:
    DEMO_AGENT_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEMO_AGENT_SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _demo_settings_for_agent(demo_id: str, config: dict) -> dict:
    settings = _load_demo_agent_settings()
    prompt_override = str((settings.get("prompts") or {}).get(demo_id) or "").strip()
    prompt = prompt_override or config.get("prompt") or ""
    extra = str(settings.get("extraInstructions") or "").strip()
    if extra:
        prompt += f"\n\nAdmin extra instructions:\n{extra}"
    return {
        "model": str(settings.get("model") or DEFAULT_REALTIME_MODEL).strip() or DEFAULT_REALTIME_MODEL,
        "voice": str(settings.get("voice") or "alloy").strip() or "alloy",
        "silenceMs": int(settings.get("silenceMs") or 700),
        "prompt": prompt,
    }


def _render_demo_index(show_admin: bool = True) -> str:
    cards = []
    for option in _demo_agent_options():
        cards.append(
            "<a class='demo-card' href='{href}'>"
            "<span class='kicker'>{status}</span>"
            "<strong>{title}</strong>"
            "<span>{description}</span>"
            "</a>".format(
                href=html.escape(option["href"]),
                status=html.escape(option["status"]),
                title=html.escape(option["title"]),
                description=html.escape(option["description"]),
            )
        )
    admin_link = "<a class='admin' href='/admin/demo'>Admin observability</a>" if show_admin else ""
    options = "".join(f"<option value='{html.escape(o['href'])}'>{html.escape(o['title'])}</option>" for o in _demo_agent_options())
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>JimsBots Voice Agents</title>
<style>
:root{{color-scheme:light dark;--ink:#111820;--muted:#415968;--line:#d7e1e8;--panel:#ffffffd9;--bg:#edf4f7;--accent:#415968}}
@media (prefers-color-scheme: dark){{:root{{--ink:#f4f8fb;--muted:#b8c7d1;--line:#283946;--panel:#101922e6;--bg:#081118;--accent:#d8e7ee}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;font-family:'Open Sans',Arial,sans-serif;background:radial-gradient(circle at top left,#fff 0,#edf4f7 35%,var(--bg) 70%);color:var(--ink)}}
main{{max-width:1120px;margin:0 auto;padding:38px 20px 52px}}.top{{display:flex;justify-content:space-between;gap:18px;align-items:center;margin-bottom:34px}}.brand{{font-weight:800;letter-spacing:.02em;color:var(--muted)}}
.admin{{color:var(--muted);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:9px 13px;background:var(--panel)}}h1{{font-size:clamp(2rem,5vw,4.4rem);line-height:.95;margin:0 0 16px;letter-spacing:-.055em}}.lede{{font-size:1.08rem;max-width:720px;color:var(--muted);line-height:1.55;margin:0 0 28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}}.demo-card{{display:flex;flex-direction:column;gap:11px;min-height:178px;padding:19px;border:1px solid var(--line);border-radius:24px;background:var(--panel);color:inherit;text-decoration:none;box-shadow:0 18px 50px #1232;transition:transform .16s ease,border-color .16s ease}}
.demo-card:hover{{transform:translateY(-3px);border-color:var(--accent)}}.kicker{{font-size:.72rem;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}strong{{font-size:1.25rem;letter-spacing:-.025em}}.demo-card span:last-child{{color:var(--muted);line-height:1.45}}.chooser{{margin:22px 0 30px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}}select,button{{font:inherit;border:1px solid var(--line);border-radius:999px;padding:11px 14px;background:var(--panel);color:var(--ink)}}button{{cursor:pointer;background:var(--accent);color:var(--bg);font-weight:800}}
</style></head><body><main><div class='top'><div class='brand'>JimsBots voice agents</div>{admin_link}</div>
<h1>Choose a voice workflow.</h1><p class='lede'>Demo voice agents using seeded fictional data only. No personal mailbox, calendar, OAuth, or production PHI is connected to this environment.</p>
<form class='chooser' onsubmit="event.preventDefault(); const v=this.workflow.value; if(v) location.assign(v);"><select name='workflow' aria-label='Choose workflow'><option value=''>Select an experience…</option>{options}</select><button>Start selected</button></form>
<div class='grid'>{''.join(cards)}</div></main></body></html>"""


def _render_voice_ui(demo_id: str, show_admin: bool = True) -> str:
    html_path = STATIC_DIR / "index.html"
    content = html_path.read_text(encoding="utf-8")
    config = DEMO_AGENTS.get(demo_id)
    if not config:
        raise HTTPException(status_code=404, detail="Unknown demo route")
    payload = json.dumps({"id": demo_id, **config}, ensure_ascii=False)
    options_payload = json.dumps(_demo_agent_options(), ensure_ascii=False)
    content = content.replace(
        "</head>",
        f"<script>window.__demoAgent = {payload}; window.__demoAgents = {options_payload}; window.__demoCanAdmin = {json.dumps(show_admin)}; window.__demoOnly = true;</script></head>",
    )
    return content


class SessionRequest(BaseModel):
    voice: str = "alloy"
    timezone: str = "America/Chicago"
    silenceMs: int = 700
    realtime: dict = {}
    prompt: str = ""
    tools: dict = {}
    lastConversation: str = ""
    demoId: str = ""


def _clamp_float(value, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return default


def _clamp_int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except Exception:
        return default


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _parse_session_json(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        log.warning("Ignoring invalid Realtime session JSON override: %s", exc)
        return {}


def _build_realtime_session_config(
    *,
    instructions: str,
    tools: list,
    voice: str,
    silence_ms: int,
    realtime: dict | None = None,
) -> dict:
    """Build a GA Realtime 2.0 session object from UI-exposed settings."""
    rt = realtime if isinstance(realtime, dict) else {}
    model = "gpt-realtime-2"
    tool_choice = str(rt.get("toolChoice") or rt.get("tool_choice") or "auto").strip()
    if tool_choice not in {"auto", "none", "required"}:
        tool_choice = "auto"

    max_tokens_raw = rt.get("maxOutputTokens", rt.get("max_output_tokens", "inf"))
    if isinstance(max_tokens_raw, str) and max_tokens_raw.strip().lower() == "inf":
        max_output_tokens = "inf"
    else:
        max_output_tokens = _clamp_int(max_tokens_raw, 4096, 1, 200000)

    transcription_model = str(rt.get("transcriptionModel") or "gpt-4o-transcribe").strip()
    transcription = None
    if transcription_model and transcription_model != "off":
        transcription = {"model": transcription_model}
        language = str(rt.get("transcriptionLanguage") or "").strip()
        prompt = str(rt.get("transcriptionPrompt") or "").strip()
        if language:
            transcription["language"] = language
        if prompt:
            transcription["prompt"] = prompt

    noise_type = str(rt.get("noiseReduction") or "near_field").strip()
    noise_reduction = None if noise_type == "off" else {"type": noise_type if noise_type in {"near_field", "far_field"} else "near_field"}

    turn_type = str(rt.get("turnDetectionType") or "server_vad").strip()
    turn_detection = None
    create_response = bool(rt.get("createResponse", True))
    interrupt_response = bool(rt.get("interruptResponse", True))
    if turn_type == "semantic_vad":
        turn_detection = {
            "type": "semantic_vad",
            "create_response": create_response,
            "interrupt_response": interrupt_response,
        }
        eagerness = str(rt.get("vadEagerness") or "auto").strip()
        if eagerness in {"low", "medium", "high", "auto"}:
            turn_detection["eagerness"] = eagerness
    elif turn_type != "off":
        turn_detection = {
            "type": "server_vad",
            "threshold": _clamp_float(rt.get("vadThreshold", 0.5), 0.5, 0, 1),
            "prefix_padding_ms": _clamp_int(rt.get("prefixPaddingMs", 300), 300, 0, 2000),
            "silence_duration_ms": _clamp_int(rt.get("silenceDurationMs", silence_ms), silence_ms, 100, 3000),
            "create_response": create_response,
            "interrupt_response": interrupt_response,
        }
        idle_timeout = _clamp_int(rt.get("idleTimeoutMs", 0), 0, 0, 600000)
        if idle_timeout:
            turn_detection["idle_timeout_ms"] = idle_timeout

    input_audio = {"turn_detection": turn_detection}
    if transcription is not None:
        input_audio["transcription"] = transcription
    if noise_reduction is not None:
        input_audio["noise_reduction"] = noise_reduction

    session = {
        "type": "realtime",
        "model": model,
        "instructions": instructions,
        "tools": tools,
        "tool_choice": tool_choice,
        "max_output_tokens": max_output_tokens,
        "audio": {
            "input": input_audio,
            "output": {
                "voice": str(voice or "alloy").strip() or "alloy",
                "speed": _clamp_float(rt.get("outputSpeed", 1), 1, 0.25, 4),
            },
        },
    }

    include_raw = rt.get("include")
    if include_raw:
        include = [part.strip() for part in str(include_raw).replace("\n", ",").split(",") if part.strip()]
        if include:
            session["include"] = include

    _deep_merge(session, _parse_session_json(rt.get("sessionJson")))
    # Keep app-owned guardrails intact even when the raw JSON escape hatch is used.
    session["type"] = "realtime"
    session["model"] = model
    session["instructions"] = instructions
    session["tools"] = tools
    return session


class ToolCallRequest(BaseModel):
    arguments: dict = {}


@app.get("/")
async def root():
    return RedirectResponse("/demo")


@app.get("/demo", response_class=HTMLResponse)
async def demo_index():
    init_demo_db()
    return HTMLResponse(_render_demo_index(), headers=_html_no_cache_headers())


@app.get("/demo/{demo_id}", response_class=HTMLResponse)
async def demo_voice(demo_id: str):
    init_demo_db()
    return HTMLResponse(_render_voice_ui(demo_id), headers=_html_no_cache_headers())


@app.get("/admin/demo", response_class=HTMLResponse)
async def demo_admin():
    init_demo_db()
    return HTMLResponse(render_admin_html(), headers=_html_no_cache_headers())


@app.get("/admin/demo/agent-settings", response_class=HTMLResponse)
async def demo_agent_settings(saved: str = "", reset: str = ""):
    init_demo_db()
    settings = _load_demo_agent_settings()
    model = html.escape(str(settings.get("model") or DEFAULT_REALTIME_MODEL))
    voice = html.escape(str(settings.get("voice") or "alloy"))
    silence = int(settings.get("silenceMs") or 700)
    extra = html.escape(str(settings.get("extraInstructions") or ""))
    notice = "<p class='notice'>Saved.</p>" if saved else ("<p class='notice'>Reset.</p>" if reset else "")
    prompt_blocks = []
    prompts = settings.get("prompts") or {}
    for demo_id, config in DEMO_AGENTS.items():
        current = html.escape(str(prompts.get(demo_id) or ""))
        default = html.escape(str(config.get("prompt") or ""))
        prompt_blocks.append(f"<details><summary>{html.escape(config.get('shortTitle') or demo_id)}</summary><textarea name='prompt__{html.escape(demo_id)}'>{current}</textarea><pre>{default}</pre></details>")
    return HTMLResponse(f"""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>Demo Agent Settings</title><style>body{{font-family:system-ui;background:#081118;color:#f4f8fb;margin:0}}main{{max-width:1000px;margin:auto;padding:24px}}textarea,input,select,button{{font:inherit;width:100%;padding:10px;margin:6px 0 14px;background:#101922;color:#f4f8fb;border:1px solid #283946;border-radius:10px}}button{{background:#9ad7ff;color:#061018;font-weight:800}}pre{{white-space:pre-wrap;max-height:180px;overflow:auto;background:#101922;padding:12px;border-radius:10px}}a{{color:#9ad7ff}}.notice{{color:#9ff0b1}}</style></head><body><main><a href='/demo'>← Demo launcher</a><h1>Demo Agent Settings</h1>{notice}<form method='post'><label>Model<input name='model' value='{model}'></label><label>Voice<input name='voice' value='{voice}'></label><label>Silence ms<input name='silenceMs' type='number' value='{silence}'></label><label>Shared extra instructions<textarea name='extraInstructions'>{extra}</textarea></label>{''.join(prompt_blocks)}<button>Save</button></form><form method='post' action='/admin/demo/agent-settings/reset'><button>Reset overrides</button></form></main></body></html>""", headers=_html_no_cache_headers())


@app.post("/admin/demo/agent-settings")
async def save_demo_agent_settings(request: Request):
    form = await request.form()
    settings = _default_agent_settings()
    settings["model"] = str(form.get("model") or DEFAULT_REALTIME_MODEL).strip() or DEFAULT_REALTIME_MODEL
    settings["voice"] = str(form.get("voice") or "alloy").strip() or "alloy"
    try:
        settings["silenceMs"] = max(300, min(3000, int(form.get("silenceMs") or 700)))
    except Exception:
        settings["silenceMs"] = 700
    settings["extraInstructions"] = str(form.get("extraInstructions") or "").strip()
    prompts = {}
    for demo_id in DEMO_AGENTS:
        value = str(form.get(f"prompt__{demo_id}") or "").strip()
        if value:
            prompts[demo_id] = value
    settings["prompts"] = prompts
    _save_demo_agent_settings(settings)
    return RedirectResponse("/admin/demo/agent-settings?saved=1", status_code=303)


@app.post("/admin/demo/agent-settings/reset")
async def reset_demo_agent_settings():
    if DEMO_AGENT_SETTINGS_PATH.exists():
        DEMO_AGENT_SETTINGS_PATH.unlink()
    return RedirectResponse("/admin/demo/agent-settings?reset=1", status_code=303)


@app.post("/client-log")
async def client_log(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    log.info("client-log ip=%s event=%s state=%s detail=%s", _client_key(request), payload.get("event"), payload.get("state"), str(payload.get("detail", ""))[:500])
    return {"ok": True}


@app.post("/session")
async def create_session(request: Request, req: SessionRequest | None = None):
    if req is None:
        req = SessionRequest()
    demo_id = (req.demoId or "").strip()
    demo_config = DEMO_AGENTS.get(demo_id)
    if not demo_config:
        raise HTTPException(status_code=400, detail="This server only creates demo sessions. Supply a valid demoId.")
    _require_rate_limit("session", f"{_client_key(request)}:{demo_id}", RATE_LIMIT_SESSION, RATE_WINDOW_SESSION_SECONDS)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")
    demo_settings = _demo_settings_for_agent(demo_id, demo_config)
    instructions = demo_settings["prompt"]
    tz = req.timezone or "America/Chicago"
    instructions += f"\n\nTimezone: interpret caller times as {tz} unless specified otherwise."
    instructions += "\n\nThis is a fictional JimsBots/Healthcare Center demo. Use seeded data only. Never request or store real PHI. Never claim a real clinical, ITSM, payer, calendar, mail, or scheduling system was changed."
    enabled_tools = set(demo_config.get("tools") or [])
    active_definitions = [t for t in DEMO_TOOL_DEFINITIONS if t.get("name") in enabled_tools]
    model = demo_settings["model"]
    if model != "gpt-realtime-2":
        log.warning("Unsupported/legacy Realtime model %s requested; forcing gpt-realtime-2 GA", model)
        model = "gpt-realtime-2"
    session_config = _build_realtime_session_config(
        instructions=instructions,
        tools=active_definitions,
        voice=req.voice or demo_settings["voice"],
        silence_ms=req.silenceMs or demo_settings["silenceMs"],
        realtime=req.realtime,
    )
    log.info("Realtime demo session %s active tools: %s", demo_id, sorted(enabled_tools))
    try:
        async with httpx.AsyncClient() as client:
            payload = {"session": session_config}
            r = await client.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
        r.raise_for_status()
        data = r.json()
        if "client_secret" not in data and data.get("value"):
            data["client_secret"] = {"value": data["value"], "expires_at": data.get("expires_at")}
        data.setdefault("model", model)
        if isinstance(data.get("session"), dict):
            data["session"]["model"] = model
        return JSONResponse(data)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:800] if exc.response is not None else str(exc)
        log.error("Session creation failed: %s", detail)
        raise HTTPException(status_code=500, detail=detail)
    except Exception as exc:
        log.exception("Session creation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/tools/{tool_name}")
async def execute_tool(request: Request, tool_name: str, req: ToolCallRequest):
    if not tool_name.startswith("demo_"):
        raise HTTPException(status_code=403, detail="This server only exposes demo tools.")
    handler = DEMO_TOOL_HANDLERS.get(tool_name)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown demo tool: {tool_name}")
    _require_rate_limit("tool", f"{_client_key(request)}:{tool_name}", RATE_LIMIT_TOOL, RATE_WINDOW_TOOL_SECONDS)
    try:
        args = dict(req.arguments or {})
        log.info("Demo tool call: %s(%s)", tool_name, args)
        result = handler(**args)
        return {"result": result}
    except Exception as exc:
        log.exception("Demo tool failed: %s", tool_name)
        return {"result": f"Error running {tool_name}: {exc}"}


@app.post("/demo/email-summary")
async def demo_email_summary():
    return {"result": "Demo email is simulated in this standalone environment. No email was sent."}


# Frontend compatibility stubs. The demo UI calls these opportunistically; the
# standalone app keeps them local/no-op so personal assistant state is not leaked.
@app.get("/auth/status")
async def auth_status():
    return {"user": None, "allowed": [], "mailProvider": "Demo only", "legacyGoogleToolsEnabled": False, "googleReauthAvailable": False}


@app.get("/preferences")
async def preferences():
    return {"quickActionsEnabled": False, "quickAllowlist": []}


@app.post("/preferences")
async def save_preferences():
    return {"ok": True}


@app.get("/action-items")
async def action_items():
    return {"items": []}


@app.get("/insights")
async def insights():
    return {"cards": []}


@app.get("/conversation/last")
async def conversation_last():
    return {"text": "", "turns": []}


@app.post("/conversation/last")
async def save_conversation_last():
    return {"ok": True}


@app.get("/conversation/history")
async def conversation_history():
    return {"items": []}


@app.post("/sidecar/turn")
async def sidecar_turn():
    return {"ok": True}


@app.get("/sidecar/state")
async def sidecar_state():
    return {"state": {}}


@app.post("/sidecar/reset")
async def sidecar_reset():
    return {"ok": True}


@app.post("/learning/turn")
async def learning_turn():
    return {"ok": True}


@app.get("/learning/state")
async def learning_state():
    return {"buckets": {"concepts": [], "next_reps": [], "pitfalls": [], "resources": [], "project_seeds": [], "questions": []}}


@app.post("/learning/reset")
async def learning_reset():
    return {"ok": True}


@app.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    raise HTTPException(status_code=404, detail="Drafts are not available in the standalone demo app")


@app.get("/health")
async def health():
    return {"status": "ok", "app": "voice_agents", "publicBaseUrl": PUBLIC_BASE_URL}
