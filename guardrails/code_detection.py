



"""Programming code and execution pattern detection."""

import ast
import re
from typing import Any


# --------------------------------------------------
# Code Patterns
# --------------------------------------------------

CODE_PATTERNS = [

    (
        "CODE_BLOCK",
        "code_block",
        r"```[\s\S]*?```",
    ),

    # Dynamic execution.
    (
        "DYNAMIC_EXECUTION",
        "execution",
        r"\b(?:eval|exec|compile|execfile|__import__)\s*\(",
    ),

    (
        "DYNAMIC_IMPORT",
        "execution",
        r"\bimportlib\.import_module\s*\(",
    ),

    # Operating system and process execution.
    (
        "OS_PROCESS_EXECUTION",
        "execution",
        r"\b(?:"
        r"os\.system|os\.popen|"
        r"subprocess\.(?:run|Popen|call|check_call|check_output)|"
        r"shell_exec|passthru|proc_open|popen"
        r")\s*\(",
    ),

    (
        "JAVA_PROCESS_EXECUTION",
        "execution",
        r"(?:Runtime\.getRuntime\(\)\.exec|new\s+ProcessBuilder)\s*\(",
    ),

    (
        "JAVASCRIPT_PROCESS_EXECUTION",
        "execution",
        r"\brequire\s*\(\s*['\"]child_process['\"]",
    ),

    (
        "POWERSHELL_EXECUTION",
        "execution",
        r"\b(?:Invoke-Expression|iex)\b",
    ),

    (
        "FUNCTION_CONSTRUCTOR",
        "execution",
        r"\bnew\s+Function\s*\(",
    ),

    # Import statements.
    (
        "IMPORT_STATEMENT",
        "programming_syntax",
        r"(?m)^\s*(?:from\s+[\w.]+\s+import|import\s+[\w.*]+)\b",
    ),

    # Shell commands.
    (
        "SHELL_COMMAND",
        "shell",
        r"(?im)^\s*(?:\$|>\s*)?"
        r"(?:sudo|apt-get|apt|pip3?|python3?|bash|sh|"
        r"docker|git|npm|node|rm|chmod|curl|wget|"
        r"cd|ls|cat|grep|find)\s+\S+",
    ),

    # SQL statements.
    (
        "SQL_STATEMENT",
        "sql",
        r"(?is)\b(?:"
        r"SELECT\s+.+?\s+FROM|"
        r"INSERT\s+INTO|"
        r"UPDATE\s+\w+\s+SET|"
        r"DELETE\s+FROM|"
        r"DROP\s+TABLE|"
        r"ALTER\s+TABLE|"
        r"CREATE\s+TABLE|"
        r"TRUNCATE\s+TABLE"
        r")\b",
    ),

    # Programming syntax.
    (
        "PROGRAMMING_SYNTAX",
        "programming_syntax",
        r"(?im)^\s*(?:"
        r"def\s+\w+\s*\(|"
        r"class\s+\w+\s*[:(]|"
        r"function\s+\w+\s*\(|"
        r"(?:const|let|var)\s+\w+\s*=|"
        r"public\s+static\s+void\s+main|"
        r"#include\s*<|"
        r"<script\b"
        r")",
    ),

]


COMPILED_CODE_PATTERNS = [
    (
        code,
        category,
        re.compile(pattern),
    )
    for code, category, pattern in CODE_PATTERNS
]


# --------------------------------------------------
# Code Request Patterns
# These apply only to user messages.
# --------------------------------------------------

CODE_REQUEST_PATTERNS = [

    re.compile(
        r"\b(?:write|generate|create|implement|execute|run|"
        r"debug|fix|modify|review)\b"
        r".{0,80}"
        r"\b(?:code|script|program|function|class|"
        r"command|sql query)\b",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"\b(?:explain|describe)\b"
        r".{0,60}"
        r"\b(?:code|script|program|function|command)\b",
        re.IGNORECASE | re.DOTALL,
    ),

    re.compile(
        r"(?:اكتب|انشئ|اعمل|نفذ|شغل|صحح|عدل|اشرح)"
        r".{0,50}"
        r"(?:كود|كوداً|سكريبت|برنامج|أمر|اكواد|كودات)",
        re.IGNORECASE | re.DOTALL,
    ),
]


# --------------------------------------------------
# Python AST Detection
# --------------------------------------------------

PYTHON_CODE_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.With,
    ast.For,
    ast.While,
    ast.If,
    ast.Try,
)


def _detect_python_ast(
    text: str,
) -> bool:
    """Detect recognizable Python code structures."""

    try:

        tree = ast.parse(text)

    except (SyntaxError, ValueError, TypeError):
        return False

    return any(
        isinstance(node, PYTHON_CODE_NODES)
        for node in ast.walk(tree)
    )


# --------------------------------------------------
# Main Code Scanner
# --------------------------------------------------

def scan_code_patterns(
    text: str,
    message_type: str,
) -> dict[str, Any]:
    """Scan text for prohibited code and execution patterns."""

    findings = []
    detected_codes = set()

    for code, category, pattern in COMPILED_CODE_PATTERNS:

        if pattern.search(text):

            if code not in detected_codes:

                findings.append({
                    "code": code,
                    "category": category,
                })

                detected_codes.add(code)

    # Detect code-generation and execution requests.
    if message_type == "user":

        for pattern in CODE_REQUEST_PATTERNS:

            if pattern.search(text):

                code = "CODE_REQUEST"

                if code not in detected_codes:

                    findings.append({
                        "code": code,
                        "category": "code_request",
                    })

                    detected_codes.add(code)

    # Additional Python syntax detection.
    if _detect_python_ast(text):

        code = "PYTHON_AST"

        if code not in detected_codes:

            findings.append({
                "code": code,
                "category": "programming_syntax",
            })

    return {
        "detected": bool(findings),
        "findings": findings,
    }