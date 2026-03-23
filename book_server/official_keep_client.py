"""Official Google Keep API client using OAuth user credentials."""
from __future__ import annotations

import json
from typing import Any, Iterator

import config

SCOPES = ["https://www.googleapis.com/auth/keep.readonly"]


def connect(*, interactive: bool = False):
    """Return an authenticated Google Keep API service."""
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _load_credentials()

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)

    if not creds or not creds.valid:
        if not interactive:
            raise EnvironmentError(
                "Missing valid Google Keep OAuth credentials. "
                "Run `book-notes-keep-auth` or `python -m book_server.official_keep_client` first."
            )
        creds = bootstrap_token()

    return build("keep", "v1", credentials=creds, cache_discovery=False)


def bootstrap_token() -> Credentials:
    """Run the installed-app OAuth flow once and persist the refresh token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not config.KEEP_CLIENT_ID or not config.KEEP_CLIENT_SECRET:
        raise EnvironmentError(
            "Missing KEEP_CLIENT_ID or KEEP_CLIENT_SECRET in environment."
        )

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": config.KEEP_CLIENT_ID,
                "client_secret": config.KEEP_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _save_credentials(creds)
    return creds


def list_notes(
    service: Any,
    *,
    page_token: str | None = None,
    page_size: int = 100,
    include_trashed: bool = False,
) -> dict[str, Any]:
    """List a page of Keep notes."""
    params: dict[str, Any] = {
        "pageSize": page_size,
        "pageToken": page_token,
    }
    if not include_trashed:
        params["filter"] = "trashed = false"
    request = service.notes().list(**params)
    return request.execute()


def iter_notes(service: Any, *, page_size: int = 100) -> Iterator[dict[str, Any]]:
    """Yield all non-trashed notes available to the authenticated account."""
    page_token: str | None = None
    while True:
        payload = list_notes(service, page_token=page_token, page_size=page_size)
        for note in payload.get("notes", []):
            yield note
        page_token = payload.get("nextPageToken")
        if not page_token:
            break


def get_note(service: Any, note_name: str) -> dict[str, Any]:
    """Fetch a single note by resource name."""
    return service.notes().get(name=note_name).execute()


def extract_text(note: dict[str, Any]) -> str:
    """Extract a plain-text representation from an official Keep note payload."""
    parts: list[str] = []
    title = (note.get("title") or "").strip()
    if title:
        parts.append(title)

    body = note.get("body") or {}
    _append_section(parts, body)

    attachments = note.get("attachments") or []
    if attachments:
        mime_types = sorted(
            {
                mime
                for attachment in attachments
                for mime in (attachment.get("mimeType") or [])
                if mime
            }
        )
        if mime_types:
            parts.append(f"[attachments]: {', '.join(mime_types)}")

    return "\n".join(part for part in parts if part.strip()).strip()


def modified_time(note: dict[str, Any]) -> str | None:
    return note.get("updateTime")


def _append_section(parts: list[str], section: dict[str, Any]) -> None:
    text_block = ((section.get("text") or {}).get("text") or "").strip()
    if text_block:
        parts.append(text_block)

    list_block = section.get("list") or {}
    for item in list_block.get("listItems", []):
        _append_list_item(parts, item, indent="")


def _append_list_item(parts: list[str], item: dict[str, Any], *, indent: str) -> None:
    marker = "✓" if item.get("checked") else "•"
    text = ((item.get("text") or {}).get("text") or "").strip()
    if text:
        parts.append(f"{indent}{marker} {text}")
    for child in item.get("childListItems", []):
        _append_list_item(parts, child, indent="  ")


def _load_credentials() -> Credentials | None:
    from google.oauth2.credentials import Credentials

    token_path = config.KEEP_TOKEN_FILE
    if not token_path.exists():
        return None
    data = json.loads(token_path.read_text(encoding="utf-8"))
    return Credentials.from_authorized_user_info(data, SCOPES)


def _save_credentials(creds: Credentials) -> None:
    config.KEEP_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.KEEP_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def bootstrap_entrypoint() -> None:
    bootstrap_token()
    print(f"Saved Google Keep OAuth token to {config.KEEP_TOKEN_FILE}")


if __name__ == "__main__":
    bootstrap_entrypoint()
