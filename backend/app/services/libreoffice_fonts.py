"""Fontconfig environment shared by project LibreOffice processes."""

import os

from ..config import PROJECT_ROOT


def libreoffice_font_env() -> dict[str, str]:
    fonts = PROJECT_ROOT / "ttf"
    config = PROJECT_ROOT / "fonts.conf"
    if not fonts.is_dir() or not config.is_file():
        raise RuntimeError("LibreOffice 字体配置缺失：请检查项目 fonts.conf 和 ttf 目录")
    return {**os.environ, "FONTCONFIG_FILE": str(config)}
