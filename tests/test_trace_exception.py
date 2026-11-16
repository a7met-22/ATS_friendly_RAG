

"""Verify exception sanitization in LangSmith."""
from dotenv import load_dotenv

load_dotenv()

from observability.tracing import trace_operation


@trace_operation(
    name="privacy_exception_test",
    profile="pipeline",
)
def simulate_sensitive_error():
    raise RuntimeError(
        "Request failed for test.person@example.com "
        "with api_key=sk-TESTSECRET123456"
    )


try:
    simulate_sensitive_error()
except RuntimeError as exc:
    print("Original exception preserved:")
    print(type(exc).__name__)
    print(str(exc))