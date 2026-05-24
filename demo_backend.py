"""Healthcare demo backend for voice.jimsbots.com.

Uses seeded/non-production data. Do not use for real PHI, scheduling, or benefits work.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DEMO_HEALTHCARE_DB", BASE_DIR / "demo_healthcare.sqlite3"))

DEMO_AGENTS = {
    "medical_scheduler": {
        "title": "Healthcare Center Scheduler",
        "shortTitle": "Medical Scheduler",
        "status": "Scheduler ready",
        "trustCue": "Healthcare Center scheduling",
        "starter": "Thank you for calling Healthcare Center scheduling. I can help find an appointment. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-scheduler": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_compare_facility_options", "demo_list_open_slots", "demo_book_appointment", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center medical scheduler using seeded, non-production data. Do not claim access to a real medical record or real PHI.

Workflow:
1. Greet as Healthcare Center scheduling.
2. Verify the caller with name and passkey/keyphrase only. If the caller says they are new, do not force lookup; collect name and passkey, then use demo_register_patient to create a seeded demo account.
3. Use demo_lookup_patient before discussing appointments for returning callers. For newly registered callers, use the patient returned by demo_register_patient.
4. Ask what type of appointment they need.
5. Use demo_compare_facility_options. Then ask this exact style of question: "I can either get you in at your preferred facility in Duluth, [preferred facility], on [date/time], or sooner at our [nearby facility] location on [date/time]. Which would you prefer?"
6. Do not use a street address. Use only city/facility names.
7. Once the caller chooses preferred facility vs sooner nearby location, use demo_book_appointment with the selected slot_id.
8. If you cannot complete scheduling, use demo_add_callback_task.
9. Registration is verbal in this demo: collect only name, passkey, and optional city/preferred facility/phone/DOB if the caller volunteers them. Do not ask for real PHI.

Style: warm, concise, phone-scheduler professional. Never claim anything was booked in a real medical system. Confirm naturally as an appointment summary for this experience.""",
    },
    "medical_appt_reminder": {
        "title": "Healthcare Center Confirmation Line",
        "shortTitle": "Appointment Reminder",
        "status": "Confirmation line ready",
        "trustCue": "Healthcare Center appointment confirmation",
        "starter": "You've reached the Healthcare Center scheduling confirmation line. I can confirm your next appointment after verifying your name and passkey.",
        "toolGroups": {"demo-medical-reminder": True},
        "tools": ["demo_verify_and_get_next_appointment", "demo_lookup_patient", "demo_register_patient", "demo_get_next_appointment", "demo_confirm_appointment", "demo_request_appointment_change"],
        "prompt": """You are a Healthcare Center scheduling confirmation line using seeded, non-production data.

Workflow:
1. Open with: "You've reached the Healthcare Center scheduling confirmation line."
2. Verify the caller with name and passkey/keyphrase using demo_verify_and_get_next_appointment. If the caller says they are new, collect name and passkey, then use demo_register_patient to create a seeded demo account.
3. If the tool returns matched=true, immediately say: "Thank you, you're verified as [patient name]." Then read only the next appointment from the same tool result.
4. Do not say verification failed when matched=true. Do not ask for the same demographics again after matched=true.
5. Ask whether they want to confirm it, request reschedule, or request cancel.
6. Use demo_confirm_appointment or demo_request_appointment_change.

Fallback only: use demo_lookup_patient and demo_get_next_appointment separately if the combined verification tool is unavailable.

Style: brief and phone-like. Do not discuss unrelated medical details. Never imply a real appointment was changed.""",
    },
    "medical_benefits_confirmation": {
        "title": "Healthcare Center Benefits Confirmation",
        "shortTitle": "Benefits Confirmation",
        "status": "Benefits line ready",
        "trustCue": "Healthcare Center benefits intake",
        "starter": "You've reached Healthcare Center benefits confirmation. I can collect insurance details for a verification record.",
        "toolGroups": {"demo-medical-benefits": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_capture_insurance", "demo_mark_benefits_status"],
        "prompt": """You are a Healthcare Center benefits confirmation assistant using seeded, non-production data.

Workflow:
1. Explain that you will collect insurance details for benefits verification.
2. Verify caller with name and passkey/keyphrase using demo_lookup_patient. If the caller says they are new, collect name and passkey, then use demo_register_patient to create a seeded demo account.
3. Ask for insurance provider, member ID, group number, subscriber name, subscriber DOB, and relationship to subscriber.
4. Use demo_capture_insurance as soon as required fields are known.
5. Use demo_mark_benefits_status with complete, pending_verification, or missing_info.

Style: calm, privacy-aware, concise. Never claim benefits were checked with a real payer.""",
    },
    "medical_discharge_followup": {
        "title": "Healthcare Center Discharge Follow-up",
        "shortTitle": "Discharge Agent",
        "status": "Discharge follow-up ready",
        "trustCue": "Healthcare Center post-visit follow-up",
        "starter": "This is Healthcare Center calling for a post-visit follow-up. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-discharge": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_get_discharge_followup", "demo_record_discharge_checkin", "demo_assess_call_risk", "demo_page_human_triage", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center discharge follow-up assistant using seeded, non-production data.

Workflow:
1. Explain this is a configurable 24/48/post-event follow-up call to check recovery and prevent avoidable readmission.
2. Verify caller with name and passkey/keyphrase using demo_lookup_patient, or register a new seeded caller with demo_register_patient if they say they are new.
3. Use demo_get_discharge_followup to read the seeded event and follow-up window.
4. Ask about worsening symptoms, medication access, follow-up appointment barriers, transportation, and understanding of discharge instructions.
5. Use demo_assess_call_risk after collecting symptoms/barriers.
6. If risk is high/critical or the caller reports red flags, use demo_page_human_triage immediately and say a nurse/human clinician should be engaged.
7. Use demo_record_discharge_checkin to record the outcome.

Medication questions: if the caller asks a general question like whether they can take a medication with something else and reports no urgent symptoms/red flags, do not page immediately. Record medium/needs-review risk and offer a clinician/pharmacist callback. Page only if there are urgent symptoms, allergic reaction, overdose concern, critical medication interruption, confusion, or severe distress.

Escape logic: page human triage for chest pain, shortness of breath, severe bleeding, new confusion, fainting, stroke-like symptoms, uncontrolled pain, fever with worsening condition, inability to obtain critical medications, allergic reaction/overdose concern, or any caller distress you cannot safely resolve. This is demo-only; do not provide diagnosis or emergency medical advice beyond directing urgent symptoms to emergency services/human triage.""",
    },
    "medical_rx_refill": {
        "title": "Healthcare Center Rx Refill Line",
        "shortTitle": "Rx Refill",
        "status": "Rx refill intake ready",
        "trustCue": "Healthcare Center prescription refill intake",
        "starter": "You've reached Healthcare Center prescription refill intake. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-rx": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_request_rx_refill", "demo_assess_call_risk", "demo_page_human_triage", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center prescription refill intake assistant using seeded, non-production data.

Workflow:
1. Verify caller with name and passkey/keyphrase using demo_lookup_patient, or register a new seeded caller with demo_register_patient if needed.
2. Collect medication name, dose if known, preferred pharmacy, remaining supply, and whether doses have already been missed.
3. Use demo_assess_call_risk if the caller reports missed critical medication, symptoms, confusion, or distress.
4. Use demo_request_rx_refill to record the refill request.
5. If there is urgent medication interruption, concerning symptoms, controlled-substance ambiguity, allergy/reaction, overdose concern, or immediate safety concern, use demo_page_human_triage.
6. For a general medication-compatibility question without symptoms or red flags, do not page immediately. Say you cannot give medication advice in the demo, record it as medium/needs-review, and offer a clinician/pharmacist callback using demo_add_callback_task.

Escape logic: page human triage for no supply of critical medication, missed doses with symptoms, adverse reaction/allergy, overdose concern, suicidal ideation, controlled-substance concerns, unclear medication identity with urgent need, or any urgent clinical question. Do not promise a real refill was approved.""",
    },
    "medical_general_care": {
        "title": "Healthcare Center General Care Line",
        "shortTitle": "General Care",
        "status": "General care line ready",
        "trustCue": "Healthcare Center care navigation",
        "starter": "You've reached Healthcare Center general care navigation. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-care": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_assess_call_risk", "demo_route_general_care", "demo_page_human_triage", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center general care navigation assistant using seeded, non-production data.

Workflow:
1. Verify caller with name and passkey/keyphrase using demo_lookup_patient, or register a new seeded caller with demo_register_patient if needed.
2. Ask one concise question to understand the reason for calling.
3. Use demo_assess_call_risk to classify risk level and risk factors from caller-reported transcript only.
4. Use demo_route_general_care to route low/medium risk calls to follow-up care, scheduling, refill line, benefits, or callback.
5. If risk is high/critical or the concern is urgent/unsafe, use demo_page_human_triage quickly.
6. If the caller asks a non-urgent medication-compatibility question, do not escalate straight to a page. Route to human_nurse_triage or callback as needs-review unless red flags are present.

Escape logic: do not attempt nurse triage. Page/engage human nurse triage for urgent symptoms, worsening condition, mental-health crisis, urgent medication safety concern, post-discharge deterioration, caller confusion, or uncertainty where immediate human judgment is needed. Non-urgent medication questions should become a callback/needs-review handoff, not an emergency page.""",
    },
    "medical_hypertension_checkup": {
        "title": "Healthcare Center Blood Pressure Check-in",
        "shortTitle": "Hypertension Checkup",
        "status": "Blood pressure check-in ready",
        "trustCue": "Healthcare Center hypertension outreach",
        "starter": "This is Healthcare Center calling for a blood pressure check-in. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-hypertension": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_record_blood_pressure", "demo_assess_call_risk", "demo_page_human_triage", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center hypertension outbound check-in assistant using seeded, non-production data.

Workflow:
1. Explain this is a blood pressure check-in call.
2. Verify caller with name and passkey/keyphrase using demo_lookup_patient, or register a new seeded caller with demo_register_patient if needed.
3. Ask whether they have a recent blood pressure reading. Collect systolic/top number, diastolic/bottom number, pulse if volunteered, reading time, and whether they had symptoms.
4. Use demo_record_blood_pressure once systolic and diastolic are known.
5. Use demo_assess_call_risk if the caller reports symptoms, very high/low readings, missed medications, confusion, or distress.
6. If the caller asks whether they can take medication with it, do not page immediately unless there are red-flag symptoms, a crisis-range reading, allergic reaction/overdose concern, confusion, or severe distress. Say you cannot give medication advice in the demo and offer a clinician/pharmacist callback.
7. Use demo_page_human_triage for urgent readings/symptoms or immediate safety concerns.

Escape logic: page human triage for chest pain, shortness of breath, severe headache, vision changes, neurological symptoms, fainting, confusion, systolic >= 180, diastolic >= 120, symptomatic low blood pressure, allergic reaction/overdose concern, or immediate medication safety concerns. Non-urgent medication compatibility questions are callback/needs-review, not instant page. Do not diagnose or adjust medication.""",
    },
    "medical_annual_wellness": {
        "title": "Healthcare Center Annual Wellness Reminder",
        "shortTitle": "Annual Wellness Visit",
        "status": "Annual wellness outreach ready",
        "trustCue": "Healthcare Center preventive care outreach",
        "starter": "This is Healthcare Center calling with an annual wellness visit reminder. To start, please tell me your name and passkey.",
        "toolGroups": {"demo-medical-wellness": True},
        "tools": ["demo_lookup_patient", "demo_register_patient", "demo_get_annual_wellness_offer", "demo_book_appointment", "demo_add_callback_task"],
        "prompt": """You are a Healthcare Center annual wellness visit outreach assistant using seeded, non-production data.

Workflow:
1. Explain that the patient's annual wellness visit is due and you can help schedule now.
2. Verify caller with name and passkey/keyphrase using demo_lookup_patient, or register a new seeded caller with demo_register_patient if needed.
3. Use demo_get_annual_wellness_offer.
4. Use this offer style: "Your last visit was on a Thursday morning at 8:00 AM. There is a Thursday at 8:00 AM available next week in Duluth. Would you like that appointment?"
5. If the caller accepts, use demo_book_appointment with the offered slot_id.
6. If they decline or need another time, use demo_add_callback_task or offer scheduling follow-up.

Style: concise, friendly preventive-care outreach. Never claim a real appointment was booked in a real medical system.""",
    },
    "service_desk": {
        "title": "Service Desk Incident & Request Intake",
        "shortTitle": "Service Desk",
        "status": "Service desk ready",
        "trustCue": "IT service desk intake",
        "starter": "You've reached the service desk intake line. I can collect an incident or service request and create a ticket summary.",
        "toolGroups": {"demo-service-desk": True},
        "tools": ["demo_get_service_desk_catalog", "demo_create_service_ticket"],
        "prompt": """You are a fictional IT service desk intake agent using seeded, non-production data.

Workflow:
1. Greet as service desk intake and ask whether the caller is reporting an incident or making a service request.
2. Incident = something broken/degraded. Request = access, equipment, software, information, or a standard fulfillment ask.
3. Collect caller name, callback/contact, affected service or system, short summary, details, impact, urgency, location/department if volunteered, and any troubleshooting already tried.
4. Use demo_get_service_desk_catalog if you need category examples or priority guidance.
5. Use demo_create_service_ticket once you have enough to create a useful intake record. If some fields are unknown, use "not provided" rather than repeatedly interrogating the caller.
6. Read back the ticket number, classification, priority, and next step.

Priority guidance: critical = widespread outage or safety/business-critical work stopped; high = one team or VIP/blocking issue; medium = single user impaired with workaround or normal request; low = informational/minor request.

Style: concise, calm, practical service desk agent. Never claim a real production ITSM ticket was created; this is a demo intake record.""",
    },
    "dlp_posture_consultant": {
        "title": "DLP Posture Consultant",
        "shortTitle": "DLP Posture Consultant",
        "status": "Discovery interview ready",
        "trustCue": "Enterprise DLP planning and discovery",
        "starter": "I'm your DLP posture consultant for enterprise planning and discovery. First question: what area of the business are you from?",
        "toolGroups": {"demo-dlp-discovery": True},
        "tools": ["demo_record_dlp_discovery"],
        "prompt": """You are a DLP Posture Consultant running an ethnographic discovery interview for enterprise DLP planning. Your job is to understand how work actually happens before recommending controls.

Opening:
1. Start with this as the first question, before any other discovery question: "What area of the business are you from?"
2. After they answer, tailor all follow-up questions to that business area and their actual work context.

Interview approach:
- Use ethnographic interviewing: ask about real workflows, handoffs, documents, systems, exceptions, incentives, and workarounds.
- Ask one question at a time. Prefer concrete examples over abstract policy answers.
- Listen for where sensitive data is created, copied, transformed, exported, shared, stored locally, pasted into tools, emailed, uploaded, printed, or discussed.
- Distinguish official process from what people actually do under deadline pressure.
- Do not interrogate or shame the caller. Frame DLP as protecting work, patients/customers, and the organization without blocking legitimate business.

Tailoring by business area:
- Clinical / operations: patient/customer-facing workflows, scheduling, referrals, care coordination, reports, after-hours work, fax/email, and exception handling.
- Finance / revenue cycle: claims, remittance, spreadsheets, payment data, vendor portals, month-end work, and external file exchange.
- HR / legal / compliance: employee records, investigations, contracts, policy evidence, retention, privileged material, and need-to-know sharing.
- Sales / account teams: prospect/customer lists, proposals, pricing, contracts, presentations, CRM exports, and travel/mobile sharing.
- Engineering / analytics / IT: production data pulls, logs, tickets, databases, SaaS admins, cloud storage, AI tools, and test data.
- Executives / leadership: board materials, strategy, M&A, performance data, travel devices, delegated inbox/calendar access, and assistant workflows.
- If the area is something else, infer the likely data flows and ask tailored questions without pretending certainty.

Minimum discovery arc:
1. Business area and role context.
2. A recent real example of work involving sensitive data.
3. Source systems and destinations.
4. Collaboration channels and external parties.
5. Local/offline/mobile work patterns.
6. AI, automation, copy/paste, screenshots, exports, and shadow tools.
7. Deadline exceptions and workarounds.
8. Current controls that help or frustrate the work.
9. What would break if DLP became too restrictive.
10. Risk signals and candidate policy/control ideas.

Output behavior:
- Periodically summarize what you heard as observed workflows, sensitive-data touchpoints, likely leakage paths, control friction, and open questions.
- When enough context is gathered, use demo_record_dlp_discovery with business_area, role_context, workflows, sensitive_data, channels, shadow_tools, pain_points, risk_signals, and recommended_next_questions.
- Do not claim you performed a full compliance assessment. This is a discovery interview for planning.

Style: consultative, curious, practical, and concise. Sound like a senior enterprise security advisor who understands that workflow reality matters more than policy theater.""",
    },

}

DEMO_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "demo_lookup_patient",
        "description": "Look up a seeded patient by caller name and passkey/keyphrase only.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "keyphrase": {"type": "string", "description": "Caller passkey/keyphrase."}, "phone": {"type": "string"}, "dob": {"type": "string"}}, "required": ["name", "keyphrase"]},
    },
    {
        "type": "function",
        "name": "demo_register_patient",
        "description": "Create or update a seeded demo patient account verbally using caller-provided name and passkey/keyphrase. This is demo-only and not real registration.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "keyphrase": {"type": "string", "description": "Caller passkey/keyphrase."}, "phone": {"type": "string"}, "dob": {"type": "string"}, "city": {"type": "string"}, "preferred_facility": {"type": "string"}}, "required": ["name", "keyphrase"]},
    },
    {
        "type": "function",
        "name": "demo_compare_facility_options",
        "description": "Compare the seeded patient's preferred Duluth facility option against the soonest nearby facility option using city-level data only.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "appointment_type": {"type": "string"}}, "required": ["patient_id"]},
    },
    {
        "type": "function",
        "name": "demo_list_open_slots",
        "description": "List open appointment slots for a seeded patient and appointment need.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "appointment_type": {"type": "string"}, "location": {"type": "string"}, "time_preference": {"type": "string"}}, "required": ["patient_id"]},
    },
    {
        "type": "function",
        "name": "demo_book_appointment",
        "description": "Book a appointment slot for a seeded patient.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "slot_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["patient_id", "slot_id"]},
    },
    {
        "type": "function",
        "name": "demo_add_callback_task",
        "description": "Create a scheduling callback task.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "reason": {"type": "string"}, "preferred_callback_time": {"type": "string"}}, "required": ["patient_id", "reason"]},
    },
    {
        "type": "function",
        "name": "demo_verify_and_get_next_appointment",
        "description": "Verify a seeded patient by caller name and passkey/keyphrase, then return the next appointment in one call.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "keyphrase": {"type": "string", "description": "Caller passkey/keyphrase."}, "phone": {"type": "string"}, "dob": {"type": "string"}}, "required": ["name", "keyphrase"]},
    },
    {
        "type": "function",
        "name": "demo_get_next_appointment",
        "description": "Get the next appointment for a seeded patient.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}}, "required": ["patient_id"]},
    },
    {
        "type": "function",
        "name": "demo_confirm_appointment",
        "description": "Confirm a appointment reminder.",
        "parameters": {"type": "object", "properties": {"appointment_id": {"type": "integer"}, "confirmed_by": {"type": "string"}}, "required": ["appointment_id"]},
    },
    {
        "type": "function",
        "name": "demo_request_appointment_change",
        "description": "Record a request to reschedule or cancel an appointment.",
        "parameters": {"type": "object", "properties": {"appointment_id": {"type": "integer"}, "change_type": {"type": "string", "enum": ["reschedule", "cancel"]}, "reason": {"type": "string"}}, "required": ["appointment_id", "change_type"]},
    },
    {
        "type": "function",
        "name": "demo_capture_insurance",
        "description": "Capture insurance information for a benefits verification workflow.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "provider": {"type": "string"}, "member_id": {"type": "string"}, "group_number": {"type": "string"}, "subscriber_name": {"type": "string"}, "subscriber_dob": {"type": "string"}, "relationship": {"type": "string"}}, "required": ["patient_id", "provider", "member_id", "group_number"]},
    },
    {
        "type": "function",
        "name": "demo_mark_benefits_status",
        "description": "Mark benefits verification status.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "status": {"type": "string", "enum": ["complete", "pending_verification", "missing_info"]}, "note": {"type": "string"}}, "required": ["patient_id", "status"]},
    },
    {
        "type": "function",
        "name": "demo_get_discharge_followup",
        "description": "Return seeded post-discharge follow-up context and configurable follow-up window.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "hours_post_event": {"type": "integer", "description": "Post-event follow-up window such as 24, 48, or configurable hours."}}, "required": ["patient_id"]},
    },
    {
        "type": "function",
        "name": "demo_record_discharge_checkin",
        "description": "Record a seeded discharge follow-up check-in outcome.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "hours_post_event": {"type": "integer"}, "symptoms": {"type": "string"}, "medication_access": {"type": "string"}, "followup_barriers": {"type": "string"}, "outcome": {"type": "string"}}, "required": ["patient_id", "outcome"]},
    },
    {
        "type": "function",
        "name": "demo_request_rx_refill",
        "description": "Record a seeded prescription refill request.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "medication": {"type": "string"}, "dose": {"type": "string"}, "pharmacy": {"type": "string"}, "remaining_supply": {"type": "string"}, "missed_doses": {"type": "string"}}, "required": ["patient_id", "medication"]},
    },
    {
        "type": "function",
        "name": "demo_route_general_care",
        "description": "Route a general care call to follow-up care, scheduling, Rx refill, benefits, callback, or human nurse triage.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "reason": {"type": "string"}, "recommended_route": {"type": "string", "enum": ["follow_up_care", "scheduling", "rx_refill", "benefits", "callback", "human_nurse_triage"]}, "notes": {"type": "string"}}, "required": ["patient_id", "reason", "recommended_route"]},
    },
    {
        "type": "function",
        "name": "demo_assess_call_risk",
        "description": "Record realtime call risk level, caller-reported risk factors, and escape logic. Use only caller transcript, not seeded supplemental data, for reason/risk factors.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "workflow": {"type": "string"}, "concern": {"type": "string"}, "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "risk_factors": {"type": "array", "items": {"type": "string"}}, "escape_logic": {"type": "string"}, "human_required": {"type": "boolean"}}, "required": ["workflow", "concern", "risk_level"]},
    },
    {
        "type": "function",
        "name": "demo_page_human_triage",
        "description": "Record that a human nurse/clinician must be paged or engaged for the demo call.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "workflow": {"type": "string"}, "reason": {"type": "string"}, "risk_level": {"type": "string", "enum": ["medium", "high", "critical"]}, "urgency": {"type": "string", "enum": ["routine", "same_day", "urgent", "emergency"]}}, "required": ["workflow", "reason", "risk_level"]},
    },
    {
        "type": "function",
        "name": "demo_record_blood_pressure",
        "description": "Record a seeded blood pressure reading from an outbound hypertension check-in.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}, "systolic": {"type": "integer"}, "diastolic": {"type": "integer"}, "pulse": {"type": "integer"}, "reading_time": {"type": "string"}, "symptoms": {"type": "string"}, "medication_adherence": {"type": "string"}}, "required": ["patient_id", "systolic", "diastolic"]},
    },
    {
        "type": "function",
        "name": "demo_get_annual_wellness_offer",
        "description": "Return a seeded annual wellness visit due reminder and a matching Thursday 8:00 AM Duluth appointment offer.",
        "parameters": {"type": "object", "properties": {"patient_id": {"type": "integer"}}, "required": ["patient_id"]},
    },
    {
        "type": "function",
        "name": "demo_get_service_desk_catalog",
        "description": "Return fictional service desk categories, request examples, and priority guidance for intake.",
        "parameters": {"type": "object", "properties": {"need": {"type": "string", "description": "Caller need or affected area, if known."}}},
    },
    {
        "type": "function",
        "name": "demo_create_service_ticket",
        "description": "Create a fictional service desk intake ticket for an incident or service request.",
        "parameters": {"type": "object", "properties": {"caller_name": {"type": "string"}, "ticket_type": {"type": "string", "enum": ["incident", "request"]}, "summary": {"type": "string"}, "description": {"type": "string"}, "affected_service": {"type": "string"}, "impact": {"type": "string"}, "urgency": {"type": "string"}, "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]}, "contact": {"type": "string"}, "location": {"type": "string"}, "category": {"type": "string"}, "troubleshooting": {"type": "string"}}, "required": ["caller_name", "ticket_type", "summary", "description"]},
    },
    {
        "type": "function",
        "name": "demo_record_dlp_discovery",
        "description": "Record a DLP posture ethnographic discovery summary for enterprise planning.",
        "parameters": {"type": "object", "properties": {"business_area": {"type": "string"}, "role_context": {"type": "string"}, "workflows": {"type": "array", "items": {"type": "string"}}, "sensitive_data": {"type": "array", "items": {"type": "string"}}, "channels": {"type": "array", "items": {"type": "string"}}, "shadow_tools": {"type": "array", "items": {"type": "string"}}, "pain_points": {"type": "array", "items": {"type": "string"}}, "risk_signals": {"type": "array", "items": {"type": "string"}}, "recommended_next_questions": {"type": "array", "items": {"type": "string"}}, "summary": {"type": "string"}}, "required": ["business_area", "summary"]},
    },
]


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_demo_db(reset: bool = False) -> None:
    with _conn() as con:
        cur = con.cursor()
        if reset:
            cur.executescript("""
            DROP TABLE IF EXISTS demo_interactions;
            DROP TABLE IF EXISTS demo_service_tickets;
            DROP TABLE IF EXISTS demo_insurance;
            DROP TABLE IF EXISTS demo_appointments;
            DROP TABLE IF EXISTS demo_patients;
            """)
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS demo_patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            dob TEXT NOT NULL,
            keyphrase TEXT NOT NULL,
            preferred_location TEXT,
            preferred_facility TEXT,
            city TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS demo_appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            starts_at TEXT NOT NULL,
            appointment_type TEXT NOT NULL,
            provider TEXT NOT NULL,
            location TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT DEFAULT '',
            FOREIGN KEY(patient_id) REFERENCES demo_patients(id)
        );
        CREATE TABLE IF NOT EXISTS demo_insurance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            provider TEXT,
            member_id TEXT,
            group_number TEXT,
            subscriber_name TEXT,
            subscriber_dob TEXT,
            relationship TEXT,
            status TEXT NOT NULL DEFAULT 'missing_info',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(patient_id) REFERENCES demo_patients(id)
        );
        CREATE TABLE IF NOT EXISTS demo_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            demo_type TEXT NOT NULL,
            patient_id INTEGER,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            outcome TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS demo_service_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ticket_type TEXT NOT NULL,
            caller_name TEXT NOT NULL,
            contact TEXT,
            summary TEXT NOT NULL,
            description TEXT NOT NULL,
            affected_service TEXT,
            category TEXT,
            impact TEXT,
            urgency TEXT,
            priority TEXT NOT NULL,
            location TEXT,
            troubleshooting TEXT,
            status TEXT NOT NULL DEFAULT 'new'
        );
        CREATE TABLE IF NOT EXISTS demo_risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            workflow TEXT NOT NULL,
            patient_id INTEGER,
            risk_level TEXT NOT NULL,
            risk_factors_json TEXT NOT NULL,
            concern TEXT NOT NULL,
            escape_logic TEXT,
            human_required INTEGER NOT NULL DEFAULT 0,
            escalation_status TEXT NOT NULL DEFAULT 'watch'
        );
        CREATE TABLE IF NOT EXISTS demo_escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            workflow TEXT NOT NULL,
            patient_id INTEGER,
            risk_level TEXT NOT NULL,
            urgency TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'paged'
        );
        """)
        existing_cols = {r["name"] for r in cur.execute("PRAGMA table_info(demo_patients)").fetchall()}
        if "preferred_facility" not in existing_cols:
            cur.execute("ALTER TABLE demo_patients ADD COLUMN preferred_facility TEXT")
        if "city" not in existing_cols:
            cur.execute("ALTER TABLE demo_patients ADD COLUMN city TEXT")
        cur.execute("UPDATE demo_patients SET preferred_facility=COALESCE(preferred_facility, preferred_location), city=COALESCE(city, 'Duluth') WHERE preferred_facility IS NULL OR city IS NULL")
        # Keep long-lived seed stores aligned with the current seed story.
        cur.execute("UPDATE demo_patients SET city='Duluth', preferred_location='Duluth Specialty Center', preferred_facility='Duluth Specialty Center' WHERE phone='555-0101'")
        cur.execute("UPDATE demo_patients SET city='Superior', preferred_location='Duluth Specialty Center', preferred_facility='Duluth Specialty Center' WHERE phone='555-0112'")
        cur.execute("UPDATE demo_patients SET city='Hermantown', preferred_location='Duluth Specialty Center', preferred_facility='Duluth Specialty Center' WHERE phone='555-0144'")
        count = cur.execute("SELECT COUNT(*) AS c FROM demo_patients").fetchone()["c"]
        if count == 0:
            now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            patients = [
                ("Avery Morgan", "555-0101", "1984-04-12", "bluebird", "Duluth", "Duluth Specialty Center", now),
                ("Jordan Lee", "555-0112", "1976-11-03", "riverstone", "Superior", "Duluth Specialty Center", now),
                ("Taylor Quinn", "555-0144", "1992-07-28", "sunflower", "Hermantown", "Duluth Specialty Center", now),
            ]
            cur.executemany("INSERT INTO demo_patients(name, phone, dob, keyphrase, city, preferred_location, preferred_facility, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(n, p, d, k, c, f, f, t) for (n, p, d, k, c, f, t) in patients])
            base = datetime.now() + timedelta(days=3)
            appts = [
                (1, (base.replace(hour=9, minute=30, second=0, microsecond=0)).isoformat(), "Primary care follow-up", "Dr. Patel", "Duluth Specialty Center", "scheduled", "Arrive 15 minutes early."),
                (2, (base.replace(day=base.day+1, hour=14, minute=0, second=0, microsecond=0)).isoformat(), "Lab review", "Nurse Team", "East Clinic", "scheduled", "Bring medication list."),
                (3, (base.replace(day=base.day+2, hour=10, minute=15, second=0, microsecond=0)).isoformat(), "Virtual intake", "Care Coordinator", "Virtual Care", "scheduled", "Video link sent by text."),
            ]
            cur.executemany("INSERT INTO demo_appointments(patient_id, starts_at, appointment_type, provider, location, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)", appts)
            cur.executemany("INSERT INTO demo_insurance(patient_id, provider, member_id, group_number, subscriber_name, subscriber_dob, relationship, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                (1, "North Star Health Plan", "NS-102938", "GRP-410", "Avery Morgan", "1984-04-12", "self", "pending_verification", now),
                (2, "PrairieCare Choice", "PC-778899", "GRP-205", "Jordan Lee", "1976-11-03", "self", "complete", now),
                (3, "", "", "", "", "", "", "missing_info", now),
            ])
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        jimmy = cur.execute("SELECT id FROM demo_patients WHERE phone=?", ("7551493",)).fetchone()
        if jimmy:
            jimmy_id = jimmy["id"]
            cur.execute("""
                UPDATE demo_patients
                SET name=?, dob=?, keyphrase=?, city=?, preferred_location=?, preferred_facility=?
                WHERE id=?
            """, ("Jimmy Hanson", "1986-02-03", "mailbox", "Duluth", "Duluth Specialty Center", "Duluth Specialty Center", jimmy_id))
        else:
            cur.execute("""
                INSERT INTO demo_patients(name, phone, dob, keyphrase, city, preferred_location, preferred_facility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("Jimmy Hanson", "7551493", "1986-02-03", "mailbox", "Duluth", "Duluth Specialty Center", "Duluth Specialty Center", now))
            jimmy_id = cur.lastrowid
        jimmy_appt = cur.execute("SELECT id FROM demo_appointments WHERE patient_id=? AND notes LIKE '%Jimmy seeded appointment%'", (jimmy_id,)).fetchone()
        jimmy_appt_start = (datetime.now() + timedelta(days=4)).replace(hour=13, minute=30, second=0, microsecond=0).isoformat()
        if jimmy_appt:
            cur.execute("""
                UPDATE demo_appointments
                SET starts_at=?, appointment_type=?, provider=?, location=?, status=?, notes=?
                WHERE id=?
            """, (jimmy_appt_start, "Primary care check-in", "Dr. Crusher", "Duluth Specialty Center", "scheduled", "Jimmy seeded appointment. Bring medication list and insurance card.", jimmy_appt["id"]))
        else:
            cur.execute("""
                INSERT INTO demo_appointments(patient_id, starts_at, appointment_type, provider, location, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (jimmy_id, jimmy_appt_start, "Primary care check-in", "Dr. Crusher", "Duluth Specialty Center", "scheduled", "Jimmy seeded appointment. Bring medication list and insurance card."))
        jimmy_ins = cur.execute("SELECT id FROM demo_insurance WHERE patient_id=?", (jimmy_id,)).fetchone()
        jimmy_ins_values = ("Federation Health Plan", "JH-7551493", "GRP-1701-D", "Jimmy Hanson", "1986-02-03", "self", "complete", now, jimmy_id)
        if jimmy_ins:
            cur.execute("""
                UPDATE demo_insurance
                SET provider=?, member_id=?, group_number=?, subscriber_name=?, subscriber_dob=?, relationship=?, status=?, updated_at=?
                WHERE patient_id=?
            """, jimmy_ins_values)
        else:
            cur.execute("""
                INSERT INTO demo_insurance(provider, member_id, group_number, subscriber_name, subscriber_dob, relationship, status, updated_at, patient_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, jimmy_ins_values)
        con.commit()


def _norm_phone(phone: str) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def _row_dict(row):
    return dict(row) if row else None


def record_interaction(demo_type: str, action: str, payload: dict, outcome: str, patient_id=None) -> None:
    init_demo_db()
    with _conn() as con:
        con.execute(
            "INSERT INTO demo_interactions(ts, demo_type, patient_id, action, payload_json, outcome) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(timespec="seconds") + "Z", demo_type, patient_id, action, json.dumps(payload or {}, sort_keys=True), outcome),
        )
        con.commit()


def demo_lookup_patient(name: str = "", keyphrase: str = "", phone: str = "", dob: str = ""):
    init_demo_db()
    key = str(keyphrase or "").strip().lower()
    name_norm = " ".join(str(name or "").strip().lower().split())
    with _conn() as con:
        rows = con.execute("SELECT * FROM demo_patients").fetchall()
        for row in rows:
            row_name = " ".join(str(row["name"] or "").strip().lower().split())
            if row_name == name_norm and row["keyphrase"].lower() == key:
                patient = _row_dict(row)
                record_interaction("lookup", "demo_lookup_patient", {"name": patient["name"], "method": "name_keyphrase"}, "matched", patient["id"])
                return {"matched": True, "patient": {"id": patient["id"], "name": patient["name"], "city": patient.get("city") or "Duluth", "preferred_facility": patient.get("preferred_facility") or patient["preferred_location"], "preferred_location": patient["preferred_location"]}}
    record_interaction("lookup", "demo_lookup_patient", {"name": name_norm, "method": "name_keyphrase"}, "not_found")
    return {"matched": False, "message": "No seeded patient matched that name and passkey."}


def demo_register_patient(name: str, keyphrase: str, phone: str = "", dob: str = "", city: str = "", preferred_facility: str = ""):
    init_demo_db()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    clean_name = " ".join(str(name or "").strip().split())
    clean_key = str(keyphrase or "").strip()
    if not clean_name or not clean_key:
        return {"registered": False, "message": "Name and passkey are required to create a demo patient account."}
    phone_norm = _norm_phone(phone) or f"demo-{abs(hash((clean_name.lower(), clean_key.lower()))) % 1000000:06d}"
    clean_dob = str(dob or "").strip() or "demo-not-collected"
    clean_city = str(city or "").strip() or "Duluth"
    facility = str(preferred_facility or "").strip() or "Duluth Specialty Center"
    name_norm = " ".join(clean_name.lower().split())
    with _conn() as con:
        rows = con.execute("SELECT * FROM demo_patients").fetchall()
        existing = None
        for row in rows:
            row_name = " ".join(str(row["name"] or "").strip().lower().split())
            if row_name == name_norm:
                existing = row
                break
        if existing:
            patient_id = existing["id"]
            con.execute("""
                UPDATE demo_patients
                SET phone=?, dob=?, keyphrase=?, city=?, preferred_location=?, preferred_facility=?
                WHERE id=?
            """, (phone_norm, clean_dob, clean_key, clean_city, facility, facility, patient_id))
            outcome = "updated"
        else:
            cur = con.execute("""
                INSERT INTO demo_patients(name, phone, dob, keyphrase, city, preferred_location, preferred_facility, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_name, phone_norm, clean_dob, clean_key, clean_city, facility, facility, now))
            patient_id = cur.lastrowid
            outcome = "registered"
        con.commit()
    record_interaction("registration", "demo_register_patient", {"name": clean_name, "city": clean_city, "preferred_facility": facility}, outcome, patient_id)
    return {"registered": True, "outcome": outcome, "patient": {"id": patient_id, "name": clean_name, "city": clean_city, "preferred_facility": facility, "preferred_location": facility}, "message": f"Demo patient account {outcome} for {clean_name}."}


def _patient_context(patient_id: int) -> dict:
    init_demo_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM demo_patients WHERE id=?", (patient_id,)).fetchone()
    patient = _row_dict(row) or {}
    return {
        "id": patient_id,
        "name": patient.get("name", "Demo patient"),
        "city": patient.get("city") or "Duluth",
        "preferred_facility": patient.get("preferred_facility") or patient.get("preferred_location") or "Duluth Specialty Center",
    }


DEMO_NEARBY_FACILITY_BY_CITY = {
    "Duluth": {"facility": "Hermantown Clinic", "city": "Hermantown", "drive_hint": "near Duluth"},
    "Superior": {"facility": "Superior Clinic", "city": "Superior", "drive_hint": "closest to Superior"},
    "Hermantown": {"facility": "Hermantown Clinic", "city": "Hermantown", "drive_hint": "closest to Hermantown"},
}


def _scheduler_slots(patient_id: int, appointment_type: str = "Primary care"):
    patient = _patient_context(patient_id)
    now = datetime.now()
    nearby = DEMO_NEARBY_FACILITY_BY_CITY.get(patient["city"], DEMO_NEARBY_FACILITY_BY_CITY["Duluth"])
    sooner_dt = (now + timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
    preferred_dt = (now + timedelta(days=6)).replace(hour=10, minute=30, second=0, microsecond=0)
    days_until_thursday = (3 - now.weekday()) % 7 or 7
    wellness_dt = (now + timedelta(days=days_until_thursday)).replace(hour=8, minute=0, second=0, microsecond=0)
    appt_type = appointment_type or "Primary care"
    slots = [
        {
            "slot_id": f"SOONER-{patient_id}-1",
            "option_type": "sooner_nearby",
            "starts_at": sooner_dt.isoformat(),
            "appointment_type": appt_type,
            "provider": "Nurse Practitioner Vale",
            "location": nearby["facility"],
            "city": nearby["city"],
            "drive_hint": nearby["drive_hint"],
        },
        {
            "slot_id": f"PREFERRED-{patient_id}-1",
            "option_type": "preferred_facility",
            "starts_at": preferred_dt.isoformat(),
            "appointment_type": appt_type,
            "provider": "Dr. Patel",
            "location": patient["preferred_facility"],
            "city": "Duluth",
            "drive_hint": "preferred facility in Duluth",
        },
    ]
    if "wellness" in appt_type.lower() or "annual" in appt_type.lower():
        slots.insert(0, {
            "slot_id": f"AWV-{patient_id}-THU-0800",
            "option_type": "annual_wellness_match",
            "starts_at": wellness_dt.isoformat(),
            "appointment_type": "Annual wellness visit",
            "provider": "Dr. Patel",
            "location": "Duluth Specialty Center",
            "city": "Duluth",
            "drive_hint": "matches prior Thursday morning pattern",
        })
    return slots


def demo_compare_facility_options(patient_id: int, appointment_type: str = "Primary care"):
    patient = _patient_context(patient_id)
    slots = _scheduler_slots(patient_id, appointment_type)
    sooner = next(s for s in slots if s["option_type"] == "sooner_nearby")
    preferred = next(s for s in slots if s["option_type"] == "preferred_facility")
    question = (
        f"I can either get you in at your preferred facility in Duluth, {preferred['location']}, "
        f"on {preferred['starts_at']}, or sooner at our {sooner['location']} location "
        f"on {sooner['starts_at']}. Which would you prefer?"
    )
    record_interaction("medical_scheduler", "demo_compare_facility_options", {"patient_id": patient_id, "appointment_type": appointment_type}, "returned_preferred_vs_sooner", patient_id)
    return {"patient": patient, "preferred_option": preferred, "sooner_option": sooner, "slots": slots, "suggested_question": question, "note": "Use city/facility names only; no addresses."}


def demo_list_open_slots(patient_id: int, appointment_type: str = "Primary care", location: str = "", time_preference: str = ""):
    init_demo_db()
    slots = _scheduler_slots(patient_id, appointment_type)
    if location:
        slots = [s for s in slots if location.lower() in s["location"].lower() or location.lower() in s.get("city", "").lower()] or slots
    record_interaction("medical_scheduler", "demo_list_open_slots", {"patient_id": patient_id, "appointment_type": appointment_type, "location": location, "time_preference": time_preference}, "returned_slots", patient_id)
    return {"slots": slots, "note": "Open slots returned. Preferred Duluth option and sooner nearby option are included when available."}


def demo_book_appointment(patient_id: int, slot_id: str, reason: str = ""):
    init_demo_db()
    slots = _scheduler_slots(patient_id, reason or "Primary care")
    slot = next((s for s in slots if s["slot_id"] == slot_id), None)
    if not slot:
        return "No seeded slot was available to book. Ask the caller whether they prefer the Duluth preferred facility or the sooner nearby option."
    with _conn() as con:
        cur = con.execute("INSERT INTO demo_appointments(patient_id, starts_at, appointment_type, provider, location, status, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (patient_id, slot["starts_at"], slot["appointment_type"], slot["provider"], slot["location"], "demo_booked", reason or "Booked by scheduler demo"))
        appt_id = cur.lastrowid
        con.commit()
    record_interaction("medical_scheduler", "demo_book_appointment", {"slot_id": slot_id, "reason": reason}, "booked", patient_id)
    return f"Appointment summary ready: appointment_id {appt_id}, {slot['appointment_type']} with {slot['provider']} at {slot['location']} on {slot['starts_at']}."


def demo_add_callback_task(patient_id: int, reason: str, preferred_callback_time: str = ""):
    record_interaction("medical_scheduler", "demo_add_callback_task", {"reason": reason, "preferred_callback_time": preferred_callback_time}, "callback_task_created", patient_id)
    return "Callback task created for the Healthcare Center scheduling team."


def demo_verify_and_get_next_appointment(name: str = "", keyphrase: str = "", phone: str = "", dob: str = ""):
    lookup = demo_lookup_patient(name=name, keyphrase=keyphrase, phone=phone, dob=dob)
    if not lookup.get("matched"):
        record_interaction("medical_appt_reminder", "demo_verify_and_get_next_appointment", {"matched": False}, "not_verified")
        return {"matched": False, "message": lookup.get("message", "No seeded patient matched those details.")}
    patient = lookup["patient"]
    appt = demo_get_next_appointment(patient["id"])
    record_interaction("medical_appt_reminder", "demo_verify_and_get_next_appointment", {"matched": True, "patient_id": patient["id"]}, "verified_with_next", patient["id"])
    return {
        "matched": True,
        "verified_message": f"Thank you, you're verified as {patient['name']}.",
        "patient": patient,
        "next_appointment": appt.get("appointment"),
        "message": "Verified seeded patient and returned the next appointment.",
    }


def demo_get_next_appointment(patient_id: int):
    init_demo_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM demo_appointments WHERE patient_id=? AND status NOT IN ('cancel_requested') ORDER BY starts_at ASC LIMIT 1", (patient_id,)).fetchone()
    if not row:
        record_interaction("medical_appt_reminder", "demo_get_next_appointment", {"patient_id": patient_id}, "none", patient_id)
        return {"appointment": None, "message": "No seeded upcoming appointment found."}
    appt = _row_dict(row)
    record_interaction("medical_appt_reminder", "demo_get_next_appointment", {"patient_id": patient_id}, "returned_next", patient_id)
    return {"appointment": appt}


def demo_confirm_appointment(appointment_id: int, confirmed_by: str = "caller"):
    init_demo_db()
    with _conn() as con:
        con.execute("UPDATE demo_appointments SET status='confirmed' WHERE id=?", (appointment_id,))
        row = con.execute("SELECT patient_id FROM demo_appointments WHERE id=?", (appointment_id,)).fetchone()
        con.commit()
    patient_id = row["patient_id"] if row else None
    record_interaction("medical_appt_reminder", "demo_confirm_appointment", {"appointment_id": appointment_id, "confirmed_by": confirmed_by}, "confirmed", patient_id)
    return "Appointment confirmation recorded."


def demo_request_appointment_change(appointment_id: int, change_type: str, reason: str = ""):
    init_demo_db()
    status = "reschedule_requested" if change_type == "reschedule" else "cancel_requested"
    with _conn() as con:
        con.execute("UPDATE demo_appointments SET status=?, notes=? WHERE id=?", (status, reason, appointment_id))
        row = con.execute("SELECT patient_id FROM demo_appointments WHERE id=?", (appointment_id,)).fetchone()
        con.commit()
    patient_id = row["patient_id"] if row else None
    record_interaction("medical_appt_reminder", "demo_request_appointment_change", {"appointment_id": appointment_id, "change_type": change_type, "reason": reason}, status, patient_id)
    return f"{change_type.title()} request recorded."


def demo_capture_insurance(patient_id: int, provider: str, member_id: str, group_number: str, subscriber_name: str = "", subscriber_dob: str = "", relationship: str = ""):
    init_demo_db()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _conn() as con:
        existing = con.execute("SELECT id FROM demo_insurance WHERE patient_id=?", (patient_id,)).fetchone()
        values = (provider, member_id, group_number, subscriber_name, subscriber_dob, relationship, "pending_verification", now, patient_id)
        if existing:
            con.execute("UPDATE demo_insurance SET provider=?, member_id=?, group_number=?, subscriber_name=?, subscriber_dob=?, relationship=?, status=?, updated_at=? WHERE patient_id=?", values)
        else:
            con.execute("INSERT INTO demo_insurance(provider, member_id, group_number, subscriber_name, subscriber_dob, relationship, status, updated_at, patient_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
        con.commit()
    record_interaction("medical_benefits_confirmation", "demo_capture_insurance", {"provider": provider, "member_id_last4": str(member_id)[-4:], "group_number": group_number, "relationship": relationship}, "captured", patient_id)
    return "Insurance information captured for benefits verification."


def demo_mark_benefits_status(patient_id: int, status: str, note: str = ""):
    init_demo_db()
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _conn() as con:
        con.execute("UPDATE demo_insurance SET status=?, updated_at=? WHERE patient_id=?", (status, now, patient_id))
        con.commit()
    record_interaction("medical_benefits_confirmation", "demo_mark_benefits_status", {"status": status, "note": note}, status, patient_id)
    return f"Benefits status marked as {status}."


def demo_get_discharge_followup(patient_id: int, hours_post_event: int = 48):
    init_demo_db()
    patient = _patient_context(patient_id)
    hours = int(hours_post_event or 48)
    event_time = (datetime.now() - timedelta(hours=hours)).replace(second=0, microsecond=0)
    followup = {
        "patient": patient,
        "event": "Seeded outpatient visit discharge",
        "event_time": event_time.isoformat(),
        "hours_post_event": hours,
        "quality_checks": ["symptoms worse or new", "medications obtained", "follow-up scheduled", "transportation/barriers", "understands discharge instructions"],
        "red_flags": ["chest pain", "shortness of breath", "severe bleeding", "new confusion", "fainting", "stroke-like symptoms", "uncontrolled pain"],
    }
    record_interaction("medical_discharge_followup", "demo_get_discharge_followup", {"hours_post_event": hours}, "returned_followup_context", patient_id)
    return followup


def demo_record_discharge_checkin(patient_id: int, outcome: str, hours_post_event: int = 48, symptoms: str = "", medication_access: str = "", followup_barriers: str = ""):
    payload = {"hours_post_event": hours_post_event, "symptoms": symptoms, "medication_access": medication_access, "followup_barriers": followup_barriers, "outcome": outcome}
    record_interaction("medical_discharge_followup", "demo_record_discharge_checkin", payload, outcome or "recorded", patient_id)
    return {"recorded": True, "message": "Discharge follow-up check-in recorded for the demo.", "outcome": outcome}


def demo_request_rx_refill(patient_id: int, medication: str, dose: str = "", pharmacy: str = "", remaining_supply: str = "", missed_doses: str = ""):
    payload = {"medication": medication, "dose": dose, "pharmacy": pharmacy, "remaining_supply": remaining_supply, "missed_doses": missed_doses}
    risk_hint = "needs_review" if any(str(v).strip() for v in [missed_doses]) else "refill_intake_recorded"
    record_interaction("medical_rx_refill", "demo_request_rx_refill", payload, risk_hint, patient_id)
    return {"recorded": True, "status": risk_hint, "message": "Rx refill intake recorded for clinician/pharmacy review in this demo."}


def demo_route_general_care(patient_id: int, reason: str, recommended_route: str, notes: str = ""):
    payload = {"reason": reason, "recommended_route": recommended_route, "notes": notes}
    record_interaction("medical_general_care", "demo_route_general_care", payload, recommended_route, patient_id)
    return {"routed": True, "recommended_route": recommended_route, "message": f"General care call routed to {recommended_route}."}


def demo_assess_call_risk(workflow: str, concern: str, risk_level: str, patient_id: int | None = None, risk_factors=None, escape_logic: str = "", human_required: bool = False):
    init_demo_db()
    level = str(risk_level or "low").lower()
    if level not in {"low", "medium", "high", "critical"}:
        level = "medium"
    factors = risk_factors if isinstance(risk_factors, list) else ([risk_factors] if risk_factors else [])
    auto_human = human_required or level in {"high", "critical"}
    status = "human_required" if auto_human else ("watch" if level == "medium" else "low")
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO demo_risk_events(ts, workflow, patient_id, risk_level, risk_factors_json, concern, escape_logic, human_required, escalation_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, workflow, patient_id, level, json.dumps(factors), concern or "", escape_logic or "", 1 if auto_human else 0, status))
        risk_id = cur.lastrowid
        con.commit()
    record_interaction(workflow or "risk", "demo_assess_call_risk", {"risk_level": level, "risk_factors": factors, "concern": concern, "human_required": auto_human}, status, patient_id)
    return {"risk_event_id": risk_id, "risk_level": level, "risk_factors": factors, "human_required": auto_human, "escape_logic": escape_logic, "status": status}


def demo_page_human_triage(workflow: str, reason: str, risk_level: str, patient_id: int | None = None, urgency: str = "urgent"):
    init_demo_db()
    level = str(risk_level or "high").lower()
    if level not in {"medium", "high", "critical"}:
        level = "high"
    urg = str(urgency or "urgent").lower()
    if urg not in {"routine", "same_day", "urgent", "emergency"}:
        urg = "urgent"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO demo_escalations(ts, workflow, patient_id, risk_level, urgency, reason, status)
            VALUES (?, ?, ?, ?, ?, ?, 'paged')
        """, (now, workflow, patient_id, level, urg, reason or "Human review required"))
        esc_id = cur.lastrowid
        con.commit()
    record_interaction(workflow or "triage", "demo_page_human_triage", {"risk_level": level, "urgency": urg, "reason": reason}, "human_paged", patient_id)
    return {"escalation_id": esc_id, "paged": True, "risk_level": level, "urgency": urg, "message": "Human nurse/clinician triage paged for this demo call."}


def demo_record_blood_pressure(patient_id: int, systolic: int, diastolic: int, pulse: int | None = None, reading_time: str = "", symptoms: str = "", medication_adherence: str = ""):
    sys_val = int(systolic)
    dia_val = int(diastolic)
    risk_level = "low"
    risk_factors = []
    human_required = False
    if sys_val >= 180 or dia_val >= 120:
        risk_level = "critical"
        human_required = True
        risk_factors.append("hypertensive crisis range reading")
    elif sys_val >= 160 or dia_val >= 100:
        risk_level = "high"
        human_required = True
        risk_factors.append("very elevated blood pressure")
    elif sys_val >= 140 or dia_val >= 90:
        risk_level = "medium"
        risk_factors.append("elevated blood pressure")
    if symptoms:
        risk_level = "high" if risk_level in {"low", "medium"} else risk_level
        human_required = True
        risk_factors.append("caller-reported symptoms")
    payload = {
        "systolic": sys_val,
        "diastolic": dia_val,
        "pulse": pulse,
        "reading_time": reading_time,
        "symptoms": symptoms,
        "medication_adherence": medication_adherence,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "human_required": human_required,
    }
    record_interaction("medical_hypertension_checkup", "demo_record_blood_pressure", payload, risk_level, patient_id)
    return {"recorded": True, **payload, "message": "Blood pressure reading recorded for the hypertension check-in demo."}


def demo_get_annual_wellness_offer(patient_id: int):
    patient = _patient_context(patient_id)
    slot = next(s for s in _scheduler_slots(patient_id, "Annual wellness visit") if s["option_type"] == "annual_wellness_match")
    offer = {
        "patient": patient,
        "due": True,
        "last_visit_summary": "Thursday morning at 8:00 AM",
        "offered_slot": slot,
        "suggested_question": "Your last visit was on a Thursday morning at 8:00 AM. There is a Thursday at 8:00 AM available next week in Duluth. Would you like that appointment?",
    }
    record_interaction("medical_annual_wellness", "demo_get_annual_wellness_offer", {"patient_id": patient_id, "slot_id": slot["slot_id"]}, "offered_thursday_8am", patient_id)
    return offer


SERVICE_DESK_CATALOG = {
    "incident_categories": ["access/login", "application", "device", "network", "printing", "telephony", "security", "other"],
    "request_categories": ["new access", "access change", "hardware", "software install", "equipment move", "how-to/help", "other"],
    "priority_guidance": {
        "critical": "Widespread outage, safety/business-critical work stopped, or security incident in progress.",
        "high": "Team-level outage, executive/VIP blocker, or no workaround for urgent work.",
        "medium": "Single user impaired, workaround exists, or standard request with normal urgency.",
        "low": "Minor issue, informational ask, or future-dated request.",
    },
    "required_intake": ["caller name", "contact", "incident/request", "affected service", "summary", "impact", "urgency", "location if relevant"],
}


def demo_get_service_desk_catalog(need: str = ""):
    record_interaction("service_desk", "demo_get_service_desk_catalog", {"need": need}, "returned_catalog")
    return SERVICE_DESK_CATALOG


def _normalize_ticket_priority(priority: str = "", impact: str = "", urgency: str = "", ticket_type: str = "request") -> str:
    p = str(priority or "").strip().lower()
    if p in {"low", "medium", "high", "critical"}:
        return p
    combined = f"{impact} {urgency} {ticket_type}".lower()
    if any(term in combined for term in ["outage", "widespread", "critical", "patient safety", "security incident", "everyone", "all users"]):
        return "critical"
    if any(term in combined for term in ["blocked", "urgent", "no workaround", "team", "department", "vip"]):
        return "high"
    if any(term in combined for term in ["minor", "question", "future", "low"]):
        return "low"
    return "medium"


def demo_create_service_ticket(caller_name: str, ticket_type: str, summary: str, description: str, affected_service: str = "", impact: str = "", urgency: str = "", priority: str = "", contact: str = "", location: str = "", category: str = "", troubleshooting: str = ""):
    init_demo_db()
    kind = str(ticket_type or "incident").strip().lower()
    if kind not in {"incident", "request"}:
        kind = "incident"
    clean_priority = _normalize_ticket_priority(priority, impact, urgency, kind)
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    values = (
        now,
        kind,
        str(caller_name or "Caller").strip() or "Caller",
        str(contact or "not provided").strip() or "not provided",
        str(summary or "Service desk intake").strip() or "Service desk intake",
        str(description or "not provided").strip() or "not provided",
        str(affected_service or "not provided").strip() or "not provided",
        str(category or "other").strip() or "other",
        str(impact or "not provided").strip() or "not provided",
        str(urgency or "not provided").strip() or "not provided",
        clean_priority,
        str(location or "not provided").strip() or "not provided",
        str(troubleshooting or "not provided").strip() or "not provided",
    )
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO demo_service_tickets(ts, ticket_type, caller_name, contact, summary, description, affected_service, category, impact, urgency, priority, location, troubleshooting)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)
        ticket_id = cur.lastrowid
        con.commit()
    record_interaction("service_desk", "demo_create_service_ticket", {"ticket_type": kind, "summary": values[4], "priority": clean_priority, "affected_service": values[6]}, "ticket_created")
    return {
        "created": True,
        "ticket_id": ticket_id,
        "ticket_number": f"SD-{ticket_id:05d}",
        "ticket_type": kind,
        "priority": clean_priority,
        "status": "new",
        "message": f"Service desk {kind} ticket SD-{ticket_id:05d} created with {clean_priority} priority for this demo.",
    }


def demo_record_dlp_discovery(
    business_area: str,
    summary: str,
    role_context: str = "",
    workflows: list[str] | None = None,
    sensitive_data: list[str] | None = None,
    channels: list[str] | None = None,
    shadow_tools: list[str] | None = None,
    pain_points: list[str] | None = None,
    risk_signals: list[str] | None = None,
    recommended_next_questions: list[str] | None = None,
):
    payload = {
        "business_area": str(business_area or "unknown").strip() or "unknown",
        "role_context": str(role_context or "not provided").strip() or "not provided",
        "workflows": workflows or [],
        "sensitive_data": sensitive_data or [],
        "channels": channels or [],
        "shadow_tools": shadow_tools or [],
        "pain_points": pain_points or [],
        "risk_signals": risk_signals or [],
        "recommended_next_questions": recommended_next_questions or [],
        "summary": str(summary or "DLP discovery notes captured.").strip() or "DLP discovery notes captured.",
    }
    record_interaction("dlp_posture_consultant", "demo_record_dlp_discovery", payload, "discovery_recorded")
    return {
        "recorded": True,
        "workflow": "dlp_posture_consultant",
        "business_area": payload["business_area"],
        "summary": payload["summary"],
        "message": "DLP discovery notes captured for this demo.",
    }


DEMO_TOOL_HANDLERS = {
    "demo_lookup_patient": demo_lookup_patient,
    "demo_register_patient": demo_register_patient,
    "demo_compare_facility_options": demo_compare_facility_options,
    "demo_list_open_slots": demo_list_open_slots,
    "demo_book_appointment": demo_book_appointment,
    "demo_add_callback_task": demo_add_callback_task,
    "demo_verify_and_get_next_appointment": demo_verify_and_get_next_appointment,
    "demo_get_next_appointment": demo_get_next_appointment,
    "demo_confirm_appointment": demo_confirm_appointment,
    "demo_request_appointment_change": demo_request_appointment_change,
    "demo_capture_insurance": demo_capture_insurance,
    "demo_mark_benefits_status": demo_mark_benefits_status,
    "demo_get_discharge_followup": demo_get_discharge_followup,
    "demo_record_discharge_checkin": demo_record_discharge_checkin,
    "demo_request_rx_refill": demo_request_rx_refill,
    "demo_route_general_care": demo_route_general_care,
    "demo_assess_call_risk": demo_assess_call_risk,
    "demo_page_human_triage": demo_page_human_triage,
    "demo_record_blood_pressure": demo_record_blood_pressure,
    "demo_get_annual_wellness_offer": demo_get_annual_wellness_offer,
    "demo_get_service_desk_catalog": demo_get_service_desk_catalog,
    "demo_create_service_ticket": demo_create_service_ticket,
    "demo_record_dlp_discovery": demo_record_dlp_discovery,
}


def admin_snapshot() -> dict:
    init_demo_db()
    with _conn() as con:
        return {
            "patients": [dict(r) for r in con.execute("SELECT * FROM demo_patients ORDER BY id")],
            "appointments": [dict(r) for r in con.execute("SELECT a.*, p.name AS patient_name FROM demo_appointments a JOIN demo_patients p ON p.id=a.patient_id ORDER BY a.starts_at")],
            "insurance": [dict(r) for r in con.execute("SELECT i.*, p.name AS patient_name FROM demo_insurance i JOIN demo_patients p ON p.id=i.patient_id ORDER BY i.id")],
            "service_tickets": [dict(r) for r in con.execute("SELECT * FROM demo_service_tickets ORDER BY id DESC LIMIT 50")],
            "risk_events": [dict(r) for r in con.execute("SELECT r.*, p.name AS patient_name FROM demo_risk_events r LEFT JOIN demo_patients p ON p.id=r.patient_id ORDER BY r.id DESC LIMIT 30")],
            "escalations": [dict(r) for r in con.execute("SELECT e.*, p.name AS patient_name FROM demo_escalations e LEFT JOIN demo_patients p ON p.id=e.patient_id ORDER BY e.id DESC LIMIT 30")],
            "interactions": [dict(r) for r in con.execute("SELECT * FROM demo_interactions ORDER BY id DESC LIMIT 100")],
        }


def render_admin_html() -> str:
    snap = admin_snapshot()
    def rows(items, keys):
        if not items:
            return "<tr><td colspan='9'>No rows.</td></tr>"
        out = []
        for item in items:
            out.append("<tr>" + "".join(f"<td>{str(item.get(k, '') or '')}</td>" for k in keys) + "</tr>")
        return "\n".join(out)
    return f"""<!doctype html><html><head><meta name='viewport' content='width=device-width, initial-scale=1'><meta http-equiv='refresh' content='8'><title>Healthcare Admin</title>
<style>body{{margin:0;background:#080d15;color:#edf3fb;font-family:Inter,system-ui,sans-serif}}main{{max-width:1280px;margin:0 auto;padding:28px}}h1{{font-size:1.4rem}}.muted{{color:#92a0b4}}.grid{{display:grid;gap:18px}}section{{border:1px solid #263246;background:#101827;border-radius:18px;padding:16px;box-shadow:0 18px 60px #0005;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:.82rem}}th,td{{border-bottom:1px solid #263246;padding:8px;text-align:left;vertical-align:top}}th{{color:#9cc7ff;font-weight:650}}button{{border:1px solid #49d3b455;background:#49d3b414;color:#a7ffe9;border-radius:999px;padding:8px 12px;cursor:pointer}}.pill{{display:inline-block;border:1px solid #ffffff18;border-radius:999px;padding:5px 9px;color:#aeb8c8}}.escape{{border-color:#ff7d8a55;background:#2a1218}}</style></head>
<body><main><p class='pill'>Seeded data · auto-refresh 8s</p><h1>Healthcare Admin</h1><p class='muted'>Seeded patients, appointments, insurance records, realtime risk analysis, escalation receipts, and voice workflow outcomes for voice.jimsbots.com.</p>
<form method='post' action='/admin/demo/reset' onsubmit='return confirm("Reset seeded seed data?")'><button>Reset seed data</button></form><div class='grid'>
<section class='escape'><h2>Realtime risk / escalation monitor</h2><p class='muted'>Escape logic: human triage must be paged for high/critical risk, urgent symptoms, medication safety issues, post-discharge deterioration, caller confusion/distress, or ambiguity needing clinical judgment.</p><table><thead><tr><th>ID</th><th>Time</th><th>Workflow</th><th>Patient</th><th>Risk</th><th>Human?</th><th>Factors</th><th>Concern</th><th>Escape logic</th></tr></thead><tbody>{rows(snap['risk_events'], ['id','ts','workflow','patient_name','risk_level','human_required','risk_factors_json','concern','escape_logic'])}</tbody></table></section>
<section><h2>Human engagement / pages</h2><table><thead><tr><th>ID</th><th>Time</th><th>Workflow</th><th>Patient</th><th>Risk</th><th>Urgency</th><th>Reason</th><th>Status</th></tr></thead><tbody>{rows(snap['escalations'], ['id','ts','workflow','patient_name','risk_level','urgency','reason','status'])}</tbody></table></section>
<section><h2>Patients</h2><table><thead><tr><th>ID</th><th>Name</th><th>Phone</th><th>DOB</th><th>Keyphrase</th><th>City</th><th>Preferred facility</th></tr></thead><tbody>{rows(snap['patients'], ['id','name','phone','dob','keyphrase','city','preferred_facility'])}</tbody></table></section>
<section><h2>Appointments</h2><table><thead><tr><th>ID</th><th>Patient</th><th>Starts</th><th>Type</th><th>Provider</th><th>Location</th><th>Status</th><th>Notes</th></tr></thead><tbody>{rows(snap['appointments'], ['id','patient_name','starts_at','appointment_type','provider','location','status','notes'])}</tbody></table></section>
<section><h2>Insurance / Benefits</h2><table><thead><tr><th>ID</th><th>Patient</th><th>Provider</th><th>Member</th><th>Group</th><th>Subscriber</th><th>Relationship</th><th>Status</th></tr></thead><tbody>{rows(snap['insurance'], ['id','patient_name','provider','member_id','group_number','subscriber_name','relationship','status'])}</tbody></table></section>
<section><h2>Service desk tickets</h2><table><thead><tr><th>ID</th><th>Time</th><th>Type</th><th>Caller</th><th>Contact</th><th>Summary</th><th>Service</th><th>Priority</th><th>Status</th></tr></thead><tbody>{rows(snap['service_tickets'], ['id','ts','ticket_type','caller_name','contact','summary','affected_service','priority','status'])}</tbody></table></section>
<section><h2>Recent interactions</h2><table><thead><tr><th>ID</th><th>Time</th><th>Demo</th><th>Patient</th><th>Action</th><th>Outcome</th><th>Payload</th></tr></thead><tbody>{rows(snap['interactions'], ['id','ts','demo_type','patient_id','action','outcome','payload_json'])}</tbody></table></section>
</div></main></body></html>"""
