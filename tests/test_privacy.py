


"""Tests for observability privacy protection."""


import traceback
from observability.privacy import (
    anonymize_text,
    sanitize_value,
    sanitize_langsmith_payload,
)


def test_email_detection():
    result = anonymize_text(
        "Contact me at ahmed@example.com"
    )

    assert "ahmed@example.com" not in result


def test_international_phone_detection():
    numbers = [
        "+1 415 555 2671",
        "+44 20 7946 0958",
        "+49 151 23456789",
        "+966 50 123 4567",
        "+201001234567",
    ]

    for number in numbers:
        result = anonymize_text(f"Phone: {number}")
        assert number not in result, f"Phone was not detected: {number}"


def test_arabic_digit_phone_detection():
    result = anonymize_text(
        "رقم الهاتف: ٠١٠١٢٣٤٥٦٧٨"
    )

    assert "٠١٠١٢٣٤٥٦٧٨" not in result


def test_credit_card_detection():
    number = "4111 1111 1111 1111"

    result = anonymize_text(
        f"Credit card: {number}"
    )

    assert number not in result


def test_iban_detection():
    iban = "GB82 WEST 1234 5698 7654 32"

    result = anonymize_text(
        f"IBAN: {iban}"
    )

    assert iban not in result


def test_ip_address_detection():
    ip = "192.168.1.100"

    result = anonymize_text(
        f"IP address: {ip}"
    )

    assert ip not in result


def test_technical_secret_detection():
    secret = "Bearer abcdef1234567890"

    result = anonymize_text(secret)

    assert "abcdef1234567890" not in result


def test_sensitive_keys():
    data = {
        "email": "ahmed@example.com",
        "phone_number": "+201001234567",
        "api_key": "secret-value",
        "message_type": "user",
    }

    result = sanitize_value(data)

    assert result["email"] == "[REDACTED]"
    assert result["phone_number"] == "[REDACTED]"
    assert result["api_key"] == "[REDACTED]"
    assert result["message_type"] == "user"


def test_nested_parser_data():
    data = {
        "pages": [
            {
                "page_number": 1,
                "text": (
                    "Ahmed works at Google. "
                    "Email: ahmed@example.com"
                ),
            }
        ]
    }

    result = sanitize_value(data)

    assert "ahmed@example.com" not in str(result)
    assert "Google" in str(result)


def test_non_pii_numbers_are_preserved():
    text = (
        "Worked for 5 years. "
        "Projects: 2021, 2022, 2023. "
        "Experience: 12 years."
    )

    result = anonymize_text(text)

    assert "5 years" in result
    assert "2021" in result
    assert "2022" in result
    assert "2023" in result
    assert "12 years" in result


def test_person_names_and_locations_are_not_detected():
    text = "Ahmed works in Cairo."

    result = anonymize_text(text)

    assert "Ahmed" in result
    assert "Cairo" in result



def test_exception_traceback_sanitization():
    try:
        raise RuntimeError(
            "Request failed for test.person@example.com "
            "with api_key=sk-TESTSECRET123456"
        )

    except RuntimeError as exc:
        traceback_text = "".join(
            traceback.format_exception(
                type(exc),
                exc,
                exc.__traceback__,
            )
        )

    result = sanitize_langsmith_payload({
        "error": traceback_text,
    })

    sanitized_error = result["error"]

    assert "test.person@example.com" not in sanitized_error
    assert "sk-TESTSECRET123456" not in sanitized_error
    assert "RuntimeError" in sanitized_error


if __name__ == "__main__":
    test_email_detection()
    test_international_phone_detection()
    test_arabic_digit_phone_detection()
    test_credit_card_detection()
    test_iban_detection()
    test_ip_address_detection()
    test_technical_secret_detection()
    test_sensitive_keys()
    test_nested_parser_data()
    test_non_pii_numbers_are_preserved()
    test_person_names_and_locations_are_not_detected()

    print("All privacy tests passed!")