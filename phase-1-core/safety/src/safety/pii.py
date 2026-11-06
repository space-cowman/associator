"""Personal data detection: Microsoft Presidio with spaCy's small English model."""

import logging
import re
import threading
import types

import tldextract
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    InAadhaarRecognizer,
    InPanRecognizer,
    PhoneRecognizer,
)
from presidio_analyzer.predefined_recognizers.generic import email_recognizer

setattr(  # noqa: B010
    email_recognizer,
    "tldextract",
    types.SimpleNamespace(extract=tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)),
)

logging.getLogger("presidio-analyzer").setLevel(logging.WARNING)

ALWAYS_BLOCK = {"EMAIL_ADDRESS", "CREDIT_CARD", "IBAN_CODE", "US_SSN", "IN_PAN", "IN_AADHAAR"}
WARN = {"PERSON", "LOCATION", "IP_ADDRESS"}
ENTITIES = sorted(ALWAYS_BLOCK | WARN | {"PHONE_NUMBER"})
PHONE_REGIONS = ("IN", "US", "GB", "DE", "CA", "AU", "SG", "AE")
SCORE_THRESHOLD = 0.35
_WORDS = re.compile(r"[A-Za-z][A-Za-z .'-]*")

_engine: AnalyzerEngine | None = None
_engine_lock = threading.Lock()


def engine() -> AnalyzerEngine:
    """Built once (loading the model takes seconds); call at startup to warm it."""
    global _engine
    with _engine_lock:
        if _engine is None:
            nlp = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                }
            ).create_engine()
            registry = RecognizerRegistry(supported_languages=["en"])
            registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp)
            registry.remove_recognizer("PhoneRecognizer")
            registry.add_recognizer(PhoneRecognizer(supported_regions=PHONE_REGIONS))
            registry.add_recognizer(InPanRecognizer())
            registry.add_recognizer(InAadhaarRecognizer())
            _engine = AnalyzerEngine(registry=registry, nlp_engine=nlp, supported_languages=["en"])
        return _engine


def find_pii(text: str, kind: str) -> list[tuple[str, str, int, int]]:
    """(entity, severity, start, end) for personal data in text."""
    found: list[tuple[str, str, int, int]] = []
    for r in engine().analyze(
        text=text, language="en", entities=ENTITIES, score_threshold=SCORE_THRESHOLD
    ):
        span = text[r.start : r.end]
        if r.entity_type in ("PERSON", "LOCATION") and not _WORDS.fullmatch(span):
            continue
        if r.entity_type in ALWAYS_BLOCK:
            severity = "block"
        elif r.entity_type == "PHONE_NUMBER":
            severity = "block" if kind in ("text", "steps") else "warn"
        else:
            severity = "warn"
        found.append((r.entity_type, severity, r.start, r.end))
    return found
