"""Pytest fixtures shared across the test suite.

Tkinter's Tcl interpreter doesn't handle having many root windows
created and destroyed in the same process — we share a single root
for all CTk-using tests. Each test creates a ``CTkFrame`` as a child
of the shared root and tears down its own children only.
"""
from __future__ import annotations

import threading
import time

import pytest


# ----- Shared Tk root for all tests that need it -------------------------


_shared_root = None
_shared_root_lock = threading.Lock()


@pytest.fixture(scope="session")
def _shared_ctk_root():
    """One CTk root for the whole pytest session.

    Tkinter's Tcl interpreter is finicky about being asked to create
    and destroy multiple roots in the same process — so we share one
    and ask each test to clean up only the widgets it created.
    """
    global _shared_root
    with _shared_root_lock:
        if _shared_root is None:
            import customtkinter as ctk
            _shared_root = ctk.CTk()
            yield _shared_root
            try:
                _shared_root.destroy()
            except Exception:
                pass
            _shared_root = None
        else:
            yield _shared_root


@pytest.fixture
def tk_root(_shared_ctk_root):
    """Hand the shared CTk root to a test."""
    return _shared_root


@pytest.fixture
def tk_serial(_shared_ctk_root):
    """Serialise Tk-using tests via a simple mutex (single-threaded
    pytest already runs serially; this is mainly a safety net).
    """
    yield