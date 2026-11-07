


"""Streamlit views: access selection, login, upload, and RAG workspace."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import streamlit as st

from application.services.document_scope import get_session_upload_ids
from application.services.qa_service import answer_question
from application.services.upload_service import process_uploaded_pdf
from database_utilities.database_connection import get_connection
from security.authorization import Principal, authenticate, is_principal_active
from parsingWays.llama_parsing import create_drive_parser
from parsingWays.pymupdf_parsing import parse_pdf_bytes as pymupdf_parser
from config.settings import PARSER_TYPE


PARSING = PARSER_TYPE  # "llama" or "pymupdf"

def _initialize_state() -> None:
    defaults = {
        "access_mode": None,
        "principal": None,
        "upload_session_id": uuid.uuid4().hex,
        "chat_history": [],
        "parser": None,
        "login_failures": 0,
        "lockout_until": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _logout() -> None:
    for key in (
        "principal",
        "access_mode",
        "chat_history",
        "login_failures",
        "lockout_until",
    ):
        st.session_state[key] = (
            None
            if key in {"principal", "access_mode", "lockout_until"}
            else []
            if key == "chat_history"
            else 0
        )

    # Start a new isolated upload session.
    st.session_state.upload_session_id = uuid.uuid4().hex

    st.rerun()

def _get_parser():
    if st.session_state.parser is None:
        if PARSING == "llama":
            st.session_state.parser = create_drive_parser()
        elif PARSING == "pymupdf":   
            st.session_state.parser = pymupdf_parser
    return st.session_state.parser


def _render_entry() -> None:
    st.title("RAG Document Assistant")
    st.write("Choose how you want to use the document assistant.")
    left, right = st.columns(2)
    with left:
        st.subheader("Guest workspace")
        st.write("Upload your own PDFs and search only those files in this session.")
        if st.button("Continue as guest", type="primary", use_container_width=True):
            st.session_state.access_mode = "guest"
            st.rerun()
    with right:
        st.subheader("Authorized system access")
        st.write("Sign in with an approved account to search system documents.")
        if st.button("Sign in", use_container_width=True):
            st.session_state.access_mode = "login"
            st.rerun()


def _render_login() -> None:
    st.title("Authorized sign in")
    st.caption("System-document access is available only to approved accounts.")
    lockout_until = st.session_state.lockout_until
    if lockout_until and datetime.now(timezone.utc) < lockout_until:
        st.error("Too many failed attempts. Please wait before trying again.")
        if st.button("Back"):
            st.session_state.access_mode = None
            st.rerun()
        return

    with st.form("authorized_login"):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Authenticate", type="primary")

    if submitted:
        principal = authenticate(email, password)
        if principal is None:
            st.session_state.login_failures += 1
            if st.session_state.login_failures >= 5:
                from datetime import timedelta
                st.session_state.lockout_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            st.error("The email or password is incorrect, or the account is not authorized.")
        else:
            st.session_state.principal = principal
            st.session_state.access_mode = "system"
            st.session_state.login_failures = 0
            st.session_state.lockout_until = None
            st.session_state.chat_history = []
            st.rerun()

    if st.button("Back to access selection"):
        st.session_state.access_mode = None
        st.rerun()


def _render_upload_section() -> None:
    st.subheader("Upload PDFs")
    uploaded_files = st.file_uploader(
        "Choose one or more PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploads",
    )
    if st.button("Process uploaded PDFs", type="primary", disabled=not uploaded_files):
        progress = st.progress(0)
        messages = st.container()
        for index, uploaded_file in enumerate(uploaded_files):
            with messages:
                try:
                    result = process_uploaded_pdf(
                        pdf_bytes=uploaded_file.getvalue(),
                        filename=uploaded_file.name,
                        upload_session_id=st.session_state.upload_session_id,
                        parser=_get_parser(),
                    )
                    action = "Duplicate content reused" if result["reused"] else "Processed"
                    st.success(
                        f"{result['filename']} — {result['chunk_count']} chunks — "
                        f"{action} (document ID: {result['document_id']})"
                    )
                except Exception as exc:
                    st.error(
                        f"{uploaded_file.name}: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    st.exception(exc)
                progress.progress((index + 1) / len(uploaded_files))


def _render_workspace(principal: Principal | None) -> None:
    
    authenticated = principal is not None
    st.title("RAG Document Assistant")
    if authenticated:
        st.caption(f"Authenticated as {principal.email}")
    else:
        st.caption("Guest mode — search is restricted to PDFs uploaded in this session.")

    with st.sidebar:
        st.header("Search settings")
        retrieval_mode = st.selectbox(
            "Retrieval method",
            ["hybrid", "semantic", "keyword"],
            format_func=lambda value: {
                "hybrid": "Hybrid (Semantic + Keyword)",
                "semantic": "Semantic",
                "keyword": "Keyword",
            }[value],
        )
        top_k = st.slider("Retrieved chunks", 1, 15, 5)
        if authenticated:
            st.divider()
            include_uploads = st.toggle(
                "Include my session uploads in search",
                value=False,
                help="System documents are always searched for authorized users. Enable this to add your current-session PDFs.",
            )
        else:
            include_uploads = True
            st.info("Search scope: current-session uploads only.")
        st.divider()
        if st.button("Log out" if authenticated else "Exit guest workspace"):
            _logout()

    _render_upload_section()

    upload_ids = get_session_upload_ids(st.session_state.upload_session_id)
    if upload_ids:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, filename FROM public.documents WHERE id = ANY(%s::bigint[]) ORDER BY filename, id",
                    (upload_ids,),
                )
                upload_rows = cur.fetchall()
        st.subheader("Current-session uploads")
        st.dataframe(
            [{"Document ID": row[0], "Filename": row[1]} for row in upload_rows],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No processed PDFs have been uploaded in this session yet.")

    st.divider()
    st.subheader("Ask a question")
    with st.form("rag_question", clear_on_submit=True):
        question = st.text_area("Question", placeholder="Ask a question about the available documents...", height=90)
        submitted = st.form_submit_button("Search and answer", type="primary")

    if submitted:
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            try:
                with st.spinner("Retrieving relevant chunks and generating an answer..."):
                    result = answer_question(
                        question=question.strip(),
                        upload_session_id=st.session_state.upload_session_id,
                        principal=principal,
                        include_session_uploads=include_uploads,
                        top_k=top_k,
                        retrieval_mode=retrieval_mode,
                    )
                st.session_state.chat_history.append({
                    "question": question.strip(),
                    "answer": result["answer"],
                    "sources": result["sources"],
                    "citations": result.get("citations", []),
                    "mode": result["retrieval_mode"],
                    "scope": result.get("prompt_access_level", "guest"),
                })
            except Exception as exc:
                st.error(f"Question answering failed: {type(exc).__name__}: {exc}")

    for item in reversed(st.session_state.chat_history):
        with st.chat_message("user"):
            st.markdown(item["question"])
        with st.chat_message("assistant"):
            st.markdown(item["answer"])
            if item.get("citations"):
                with st.expander(
                     f"Citations ({len(item['citations'])})"
               ):
                    for citation in item["citations"]:
                        st.write(
                            f"{citation['document_title']} "
                            f"· Chunk {citation['chunk_id']}"
                        )
            st.caption(f"Retrieval: {item['mode']} · Access policy: {item['scope']}")
            if item["sources"]:
                with st.expander(f"Sources ({len(item['sources'])})"):
                    for source in item["sources"]:
                        label = (
                            f"{source['document_title']} · Chunk {source['chunk_id']}"
                        )
                        if source.get("section"):
                            label += f" · {source['section']}"
                        st.write(label)


def render_app() -> None:
    st.set_page_config(page_title="RAG Document Assistant", page_icon="📚", layout="wide")
    _initialize_state()

    mode = st.session_state.access_mode
    principal = st.session_state.principal

    if principal is not None and not is_principal_active(principal):
        st.session_state.principal = None
        st.session_state.access_mode = None
        st.session_state.chat_history = []
        st.warning("Your authenticated session expired. Please sign in again.")
        st.session_state.upload_session_id = uuid.uuid4().hex
        st.rerun()

    if mode is None:
        _render_entry()
    elif mode == "login" and principal is None:
        _render_login()
    elif mode == "guest":
        _render_workspace(None)
    elif mode == "system" and principal is not None:
        _render_workspace(principal)
    else:
        st.session_state.access_mode = None
        st.rerun()
