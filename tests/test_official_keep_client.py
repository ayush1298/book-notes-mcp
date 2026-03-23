from __future__ import annotations

from book_server.official_keep_client import extract_text


def test_extract_text_from_plain_text_note():
    note = {
        "title": "Atomic Habits",
        "body": {
            "text": {
                "text": "Make habits obvious and easy.",
            }
        },
    }

    assert extract_text(note) == "Atomic Habits\nMake habits obvious and easy."


def test_extract_text_from_checklist_note():
    note = {
        "title": "Reading plan",
        "body": {
            "list": {
                "listItems": [
                    {
                        "text": {"text": "Read chapter 1"},
                        "checked": False,
                        "childListItems": [
                            {
                                "text": {"text": "Take notes"},
                                "checked": True,
                            }
                        ],
                    }
                ]
            }
        },
    }

    assert extract_text(note) == "Reading plan\n• Read chapter 1\n  ✓ Take notes"


def test_extract_text_returns_empty_for_unsupported_note():
    assert extract_text({"attachments": []}) == ""
