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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
