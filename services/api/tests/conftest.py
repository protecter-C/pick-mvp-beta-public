import os
import shutil
from pathlib import Path
import pytest

TEST_DB = Path(__file__).parent / "test_pick.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AUTH_SECRET"] = "test-secret"
os.environ["AFFILIATE_WEBHOOK_SECRET"] = "test-affiliate-secret"
os.environ["ADMIN_API_KEY"] = "test-admin"
os.environ["ENVIRONMENT"] = "test"
os.environ.pop("SERPAPI_KEY", None)


@pytest.fixture
def tmp_path(request):
    """Use a repository-local temp root because the managed runner blocks system temp ACLs."""
    path = Path(__file__).parent / ".runtime-tests" / request.node.name
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)
