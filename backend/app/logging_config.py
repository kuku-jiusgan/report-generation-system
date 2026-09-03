import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def configure_logging(data_dir: Path) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if getattr(root, "_report_logging_configured", False):
        return
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    application = TimedRotatingFileHandler(
        log_dir / "app.log", when="midnight", interval=1, backupCount=14,
        encoding="utf-8", utc=True,
    )
    application.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(application)
    setattr(root, "_report_logging_configured", True)
    root.info("日志系统已启用 log_dir=%s", log_dir)

