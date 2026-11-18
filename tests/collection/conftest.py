"""Shared fixtures for collection tests."""

from __future__ import annotations

import pytest

from fall_detection.collection.capture import SessionArtifactStore


@pytest.fixture(autouse=True)
def finish_open_session_stores(monkeypatch):
    """Finish session stores a test left open so their event logs are closed.

    Many controller tests stop mid-session. In the collector, the runtime always
    ends the session; here the store is finished at teardown instead.
    """
    stores: list[SessionArtifactStore] = []
    original = SessionArtifactStore.__init__

    def tracking_init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        stores.append(self)

    monkeypatch.setattr(SessionArtifactStore, "__init__", tracking_init)
    yield
    for store in stores:
        # A test that simulates a crash closes the event log itself.
        if not store._event_file.closed:
            store.finish("test_teardown", 0)
