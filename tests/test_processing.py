"""Tests for the processing/summarizer module — mocks LiteLLM, no API key needed."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


SAMPLE_RAW_TEXT = """\
The key to building good habits is to make them obvious, attractive, easy, and satisfying.
James Clear calls these the Four Laws of Behavior Change in Atomic Habits.
Implementation intentions (I will do X at Y time in Z place) dramatically increase follow-through.
"""

SAMPLE_LLM_RESPONSE = {
    "book_title": "Atomic Habits",
    "summary": "• Habits follow Four Laws: obvious, attractive, easy, satisfying\n• Implementation intentions boost follow-through",
    "ideas": [
        "Four Laws of Behavior Change",
        "Implementation intentions increase follow-through",
        "Environment design shapes habits",
    ],
    "tags": ["habits", "behavior-change", "productivity"],
    "actions": [
        "Write an implementation intention for one habit this week",
        "Audit your environment for habit cues",
    ],
}


def _make_mock_completion(response_dict: dict):
    """Create a mock litellm.completion return value."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(response_dict)
    return mock_response


# ── Tests ──────────────────────────────────────────────────────────────────

class TestProcessNote:
    @patch("processing.summarizer.litellm.completion")
    def test_returns_expected_keys(self, mock_completion):
        mock_completion.return_value = _make_mock_completion(SAMPLE_LLM_RESPONSE)
        from processing.summarizer import process_note

        result = process_note(SAMPLE_RAW_TEXT)

        assert set(result.keys()) == {"book_title", "summary", "ideas", "tags", "actions"}

    @patch("processing.summarizer.litellm.completion")
    def test_book_title_extracted(self, mock_completion):
        mock_completion.return_value = _make_mock_completion(SAMPLE_LLM_RESPONSE)
        from processing.summarizer import process_note

        result = process_note(SAMPLE_RAW_TEXT)
        assert result["book_title"] == "Atomic Habits"

    @patch("processing.summarizer.litellm.completion")
    def test_tags_are_lowercase(self, mock_completion):
        response = {**SAMPLE_LLM_RESPONSE, "tags": ["Habits", "PRODUCTIVITY", "Decision-Making"]}
        mock_completion.return_value = _make_mock_completion(response)
        from processing.summarizer import process_note

        result = process_note(SAMPLE_RAW_TEXT)
        assert all(t == t.lower() for t in result["tags"])

    @patch("processing.summarizer.litellm.completion")
    def test_strips_markdown_fences(self, mock_completion):
        """Model sometimes wraps JSON in ```json fences — we should handle that."""
        mock = MagicMock()
        mock.choices[0].message.content = (
            "```json\n" + json.dumps(SAMPLE_LLM_RESPONSE) + "\n```"
        )
        mock_completion.return_value = mock
        from processing.summarizer import process_note

        result = process_note(SAMPLE_RAW_TEXT)
        assert result["book_title"] == "Atomic Habits"

    @patch("processing.summarizer.litellm.completion")
    def test_handles_missing_optional_fields(self, mock_completion):
        """If LLM omits optional fields, we should fill in safe defaults."""
        minimal = {"book_title": None, "summary": "Short summary"}
        mock_completion.return_value = _make_mock_completion(minimal)
        from processing.summarizer import process_note

        result = process_note(SAMPLE_RAW_TEXT)
        assert result["ideas"] == []
        assert result["tags"] == []
        assert result["actions"] == []

    @patch("processing.summarizer.litellm.completion")
    def test_raises_on_invalid_json(self, mock_completion):
        mock = MagicMock()
        mock.choices[0].message.content = "This is not JSON at all."
        mock_completion.return_value = mock
        from processing.summarizer import process_note
        from tenacity import RetryError

        # tenacity wraps the ValueError in a RetryError after 3 attempts
        with pytest.raises((ValueError, RetryError)) as exc_info:
            process_note(SAMPLE_RAW_TEXT)

        # Verify the root cause is indeed a ValueError about non-JSON
        exc = exc_info.value
        if hasattr(exc, "last_attempt"):
            cause = exc.last_attempt.exception()
            assert "non-JSON" in str(cause)
        else:
            assert "non-JSON" in str(exc)
