"""Select the prompt policy associated with the verified access level."""

from prompts.guest import GUEST_SYSTEM_PROMPT
from prompts.system_user import SYSTEM_USER_PROMPT


def get_system_prompt(*, authenticated_system_access: bool) -> str:
    """Return the guest or authorized-system prompt.

    The boolean must be derived from the verified Principal, never from a UI
    checkbox or a user-provided request parameter.
    """
    return SYSTEM_USER_PROMPT if authenticated_system_access else GUEST_SYSTEM_PROMPT
