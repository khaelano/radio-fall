"""Neutral model and reader of recorded collection sessions.

This package is the one place that knows how a session directory or version-3
archive is laid out. Analysis, collection and the session inspector all depend
on it, and it imports nothing from them: its only dependency inside
``fall_detection`` is ``protocol`` (for the planned trials). Import from the
defining module: ``session.models`` holds the manifest-level models and
``load_session``/``scan_sessions``, ``session.source`` the directory/archive
reader ``SessionSource``, and ``session.schema`` the on-disk schema version.
"""
