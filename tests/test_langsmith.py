



from dotenv import load_dotenv

from guardrails.pipeline import inspect_message

load_dotenv()


def test_langsmith_privacy():
    sensitive_email = "ahmed.test@example.com"

    test_message = (
        f"My email is {sensitive_email}. "
        "Please validate this message."
    )

    result = inspect_message(
        content=test_message,
        message_type="user",
    )

    print("Local Guardrails Result:")
    print(result)

    print("\nCheck LangSmith:")
    print("1. Open the guardrails project.")
    print("2. Find the inspect_message trace.")
    print("3. Inspect Inputs and Outputs.")


if __name__ == "__main__":
    test_langsmith_privacy()