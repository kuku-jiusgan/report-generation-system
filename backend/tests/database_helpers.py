from pathlib import Path

from backend.app.config import Settings
from backend.app.database import Database


def make_test_database(directory: Path) -> Database:
    """Create a database gateway using the MySQL test database from conftest."""
    settings = Settings(
        data_dir=directory / "data",
        template_path=directory / "template.docx",
        onlyoffice_jwt_secret="test-secret",
        public_base_url="http://127.0.0.1:8010",
    )
    settings.ensure_directories()
    database = Database(settings)
    database.initialize()
    return database
