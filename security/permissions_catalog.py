"""Centralized, extensible permission catalog for RBAC (zero external imports)."""

from __future__ import annotations

PERMISSION_SYSTEM_SEARCH = "search_system_documents"
PERMISSION_DOCUMENTS_WRITE = "documents:write"
PERMISSION_SYSTEM_SYNC = "system:sync"
PERMISSION_MANAGE_USERS = "admin:manage_users"
PERMISSION_MANAGE_ROLES = "admin:manage_roles"

PERMISSION_CATALOG: tuple[dict[str, str], ...] = (
    {
        "code": PERMISSION_SYSTEM_SEARCH,
        "category": "Documents & Search",
        "label": "Read & Search System CVs",
        "description": "Query and retrieve answers from company Google Drive resumes.",
    },
    {
        "code": PERMISSION_DOCUMENTS_WRITE,
        "category": "Documents & Search",
        "label": "Upload & Manage Documents",
        "description": "Upload new resumes and manage document records.",
    },
    {
        "code": PERMISSION_SYSTEM_SYNC,
        "category": "System Operations",
        "label": "Trigger Google Drive Sync",
        "description": "Start background synchronization with Google Drive.",
    },
    {
        "code": PERMISSION_MANAGE_USERS,
        "category": "Administration",
        "label": "Manage Users",
        "description": "Create users, assign roles, and activate or deactivate accounts.",
    },
    {
        "code": PERMISSION_MANAGE_ROLES,
        "category": "Administration",
        "label": "Manage Roles & Permissions",
        "description": "Create custom roles and configure allowed operations.",
    },
)

ALL_PERMISSION_CODES: frozenset[str] = frozenset(item["code"] for item in PERMISSION_CATALOG)
