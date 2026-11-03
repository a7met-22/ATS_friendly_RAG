

import importlib

modules = [
    "config.settings",

    "security.passwords",
    "security.authorization",

    "application.services.document_scope",
    "application.services.upload_service",
    "application.services.qa_service",

    "application.ui.main_view",

    "prompts.guest",
    "prompts.system_user",
    "prompts.registry",

    "src.document_processor",
    "src.chunking",
    "src.embeddings",
    "src.store_chunks",
    "src.retrieval",
    "src.answer_generation",

    "database_utilities.database_connection",
    "database_utilities.document_utilities",

    "parsingWays.llama_parsing",
    "orchestrator.orchestration",
]

failed = []

print("=" * 45)
print("PROJECT IMPORT TEST")
print("=" * 45)

for module_name in modules:
    try:
        importlib.import_module(module_name)
        print(f"PASS  {module_name}")

    except Exception as error:
        print(f"FAIL  {module_name}: {error}")
        failed.append(module_name)

print("=" * 45)

if failed:
    print(f"FAILED MODULES: {len(failed)}")

    for module in failed:
        print(module)
else:
    print("ALL MODULES IMPORTED SUCCESSFULLY")