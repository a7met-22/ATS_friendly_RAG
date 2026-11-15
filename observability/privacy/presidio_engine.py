

"""Presidio analyzer and anonymizer configuration."""

from functools import lru_cache

import phonenumbers

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.predefined_recognizers.generic.phone_recognizer import (
    PhoneRecognizer,
)
from presidio_anonymizer import AnonymizerEngine


SUPPORTED_ENTITIES = [
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
]

PHONE_CONTEXT = [
    "phone",
    "phone number",
    "telephone",
    "mobile",
    "mobile number",
    "cellphone",
    "contact number",
    "call",
    "هاتف",
    "رقم الهاتف",
    "رقم الموبايل",
    "رقم الجوال",
    "телефон",
    "téléphone",
    "telefon",
    "teléfono",
]


@lru_cache(maxsize=1)
def get_presidio_engines():
    """Initialize and reuse Presidio engines."""

    analyzer = AnalyzerEngine()

    # Replace the default phone recognizer with a global configuration.
    analyzer.registry.remove_recognizer("PhoneRecognizer")

    analyzer.registry.add_recognizer(
        PhoneRecognizer(
            supported_regions=sorted(phonenumbers.SUPPORTED_REGIONS),
            supported_language="en",
            supported_entity="PHONE_NUMBER",
            context=PHONE_CONTEXT,
            leniency=3,
        )
    )

    anonymizer = AnonymizerEngine()

    return analyzer, anonymizer