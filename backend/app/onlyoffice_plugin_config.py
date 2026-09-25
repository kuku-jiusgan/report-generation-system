from .config import Settings


PLUGIN_GUID = "asc.{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"
PLUGIN_PATH = "%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=26"


def editor_plugins(settings: Settings) -> dict[str, list[str]]:
    return {
        "autostart": [PLUGIN_GUID],
        "pluginsData": [f"{settings.onlyoffice_url}/sdkjs-plugins/{PLUGIN_PATH}"],
    }
