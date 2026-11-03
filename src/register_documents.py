


"""Register PDF documents in PostgreSQL.(From the local "uploaded_pdfs" directory)"""

import hashlib
import json

from config.settings import DATA_DIR
from database_utilities.database_connection import get_connection


def register_documents() -> None:
    """Register PDF files and avoid duplicates using their content hash."""

    pdf_files = sorted(DATA_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"FAIL: No PDF files found in {DATA_DIR}")
        return

    registered = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for pdf_file in pdf_files:
                content_hash = hashlib.sha256(
                    pdf_file.read_bytes()
                ).hexdigest()

                # Check whether this document already exists.
                cur.execute(
                    """
                    SELECT id
                    FROM rag.documents
                    WHERE content_hash = %s
                    LIMIT 1
                    """,
                    (content_hash,),
                )

                existing = cur.fetchone()

                if existing:
                    print(
                        f"Already registered: {pdf_file.name} "
                        f"(ID: {existing[0]})"
                    )
                    continue

                # Register the new document.
                cur.execute(
                    """
                    INSERT INTO rag.documents
                        (title, source_uri, mime_type, content_hash,
                         status, metadata)
                    VALUES (%s, %s, 'application/pdf', %s, 'pending', %s)
                    RETURNING id
                    """,
                    (
                        pdf_file.name,
                        str(pdf_file.resolve()),
                        content_hash,
                        json.dumps({"file_name": pdf_file.name}),
                    ),
                )

                document_id = cur.fetchone()[0]
                registered += 1

                print(
                    f"Registered: {pdf_file.name} "
                    f"(ID: {document_id})"
                )

    print(f"\nCompleted. New documents registered: {registered}")


if __name__ == "__main__":
    register_documents()
