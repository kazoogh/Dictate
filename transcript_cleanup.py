"""Local post-processing for Quick Dictate — filler removal + punctuation."""

from __future__ import annotations

import re
import threading

from punctuation_assets import ensure_punctuation_assets

_STANDALONE_FILLERS = frozenset(
    {
        "um",
        "uh",
        "uhh",
        "umm",
        "uhm",
        "hmm",
        "hm",
        "er",
        "ah",
        "ahh",
        "eh",
        "mmm",
        "mm",
        "mhm",
        "mm-hmm",
    }
)

_FILLER_PHRASES = [
    r"\byou know what i mean\b",
    r"\byou know\b",
    r"\bi mean\b",
    r"\bkind of\b",
    r"\bsort of\b",
]

_FILLER_WORD_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(word) for word in sorted(_STANDALONE_FILLERS, key=len, reverse=True))
    + r")\b[,.]?\s*",
    re.IGNORECASE,
)

_LIKE_COMMA_FILLER = re.compile(r",\s*like\s*,", re.IGNORECASE)
_LIKE_SENTENCE_START = re.compile(
    r"(^|[.!?]\s+)like,?\s+(?=(?:how|what|if|when|where|why|who|can|will|is|are|do|does|did|so|i|we|you|they)\b)",
    re.IGNORECASE,
)
_LIKE_VERB_FILLER = re.compile(
    r"\b(?:was|were|i'm|im|she's|he's|they're|it's)\s+like\s+",
    re.IGNORECASE,
)
_DANGLING_LIKE = re.compile(r"\s+like\s+(?:a|an|the)\s*$", re.IGNORECASE)
_SHOUTING_WORD = re.compile(r"\b[A-Z]{2,}\b")
_KNOWN_PHRASES = (
    (re.compile(r"\bwhisper\s+flow\b", re.IGNORECASE), "Whisper Flow"),
    (re.compile(r"\bdictate\s+app\b", re.IGNORECASE), "Dictate app"),
)

_CONTINUATION_AFTER_PERIOD = re.compile(
    r"(\w{2,})\.\s+("
    r"it's|i'm|i've|i'll|we're|they're|you're|he's|she's|"
    r"don't|doesn't|isn't|aren't|won't|can't|haven't|hasn't|"
    r"wouldn't|couldn't|shouldn't|didn't"
    r")\b",
    re.IGNORECASE,
)
_ACRONYMS = frozenset(
    {
        "AI",
        "API",
        "CPU",
        "GPU",
        "IAN",
        "LL",
        "LR",
        "MSA",
        "NV",
        "PDF",
        "PSA",
        "RX",
        "SRP",
        "UI",
        "UL",
        "UR",
        "USA",
        "USB",
    }
)


class _OnnxPunctuation:
    def __init__(self, punctuator) -> None:
        self._punctuator = punctuator

    def restore_punctuation(self, text: str) -> str:
        # Model is trained on plain lowercased words without existing punctuation.
        if hasattr(self._punctuator, "add_punctuation"):
            return self._punctuator.add_punctuation(text)
        return self._punctuator.add_punctuation_with_case(text)


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _fix_punctuation_artifacts(text: str) -> str:
    """Repair common ASR + model glitches."""
    text = _normalize_whitespace(text)
    text = re.sub(r",\s*,+", ", ", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r"\.\s*,", ".", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",\s*$", "", text)
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r"\s+([,.?!:;])", r"\1", text)
    text = re.sub(r"([,.?!:;]){2,}", r"\1", text)
    # "word. Next" where Next is a broken fragment -> keep; fix "I. Don't" -> "I don't"
    text = re.sub(r"\bI\.\s+([a-z])", r"I \1", text)
    text = re.sub(r",\s+I,\s+", " I ", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s+", ", ", text)
    text = re.sub(r"(?<=[.!?])\s*(?=[a-z])", " ", text)
    text = _CONTINUATION_AFTER_PERIOD.sub(lambda m: f"{m.group(1)}, {m.group(2)}", text)
    for pattern, replacement in _KNOWN_PHRASES:
        text = pattern.sub(replacement, text)
    return text.strip()


def _strip_for_punctuation_model(text: str) -> str:
    """ONNX punctuation expects unpunctuated lowercased text."""
    text = text.lower()
    tokens: list[str] = []
    for token in text.split():
        cleaned = re.sub(r"^[^a-z0-9']+|[^a-z0-9']+$", "", token)
        if cleaned:
            tokens.append(cleaned)
    return " ".join(tokens)


def _fix_pronoun_i(text: str) -> str:
    return re.sub(r"\bi\b", "I", text)


def _fix_shouting(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        word = match.group(0)
        if word in _ACRONYMS:
            return word
        return word.capitalize()

    return _SHOUTING_WORD.sub(_replace, text)


def _apply_sentence_case(text: str) -> str:
    text = _fix_punctuation_artifacts(text)
    text = _fix_shouting(text)
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        part = part[0].upper() + part[1:] if len(part) > 1 else part.upper()
        part = _fix_pronoun_i(part)
        out.append(part)
    return " ".join(out)


def remove_fillers(text: str) -> str:
    """Remove common speech disfluencies while keeping meaningful 'like' uses."""
    text = _normalize_whitespace(text)
    if not text:
        return text

    for phrase in _FILLER_PHRASES:
        text = re.sub(phrase, "", text, flags=re.IGNORECASE)

    text = re.sub(
        r"(^|[.!?]\s+)(?:basically|actually|literally|honestly|obviously|yeah|so\s+yeah),?\s+",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(^|[.!?]\s+)anyway,?\s+", r"\1", text, flags=re.IGNORECASE)

    text = _LIKE_COMMA_FILLER.sub(" ", text)
    text = _LIKE_SENTENCE_START.sub(r"\1", text)
    text = _LIKE_VERB_FILLER.sub(" ", text)
    text = _FILLER_WORD_PATTERN.sub("", text)
    text = _DANGLING_LIKE.sub("", text)

    return _fix_punctuation_artifacts(text)


class TranscriptCleaner:
    """Filler cleanup + ONNX punctuation (bundled for .exe, no PyTorch/API)."""

    def __init__(self) -> None:
        self._punct_model: _OnnxPunctuation | None = None
        self._punct_lock = threading.Lock()
        self._punct_error: str | None = None
        self._preload_started = False
        self._load_done = threading.Event()

    def preload_punctuation(self) -> None:
        with self._punct_lock:
            if self._preload_started:
                return
            self._preload_started = True
        threading.Thread(target=self._load_punctuation_model, daemon=True).start()

    def _load_punctuation_model(self) -> None:
        try:
            import sherpa_onnx

            model_dir = ensure_punctuation_assets()
            model_path = model_dir / "model.int8.onnx"
            if not model_path.is_file():
                model_path = model_dir / "model.onnx"
            bpe_vocab = model_dir / "bpe.vocab"
            model_config = sherpa_onnx.OnlinePunctuationModelConfig(
                cnn_bilstm=str(model_path),
                bpe_vocab=str(bpe_vocab),
                num_threads=2,
            )
            config = sherpa_onnx.OnlinePunctuationConfig(model_config=model_config)
            punctuator = sherpa_onnx.OnlinePunctuation(config)
            with self._punct_lock:
                self._punct_model = _OnnxPunctuation(punctuator)
        except Exception as exc:
            with self._punct_lock:
                self._punct_error = str(exc)
        finally:
            self._load_done.set()

    def wait_for_punctuation(self, timeout: float = 60.0) -> bool:
        """Block until the ONNX punctuation model is loaded (or failed)."""
        with self._punct_lock:
            if self._punct_model is not None:
                return True
            if self._punct_error:
                return False
            if not self._preload_started:
                self._preload_started = True
                threading.Thread(target=self._load_punctuation_model, daemon=True).start()
        self._load_done.wait(timeout)
        with self._punct_lock:
            return self._punct_model is not None

    def punctuation_error(self) -> str | None:
        with self._punct_lock:
            return self._punct_error

    def _get_punctuation_model(self) -> _OnnxPunctuation | None:
        with self._punct_lock:
            if self._punct_model is not None:
                return self._punct_model
            if self._punct_error:
                return None
        if not self._load_done.is_set():
            self._load_done.wait(timeout=2.0)
        with self._punct_lock:
            return self._punct_model

    def punctuation_available(self) -> bool:
        return self._get_punctuation_model() is not None

    def clean(
        self,
        text: str,
        *,
        remove_fillers_enabled: bool = True,
        add_punctuation: bool = True,
    ) -> str:
        if not text or not text.strip():
            return text

        if remove_fillers_enabled:
            text = remove_fillers(text)

        if add_punctuation:
            model = self._get_punctuation_model()
            plain = _strip_for_punctuation_model(text)
            if model is not None and plain:
                try:
                    text = model.restore_punctuation(plain)
                except Exception:
                    text = _apply_sentence_case(plain)
            elif plain:
                text = plain
            text = _apply_sentence_case(text)
        else:
            text = _apply_sentence_case(text)

        return _fix_punctuation_artifacts(text)
