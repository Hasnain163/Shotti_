import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.utils.errors import RateLimitError


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Turn upstream rate limits into skips for live tests only.

    An exhausted free-tier quota is not a code defect, and reporting it as a
    failure trains you to ignore red. Mocked tests are never affected: they make
    no network calls, so they cannot raise this.
    """
    outcome = yield
    report = outcome.get_result()
    if (
        report.when == "call"
        and call.excinfo is not None
        and isinstance(call.excinfo.value, RateLimitError)
        and item.get_closest_marker("live") is not None
    ):
        report.outcome = "skipped"
        report.wasxfail = "upstream rate limit / quota exhausted"


@pytest.fixture(autouse=True)
def reset_process_state():
    """Clear the process-wide services and result cache between tests.

    These are deliberately module-level singletons in production — one HTTP client
    pool, one shared cache. In tests that means state leaks from one test into the
    next: a cached verdict answers a later test's request before its mocks are ever
    called, which is exactly what happened when the cache was introduced.
    """
    import app.dependencies as deps

    deps._cache = None
    deps._gemini = None
    deps._firecrawl = None
    yield
    deps._cache = None
    deps._gemini = None
    deps._firecrawl = None


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
