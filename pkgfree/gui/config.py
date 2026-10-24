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
    verifyPkgs = ConfigItem("Extraction", "VerifyPkgs", False, BoolValidator())
    deletePkgs = ConfigItem("Extraction", "DeletePkgs", False, BoolValidator())
    notifyDone = ConfigItem("Extraction", "NotifyDone", True, BoolValidator())
    checkUpdates = ConfigItem("Updates", "CheckAtStartup", True, BoolValidator())
    language = OptionsConfigItem("General", "Language", "auto",
                                 OptionsValidator(["auto", "it", "en"]), restart=True)

    def addons_dir_for(self, games_dir: str) -> str:
        return self.get(self.addonsDir) or os.path.join(games_dir, "addcont")


cfg = Config()


def load_config() -> None:
    qconfig.load(config_path(), cfg)
