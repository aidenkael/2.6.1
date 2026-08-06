"""Shared pytest configuration for the whole test suite.

CRITICAL — Qt application lifecycle
===================================
The entire suite MUST share exactly ONE ``QApplication`` for the whole
session. Previously each Qt test module built its own application with
``QApplication.instance() or QApplication([])`` (often stored only in a
local variable or a module-scoped fixture). When that last Python reference
was garbage-collected the C++ ``QApplication`` was destroyed, taking every
widget with it; the next module then created a *new* application. Recreating
``QApplication`` inside a single process leaves Qt global state and widget
wrappers inconsistent, and on Linux with the ``offscreen`` platform plugin it
manifests as a segmentation fault inside Qt style/paint code (observed in
``CalculationBinder._update_single_rule_status`` -> ``QLabel.setStyleSheet``).

The session-scoped ``qapp`` fixture below is the single owner of the
``QApplication``. Every Qt test must request it (directly, or through a
fixture that requests it). Never create a ``QApplication`` inside a test
function or a narrower-scoped fixture.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")

import pytest


def _has_pyside6() -> bool:
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def qapp():
    """Single ``QApplication`` shared by every Qt test for the whole session."""
    if not _has_pyside6():
        pytest.skip("PySide6 not available")
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    # Session teardown: flush any widgets still queued for deferred deletion.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture(autouse=True)
def _qt_flush_deferred_deletes():
    """After every test, actually process pending ``DeferredDelete`` events.

    ``deleteLater()`` only *posts* a DeferredDelete event; it is handled the
    next time the event loop runs. A single ``processEvents()`` call in a test
    teardown is therefore not enough — a widget can survive into the next test
    and be destroyed mid-use. Explicitly sending the DeferredDelete events and
    then processing them guarantees a test's widgets are destroyed before the
    following test starts. This is a no-op when no ``QApplication`` exists
    (pure-logic tests).
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
    except Exception:
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
