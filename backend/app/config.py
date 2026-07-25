from functools import lru_cache
import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "报告自动生成系统"
    api_prefix: str = "/api/v1"
    data_dir: Path = PROJECT_ROOT / "data"
    template_path: Path = PROJECT_ROOT / "templates" / "report-template.docx"
    max_upload_mb: int = 50
    allowed_origins: list[str] = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8088", "http://127.0.0.1:8088",
    ]
    onlyoffice_url: str = "http://127.0.0.1:8088"
    public_base_url: str = "http://127.0.0.1:8010"
    onlyoffice_jwt_secret: str = ""
    lims_sql_enabled: bool = False
    lims_excel_import_enabled: bool = True
    lims_sql_dsn: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="REPORT_",
        extra="ignore",
    )

    @property
    def database_path(self) -> Path:
        return self.data_dir / "report-system.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def lims_dir(self) -> Path:
        return self.data_dir / "lims"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.uploads_dir, self.reports_dir, self.lims_dir, self.template_path.parent):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.onlyoffice_jwt_secret:
        local_config = Path(r"C:\Program Files\ONLYOFFICE\DocumentServer\config\local.json")
        if local_config.exists():
            try:
                payload = json.loads(local_config.read_text(encoding="utf-8"))
                settings.onlyoffice_jwt_secret = str(payload["services"]["CoAuthoring"]["secret"]["browser"]["string"])
            except (KeyError, TypeError, ValueError, OSError):
                pass
    settings.ensure_directories()
    return settings
