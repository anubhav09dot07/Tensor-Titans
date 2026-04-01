from __future__ import annotations

import json
import os
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


class NoteRequest(BaseModel):
    doctor_name: str = Field(default="")
    patient_name: str = Field(default="")
    patient_phone: str = Field(pattern=r"^\d{10}$")
    age: int | None = Field(default=None, ge=0, le=110)
    sex: str = Field(default="")
    blood_group: str = Field(default="")
    transcript: str = Field(min_length=10)
    gemini_api_key: str = Field(default="")
    model: str = Field(default="gemini-2.5-flash")


class StructuredNote(BaseModel):
    chief_complaints: List[str]
    duration: str
    history: str
    vitals: str
    medications: List[str]
    allergies: str
    assessment: str
    plan: List[str]
    follow_up: str


def build_prompt(req: NoteRequest) -> str:
    return f"""
You are a clinical documentation assistant.

Create a structured SOAP note from the consultation transcript.
Return ONLY valid JSON with the exact schema below and no extra keys.

Schema:
{{
  "chief_complaints": ["string"],
  "duration": "string",
  "history": "string",
  "vitals": "string",
  "medications": ["string"],
  "allergies": "string",
  "assessment": "string",
  "plan": ["string"],
  "follow_up": "string"
}}

Rules:
- Keep uncertain items explicit (e.g., "Not documented").
- Do not invent vitals, diagnosis certainty, or medication dose if absent.
- Use concise, clinically readable language.

Patient context:
- Doctor: {req.doctor_name or "Not provided"}
- Patient: {req.patient_name or "Unknown"}
- Patient Phone: {req.patient_phone or "NA"}
- Age: {req.age if req.age is not None else "NA"}
- Sex: {req.sex or "NA"}
- Blood Group: {req.blood_group or "NA"}

Transcript:
{req.transcript.strip()}
""".strip()


def parse_json_text(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: extract the first valid top-level JSON object from mixed output.
    start = cleaned.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", cleaned, 0)

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : i + 1])

    raise json.JSONDecodeError("Incomplete JSON object", cleaned, start)


def _to_text(value: object, fallback: str = "Not documented") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(parts) if parts else fallback
    if isinstance(value, dict):
        pairs = [f"{k}: {v}" for k, v in value.items()]
        return ", ".join(pairs) if pairs else fallback
    return str(value).strip() or fallback


def _to_list(value: object, fallback_item: str = "Not documented") -> list[str]:
    if value is None:
        return [fallback_item]
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        return items or [fallback_item]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else [fallback_item]
    if isinstance(value, dict):
        return [_to_text(value, fallback_item)]
    text = str(value).strip()
    return [text] if text else [fallback_item]


def normalize_note_dict(note_dict: dict) -> dict:
    return {
        "chief_complaints": _to_list(note_dict.get("chief_complaints"), "General consultation"),
        "duration": _to_text(note_dict.get("duration")),
        "history": _to_text(note_dict.get("history")),
        "vitals": _to_text(note_dict.get("vitals")),
        "medications": _to_list(note_dict.get("medications"), "To be confirmed by doctor"),
        "allergies": _to_text(note_dict.get("allergies")),
        "assessment": _to_text(note_dict.get("assessment")),
        "plan": _to_list(note_dict.get("plan"), "Clinical review advised"),
        "follow_up": _to_text(note_dict.get("follow_up"), "As needed"),
    }


def call_gemini(req: NoteRequest) -> StructuredNote:
    api_key = req.gemini_api_key.strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="Gemini API key missing. Add it in UI or set GEMINI_API_KEY.")

    model = req.model.strip() or "gemini-2.5-flash"
    if model.startswith("models/"):
        model = model.split("/", 1)[1]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": build_prompt(req)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }

    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"Gemini API HTTP error: {detail[:400]}") from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail="Unable to reach Gemini API.") from exc

    candidates = payload.get("candidates", [])
    if not candidates:
        raise HTTPException(status_code=502, detail="Gemini returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
    if not text.strip():
        raise HTTPException(status_code=502, detail="Gemini returned empty text response.")

    try:
        note_dict = parse_json_text(text)
        normalized = normalize_note_dict(note_dict)
        return StructuredNote(**normalized)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gemini response was not valid structured JSON.") from exc


def render_note(req: NoteRequest, note: StructuredNote) -> str:
    patient_line = f"Patient: {req.patient_name or 'Unknown'}"
    if req.age is not None or req.sex:
        patient_line += f" | Age/Sex: {req.age if req.age is not None else 'NA'}/{req.sex or 'NA'}"

    lines = [
        f"Doctor: {req.doctor_name or 'Not provided'}",
        patient_line,
        "",
        "S - Subjective",
        f"Chief complaints: {', '.join(note.chief_complaints)}",
        f"Duration: {note.duration}",
        f"History: {note.history}",
        "",
        "O - Objective",
        f"Vitals: {note.vitals}",
        f"Allergies: {note.allergies}",
        "",
        "A - Assessment",
        note.assessment,
        "",
        "P - Plan",
        f"Medications: {', '.join(note.medications)}",
        f"Follow-up: {note.follow_up}",
    ]

    for i, step in enumerate(note.plan, start=1):
        lines.append(f"{i}. {step}")

    return "\n".join(lines)


app = FastAPI(title="Clinical Documentation Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/generate-note")
def generate_note(req: NoteRequest) -> dict:
    structured = call_gemini(req)
    note_text = render_note(req, structured)
    return {
        "structured": structured.model_dump(),
        "note_text": note_text,
        "quality_flags": [
            "Doctor must verify assessment and medications before finalizing.",
            "Vitals should be captured if clinically relevant.",
            "AI output generated via Gemini and requires clinician approval.",
        ],
    }


app.mount("/", StaticFiles(directory="backend/app/static", html=True), name="static")
