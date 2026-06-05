"""Shared test setup.

Forces mock mode and an isolated throwaway database BEFORE any nichefit module
is imported, so the whole suite runs fully offline and never spends credits or
touches the real cache.
"""
import contextlib
import os
import tempfile

os.environ["NICHEFIT_FORCE_MOCK"] = "1"
os.environ["NICHEFIT_DB"] = os.path.join(tempfile.gettempdir(), "nichefit_test.db")

# Start from a clean DB, then create the schema (the app's startup hook isn't
# run for tests that call the engine directly).
with contextlib.suppress(OSError):
    os.remove(os.environ["NICHEFIT_DB"])

from nichefit.data import cache as _cache  # noqa: E402  (must follow env setup)

_cache.init_db()
