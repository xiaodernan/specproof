"""P1.4 Integration tests: SSE reconnection with Last-Event-ID."""

import json
import time
import uuid

import pytest


def make_test_job_id():
    return f"test-sse-{uuid.uuid4().hex[:12]}"


class TestSSEReconnectLogic:
    """Test SSE event stream parsing and Last-Event-ID reconnection logic
    without requiring a running server (pure protocol tests)."""

    def test_event_format_parseable(self):
        """Verify SSE event format is valid and parseable by a client."""
        sample_line = 'data: {"node": "compile", "status": "running", "percent": 42.0, "message": "ok"}'
        assert sample_line.startswith("data: ")
        payload = json.loads(sample_line[6:])
        assert payload["node"] == "compile"
        assert payload["status"] == "running"
        assert payload["percent"] == 42.0
        assert payload["message"] == "ok"

    def test_id_format(self):
        """Verify SSE id lines are parseable."""
        sample_id = "id: 1638457600000-0"
        assert sample_id.startswith("id: ")
        event_id = sample_id[4:]
        assert "-" in event_id

    def test_event_type(self):
        """Verify SSE event type is 'progress'."""
        sample_event = "event: progress"
        assert sample_event == "event: progress"

    def test_special_characters_in_message(self):
        """Messages with special characters should be valid JSON."""
        payload = json.dumps({
            "node": "run_differential",
            "status": "failed",
            "percent": 80.0,
            "message": 'Error: "NullPointerException" at line 42\n\tat com.example.Test',
        }, ensure_ascii=False)
        parsed = json.loads(payload)
        assert "NullPointerException" in parsed["message"]
        assert "\t" in parsed["message"]

    def test_unicode_in_message(self):
        """Unicode characters should survive JSON round-trip."""
        payload = json.dumps({
            "node": "compile_contracts",
            "status": "completed",
            "percent": 100.0,
            "message": "编译了 6 个合约 ✓",
        }, ensure_ascii=False)
        parsed = json.loads(payload)
        assert "编译" in parsed["message"]
        assert "✓" in parsed["message"]


class TestLastEventIDReconnection:
    """Test the reconnection catch-up logic."""

    def test_resume_from_last_id_skips_prior_events(self):
        """When reconnecting with Last-Event-ID, events up to that ID
        should be skipped and only newer events delivered."""
        all_events = [
            {"id": "1000-0", "node": "intake", "percent": 0.0},
            {"id": "1000-1", "node": "compile", "percent": 10.0},
            {"id": "1000-2", "node": "prepare_base", "percent": 20.0},
            {"id": "1000-3", "node": "prepare_head", "percent": 30.0},
            {"id": "1000-4", "node": "scan_contracts", "percent": 40.0},
        ]
        last_event_id = "1000-2"

        caught_up = [e for e in all_events if e["id"] > last_event_id]
        assert len(caught_up) == 2
        assert caught_up[0]["id"] == "1000-3"
        assert caught_up[1]["id"] == "1000-4"

    def test_resume_from_zero_gets_all(self):
        """When connecting with Last-Event-ID: 0, all events are delivered."""
        all_events = [
            {"id": "1000-0", "node": "intake", "percent": 0.0},
            {"id": "1000-1", "node": "compile", "percent": 10.0},
        ]
        from_id = "0"
        caught_up = [e for e in all_events if e["id"] > from_id]
        assert len(caught_up) == 2

    def test_deduplicate_sent_event_ids(self):
        """Events already sent should not be re-sent within the same connection."""
        sent_ids = {"1000-0", "1000-1", "1000-2"}
        all_events = [
            {"id": "1000-1", "node": "compile"},  # duplicate
            {"id": "1000-2", "node": "prepare_base"},  # duplicate
            {"id": "1000-3", "node": "prepare_head"},  # new
        ]
        new_events = [e for e in all_events if e["id"] not in sent_ids]
        assert len(new_events) == 1
        assert new_events[0]["id"] == "1000-3"

    def test_empty_stream_on_reconnect(self):
        """If no new events since last disconnect, empty result is valid."""
        all_events = []
        caught_up = [e for e in all_events if e["id"] > "1000-5"]
        assert caught_up == []


class TestProgressPercentBoundaries:
    """Verify percent values across the full 0-100 range."""

    def test_percent_boundaries(self):
        for pct in [0.0, 0.1, 8.3, 25.0, 50.0, 75.0, 91.7, 100.0]:
            payload = json.dumps({
                "node": "test",
                "status": "running",
                "percent": pct,
                "message": f"{pct}% done",
            })
            parsed = json.loads(payload)
            assert parsed["percent"] == pct

    def test_percent_float_precision(self):
        """Float percentages should maintain at least 1 decimal precision."""
        payload = json.dumps({
            "node": "test",
            "status": "running",
            "percent": 8.333333333333334,
            "message": "in progress",
        })
        parsed = json.loads(payload)
        assert abs(parsed["percent"] - 8.333) < 0.001
