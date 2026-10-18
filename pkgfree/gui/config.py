"""Persistent settings (stored as JSON in %APPDATA%\\PkgFree)."""

import os

from qfluentwidgets import (BoolValidator, ConfigItem, EnumSerializer, OptionsConfigItem,
                            OptionsValidator, QConfig, Theme, qconfig)


def config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "PkgFree", "config.json")


class Config(QConfig):
    themeMode = OptionsConfigItem(
        "QFluentWidgets", "ThemeMode", Theme.AUTO, OptionsValidator(Theme), EnumSerializer(Theme))
    gamesDir = ConfigItem("Paths", "GamesDir", "")
    addonsDir = ConfigItem("Paths", "AddonsDir", "")
    lastDir = ConfigItem("Paths", "LastDir", "")
    mergeUpdates = ConfigItem("Extraction", "MergeUpdates", True, BoolValidator())
    titleFolder = ConfigItem("Extraction", "TitleFolder", True, BoolValidator())

    def addons_dir_for(self, games_dir: str) -> str:
        return self.get(self.addonsDir) or os.path.join(games_dir, "addcont")


cfg = Config()


def load_config() -> None:
    qconfig.load(config_path(), cfg)
