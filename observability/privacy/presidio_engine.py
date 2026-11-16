


"""Centralized Presidio engine initialization."""

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

SUPPORTED_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "IP_ADDRESS",
    "URL",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_SSN",
]

@lru_cache(maxsize=1)
def get_presidio_engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    """Initialize and cache Presidio analyzer and anonymizer engines."""

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    return analyzer, anonymizer