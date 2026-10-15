"""Main window: Fluent navigation with Estrai / Avanzamento / Registro / Impostazioni."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize
from qfluentwidgets import (FluentIcon, FluentWindow, InfoBar, InfoBarPosition, MessageBox,
                            NavigationItemPosition, Theme, isDarkTheme)

from .. import __version__
from ..pkg import PkgError
from .config import cfg
from .extract_page import ExtractPage
from .progress_page import ExtractWorker, ProgressPage
from .settings_page import LogPage, SettingsPage


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.worker: ExtractWorker | None = None
        self.setWindowTitle("PKG Free")
        self.setWindowIcon(FluentIcon.GAME.icon())
        self.resize(1120, 780)
        self.setMinimumSize(QSize(900, 620))

        self.extractPage = ExtractPage(self)
        self.progressPage = ProgressPage(self)
        self.logPage = LogPage(self)
        self.settingsPage = SettingsPage(self)

        self.addSubInterface(self.extractPage, FluentIcon.DOWNLOAD, "Estrai")
        self.addSubInterface(self.progressPage, FluentIcon.SPEED_HIGH, "Avanzamento")
        self.addSubInterface(self.logPage, FluentIcon.DOCUMENT, "Registro")
        self.navigationInterface.addItem(
            "themeToggle", FluentIcon.CONSTRACT, "Cambia tema", onClick=self.toggle_theme,
            selectable=False, position=NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.settingsPage, FluentIcon.SETTING, "Impostazioni",
                             NavigationItemPosition.BOTTOM)

        self.extractPage.startRequested.connect(self.start_extraction)
        self.progressPage.cancelRequested.connect(self.cancel_extraction)
        self.logPage.append(f"PKG Free {__version__}")

    # -- theme -----------------------------------------------------------------------
    def toggle_theme(self) -> None:
        cfg.set(cfg.themeMode, Theme.LIGHT if isDarkTheme() else Theme.DARK)

    # -- extraction --------------------------------------------------------------------
    def start_extraction(self) -> None:
        games = cfg.get(cfg.gamesDir)
        if not games and not self.extractPage.choose_games_dir():
            return
        games = os.path.abspath(cfg.get(cfg.gamesDir))
        addons = os.path.abspath(cfg.addons_dir_for(games))
        try:
            plan = self.extractPage.plan()
        except PkgError as ex:
            InfoBar.error("Impossibile procedere", str(ex), duration=6000,
                          position=InfoBarPosition.TOP_RIGHT, parent=self)
            return
        existing = [g.title_id for g in plan.groups.values()
                    if g.base and os.path.isdir(os.path.join(games, g.title_id))]
        if existing:
            box = MessageBox("Cartella già esistente",
                             "Esiste già una cartella per " + ", ".join(existing) +
                             ". I file con lo stesso nome verranno sovrascritti. Continuare?", self)
            box.yesButton.setText("Continua")
            box.cancelButton.setText("Annulla")
            if not box.exec():
                return

        separate = not cfg.get(cfg.mergeUpdates)
        self.worker = ExtractWorker(plan, games, addons, separate, self)
        self.worker.logged.connect(self.logPage.append)
        self.worker.progressed.connect(self.progressPage.on_progress)
        self.worker.itemStatus.connect(self.progressPage.on_status)
        self.worker.succeeded.connect(lambda: self._finished(True, ""))
        self.worker.failed.connect(lambda msg: self._finished(False, msg))
        self.progressPage.start(plan, games, addons, separate)
        self.extractPage.set_busy(True)
        self.switchTo(self.progressPage)
        self.worker.start()

    def cancel_extraction(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.progressPage.cancelButton.setEnabled(False)
            self.progressPage.stats.setText("Annullamento…")

    def _finished(self, ok: bool, message: str) -> None:
        self.progressPage.finish(ok, message)
        self.extractPage.set_busy(False)
        self.extractPage.refresh()
        if not ok:
            self.logPage.append("ERRORE: " + message)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            box = MessageBox("Estrazione in corso", "Vuoi interrompere l'estrazione e uscire?", self)
            box.yesButton.setText("Interrompi ed esci")
            box.cancelButton.setText("Continua")
            if not box.exec():
                e.ignore()
                return
            self.worker.cancel()
            self.worker.wait(10000)
        super().closeEvent(e)
