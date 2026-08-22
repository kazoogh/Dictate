import json
import logging
import os
import re
import ssl
import tempfile
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from pydantic import BaseModel
from faster_whisper import WhisperModel

APP_NAME = "dictate-api"

API_KEY = os.environ.get("DICTATE_API_KEY", "change-this-now")
MODEL_SIZE = os.environ.get("DICTATE_MODEL_SIZE", "base")
DEVICE = os.environ.get("DICTATE_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("DICTATE_COMPUTE_TYPE", "int8")
LANGUAGE = os.environ.get("DICTATE_LANGUAGE", "en")

CLEANUP_MODE = os.environ.get("DICTATE_CLEANUP_MODE", "basic").strip().lower()
if CLEANUP_MODE not in {"basic", "openai"}:
    CLEANUP_MODE = "basic"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_CLEANUP_MODEL = os.environ.get("OPENAI_CLEANUP_MODEL", "gpt-4o-mini")
OPENAI_CLEANUP_TIMEOUT = float(os.environ.get("OPENAI_CLEANUP_TIMEOUT", "20"))
VOCAB_PATH = os.environ.get(
    "DICTATE_VOCAB_PATH", str(Path(__file__).with_name("vocabulary.json"))
)

CleanupMode = Literal["basic", "openai"]

CLEANUP_SYSTEM_PROMPT_BASE = (
    "You are polishing a voice dictation transcript into clean, Wispr-style written text.\n"
    "This is dictation cleanup, NOT verbatim transcript preservation.\n"
    "Remove speech fillers and disfluencies such as: um, uh, ah, er, like, you know, I mean, "
    "basically, actually, just, kind of, and sort of when used as filler rather than meaningful content.\n"
    "Remove repeated accidental words (for example: 'I I I need' -> 'I need', 'call call' -> 'call').\n"
    "Remove obvious false starts when the speaker restarts (for example: "
    "'I need to, I mean, we should call the patient' -> 'We should call the patient').\n"
    "Fix grammar, punctuation, capitalization, spacing, and paragraph structure.\n"
    "Fix obvious speech-to-text errors when clear from context.\n"
    "Preserve the speaker's intended meaning.\n"
    "Do not add new facts.\n"
    "Do not remove important content.\n"
    "Keep names, dates, numbers, phone numbers, emails, addresses, codes, and dollar amounts "
    "unchanged unless clearly misheard.\n"
    "Do not make clinical, legal, billing, insurance, or HR conclusions.\n"
    "Return only the corrected text."
)

# rewrite_basic_cleanup test notes:
# 1. "um so this is a test..." -> capitalized, fillers removed, trailing punctuation
# 2. "uh i need to call call the patient tomorrow at 3 pm" -> "call call" collapsed
# 3. "like the patient said..." -> leading "like" removed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title=APP_NAME)

model = None
model_lock = threading.Lock()

stats = {
    "started_at": time.time(),
    "transcribe_count": 0,
    "last_error": "",
    "last_transcribe_seconds": None,
}


class CleanupRequest(BaseModel):
    text: str


class RewriteRequest(BaseModel):
    text: str
    mode: Optional[CleanupMode] = None


class ClinicalGenerateRequest(BaseModel):
    procedure_type: str
    transcript: str
    template_name: Optional[str] = None


def require_api_key(x_api_key: Optional[str]):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_model():
    global model

    if model is None:
        model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    return model


def load_vocabulary_terms() -> list[str]:
    if not os.path.isfile(VOCAB_PATH):
        logger.warning("Vocabulary file not found path=%s", VOCAB_PATH)
        return []

    try:
        with open(VOCAB_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        logger.warning("Failed to load vocabulary file path=%s error=%s", VOCAB_PATH, exc)
        return []

    raw_terms = data.get("terms", [])
    if not isinstance(raw_terms, list):
        logger.warning("Vocabulary file invalid: terms is not a list path=%s", VOCAB_PATH)
        return []

    terms = []
    seen = set()
    for entry in raw_terms:
        if isinstance(entry, str):
            term = entry.strip()
        elif isinstance(entry, dict):
            term = str(entry.get("term", "")).strip()
        else:
            continue
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)

    logger.info("Loaded vocabulary_terms_count=%d path=%s", len(terms), VOCAB_PATH)
    return terms


def build_cleanup_system_prompt(terms: list[str]) -> str:
    prompt = CLEANUP_SYSTEM_PROMPT_BASE
    if not terms:
        return prompt

    term_lines = "\n".join(f"- {term}" for term in terms)
    return (
        f"{prompt}\n\n"
        "The following vocabulary terms are common in this user's environment. "
        "If the transcript contains a phrase that is clearly a speech-to-text error for one of "
        "these terms, correct it to the exact vocabulary term. Do not force these terms where "
        "they do not belong.\n"
        "Prefer vocabulary terms only when context strongly suggests them.\n"
        "Do not randomly replace unrelated words.\n"
        "Do not overcorrect generic words.\n"
        "Preserve exact capitalization and punctuation of vocabulary terms.\n"
        "Examples: 'chat gpt' or 'chat g p t' may become 'ChatGPT'; 'make dot com' or 'make com' "
        "may become 'Make.com'; 'oh llama' may become 'Ollama'.\n"
        "Vocabulary terms:\n"
        f"{term_lines}"
    )


def _vocabulary_obvious_variants(term: str) -> list[str]:
    variants = set()
    normalized = " ".join(term.split()).lower()
    variants.add(normalized)

    if "." in term:
        parts = [part.strip() for part in term.split(".") if part.strip()]
        if len(parts) == 2:
            variants.add(f"{parts[0].lower()} dot {parts[1].lower()}")
            variants.add(f"{parts[0].lower()} {parts[1].lower()}")

    spaced = re.sub(
        r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        " ",
        term,
    ).lower()
    variants.add(spaced)

    return [variant for variant in variants if variant]


def apply_basic_vocabulary_fixes(text: str, terms: list[str]) -> str:
    if not terms or not text:
        return text

    replacements = []
    for term in terms:
        for variant in _vocabulary_obvious_variants(term):
            if variant.lower() != term.lower():
                replacements.append((variant, term))

    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    result = text
    for variant, term in replacements:
        result = re.sub(re.escape(variant), term, result, flags=re.IGNORECASE)
    return result


def simple_cleanup(text: str) -> str:
    cleaned = " ".join((text or "").split())

    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."

    return cleaned


_FILLER_PHRASES = ("you know", "i mean", "kind of", "sort of")
_FILLER_WORDS = (
    "um",
    "uh",
    "uhh",
    "umm",
    "ah",
    "ahh",
    "er",
    "eh",
    "hmm",
    "hm",
    "like",
    "basically",
    "actually",
)
_FILLER_WORD_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(word) for word in _FILLER_WORDS)
    + r")\b[,.]?\s*",
    re.IGNORECASE,
)


def rewrite_basic_cleanup(text: str, terms: Optional[list[str]] = None) -> str:
    """Dictation cleanup for /rewrite basic mode and OpenAI fallback."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cleaned = " ".join(cleaned.split())
    vocab_terms = terms if terms is not None else load_vocabulary_terms()

    for phrase in _FILLER_PHRASES:
        cleaned = re.sub(
            rf"\b{re.escape(phrase)}\b[,.]?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = _FILLER_WORD_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"^just\s+", "", cleaned, flags=re.IGNORECASE)

    words = cleaned.split()
    collapsed = []
    for word in words:
        if collapsed and word.lower() == collapsed[-1].lower():
            continue
        collapsed.append(word)
    cleaned = " ".join(collapsed).strip()
    cleaned = apply_basic_vocabulary_fixes(cleaned, vocab_terms)

    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."

    return cleaned


def openai_cleanup(text: str, terms: Optional[list[str]] = None) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    vocab_terms = terms if terms is not None else load_vocabulary_terms()
    logger.info("OpenAI cleanup vocabulary_terms_count=%d", len(vocab_terms))

    payload = {
        "model": OPENAI_CLEANUP_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": build_cleanup_system_prompt(vocab_terms)},
            {"role": "user", "content": text},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(
            request, timeout=OPENAI_CLEANUP_TIMEOUT, context=context
        ) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {err_body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI returned no choices")
    message = choices[0].get("message") or {}
    content = str(message.get("content", "")).strip()
    if not content:
        raise RuntimeError("OpenAI returned empty content")
    return content


def apply_dictation_cleanup(text: str, mode: str) -> dict:
    """Same cleanup path as /rewrite. Returns text, mode_used, cleanup_error."""
    vocab_terms = load_vocabulary_terms()
    logger.info("Cleanup vocabulary_terms_count=%d", len(vocab_terms))

    if mode == "basic":
        return {
            "text": rewrite_basic_cleanup(text, vocab_terms),
            "mode_used": "basic",
            "cleanup_error": None,
            "vocabulary_terms_count": len(vocab_terms),
        }

    try:
        return {
            "text": openai_cleanup(text, vocab_terms),
            "mode_used": "openai",
            "cleanup_error": None,
            "vocabulary_terms_count": len(vocab_terms),
        }
    except Exception as exc:
        return {
            "text": rewrite_basic_cleanup(text, vocab_terms),
            "mode_used": "basic",
            "cleanup_error": str(exc)[:300],
            "vocabulary_terms_count": len(vocab_terms),
        }


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": APP_NAME,
        "uptime_seconds": round(time.time() - stats["started_at"], 2),
        "model_size": MODEL_SIZE,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "language": LANGUAGE,
        "model_loaded": model is not None,
        "transcribe_count": stats["transcribe_count"],
        "last_transcribe_seconds": stats["last_transcribe_seconds"],
        "last_error": stats["last_error"],
    }


@app.post("/cleanup")
def cleanup(payload: CleanupRequest, x_api_key: Optional[str] = Header(default=None)):
    require_api_key(x_api_key)

    return {
        "text": simple_cleanup(payload.text),
        "raw_text": payload.text,
    }


@app.post("/rewrite")
def rewrite(payload: RewriteRequest, x_api_key: Optional[str] = Header(default=None)):
    require_api_key(x_api_key)

    mode = payload.mode or CLEANUP_MODE
    if mode not in {"basic", "openai"}:
        raise HTTPException(status_code=400, detail="mode must be 'basic' or 'openai'")

    input_chars = len(payload.text or "")
    vocab_terms = load_vocabulary_terms()
    logger.info(
        "Rewrite request received mode=%s input_chars=%d vocabulary_terms_count=%d",
        mode,
        input_chars,
        len(vocab_terms),
    )

    if mode == "basic":
        cleaned = rewrite_basic_cleanup(payload.text, vocab_terms)
        logger.info("Output character count=%d", len(cleaned))
        return {
            "text": cleaned,
            "raw_text": payload.text,
            "mode": "basic",
            "vocabulary_terms_count": len(vocab_terms),
        }

    logger.info("OpenAI cleanup started input_chars=%d", input_chars)
    try:
        cleaned = openai_cleanup(payload.text, vocab_terms)
        logger.info("OpenAI cleanup finished output_chars=%d", len(cleaned))
        return {
            "text": cleaned,
            "raw_text": payload.text,
            "mode": "openai",
            "vocabulary_terms_count": len(vocab_terms),
        }
    except Exception as exc:
        logger.warning("Fallback used after OpenAI error: %s", exc)
        cleaned = rewrite_basic_cleanup(payload.text, vocab_terms)
        logger.info("Output character count=%d", len(cleaned))
        return {
            "text": cleaned,
            "raw_text": payload.text,
            "mode": "basic",
            "cleanup_error": str(exc)[:300],
            "vocabulary_terms_count": len(vocab_terms),
        }


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    logger.info(
        "Transcribe request received filename=%s",
        file.filename or "unknown",
    )

    started = time.time()
    temp_audio_path = ""

    try:
        suffix = os.path.splitext(file.filename or "")[1] or ".wav"
        audio_bytes = await file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            temp_audio.write(audio_bytes)
            temp_audio_path = temp_audio.name

        logger.info(
            "Temp file saved path=%s size_bytes=%d",
            temp_audio_path,
            len(audio_bytes),
        )

        with model_lock:
            logger.info("Whisper transcription started path=%s", temp_audio_path)
            whisper = get_model()
            segments, info = whisper.transcribe(
                temp_audio_path,
                language=LANGUAGE,
                beam_size=1,
                vad_filter=True,
            )

            raw_text = " ".join(segment.text.strip() for segment in segments).strip()
            logger.info(
                "Whisper transcription finished path=%s raw_chars=%d",
                temp_audio_path,
                len(raw_text),
            )

        logger.info("Cleanup mode selected mode=%s raw_chars=%d", CLEANUP_MODE, len(raw_text))
        cleanup_started = time.time()
        logger.info("Cleanup started mode=%s", CLEANUP_MODE)

        cleanup_result = apply_dictation_cleanup(raw_text, CLEANUP_MODE)
        cleaned_text = cleanup_result["text"]

        cleanup_elapsed = round(time.time() - cleanup_started, 2)
        logger.info(
            "Cleanup finished mode=%s duration_seconds=%.2f cleaned_chars=%d",
            cleanup_result["mode_used"],
            cleanup_elapsed,
            len(cleaned_text),
        )
        if cleanup_result["cleanup_error"]:
            logger.warning("Cleanup fallback used: %s", cleanup_result["cleanup_error"])

        elapsed = round(time.time() - started, 2)

        stats["transcribe_count"] += 1
        stats["last_transcribe_seconds"] = elapsed
        stats["last_error"] = ""

        response = {
            "text": cleaned_text,
            "raw_text": raw_text,
            "language": getattr(info, "language", LANGUAGE),
            "language_probability": getattr(info, "language_probability", None),
            "processing_time_seconds": elapsed,
            "model": MODEL_SIZE,
            "device": DEVICE,
            "cleanup_mode": cleanup_result["mode_used"],
            "vocabulary_terms_count": cleanup_result["vocabulary_terms_count"],
        }
        if cleanup_result["cleanup_error"]:
            response["cleanup_error"] = cleanup_result["cleanup_error"]

        logger.info(
            "Response returned processing_time_seconds=%.2f raw_chars=%d cleaned_chars=%d cleanup_mode=%s",
            elapsed,
            len(raw_text),
            len(cleaned_text),
            cleanup_result["mode_used"],
        )
        return response

    except Exception as error:
        stats["last_error"] = str(error)
        logger.exception("Transcribe failed")
        raise HTTPException(status_code=500, detail=str(error))

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                logger.info("Temp file deleted path=%s", temp_audio_path)
            except Exception as exc:
                logger.warning("Failed to delete temp file path=%s error=%s", temp_audio_path, exc)


@app.post("/clinical/generate")
def clinical_generate(
    payload: ClinicalGenerateRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    return {
        "ok": False,
        "status": "not_implemented_yet",
        "message": "Clinical generation endpoint exists, but will be connected after Quick Dictate server mode works.",
        "procedure_type": payload.procedure_type,
    }
