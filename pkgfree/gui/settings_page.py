"""'Impostazioni' and 'Registro' pages."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, HyperlinkCard, OptionsSettingCard, PlainTextEdit,
                            PushSettingCard, ScrollArea, SettingCardGroup, SwitchSettingCard,
                            TitleLabel)

from .. import __version__
from .config import cfg

REPO_URL = "https://github.com/nanobuo/pkg-free"


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view = QWidget()
        view.setObjectName("settingsView")
        view.setStyleSheet("#settingsView{background: transparent}")
        scroll.setWidget(view)
        outer.addWidget(scroll)

        lay = QVBoxLayout(view)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(24)
        lay.addWidget(TitleLabel("Impostazioni", view))

        paths = SettingCardGroup("Cartelle", view)
        self.gamesCard = PushSettingCard("Scegli cartella", FluentIcon.FOLDER, "Cartella giochi",
                                         "", paths)
        self.gamesCard.clicked.connect(self._choose_games)
        self.addonsCard = PushSettingCard("Scegli cartella", FluentIcon.LIBRARY, "Cartella DLC",
                                          "", paths)
        self.addonsCard.clicked.connect(self._choose_addons)
        self.mergeCard = SwitchSettingCard(
            FluentIcon.SYNC, "Unisci gli aggiornamenti al gioco",
            "Se disattivato, gli aggiornamenti vengono estratti a parte in <TITLE_ID>-UPDATE",
            configItem=cfg.mergeUpdates, parent=paths)
        self.mergeCard.switchButton.setOnText("Attivo")
        self.mergeCard.switchButton.setOffText("Disattivo")
        self.mergeCard.setValue(cfg.get(cfg.mergeUpdates))
        paths.addSettingCard(self.gamesCard)
        paths.addSettingCard(self.addonsCard)
        paths.addSettingCard(self.mergeCard)
        lay.addWidget(paths)

        look = SettingCardGroup("Aspetto", view)
        self.themeCard = OptionsSettingCard(
            cfg.themeMode, FluentIcon.BRUSH, "Tema", "Chiaro, scuro o come Windows",
            texts=["Chiaro", "Scuro", "Usa impostazione di sistema"], parent=look)
        look.addSettingCard(self.themeCard)
        lay.addWidget(look)

        about = SettingCardGroup("Informazioni", view)
        about.addSettingCard(HyperlinkCard(
            REPO_URL, "Codice sorgente", FluentIcon.INFO, "PKG Free",
            f"Versione {__version__} · GPL-3.0 · supporta solo PKG fake (fPKG)", about))
        lay.addWidget(about)
        lay.addStretch(1)

        cfg.gamesDir.valueChanged.connect(lambda _: self._refresh())
        cfg.addonsDir.valueChanged.connect(lambda _: self._refresh())
        self._refresh()

    def _refresh(self) -> None:
        games = cfg.get(cfg.gamesDir)
        self.gamesCard.setContent(games or "Non impostata")
        addons = cfg.get(cfg.addonsDir)
        if addons:
            self.addonsCard.setContent(addons)
        else:
            default = os.path.join(games, "addcont") if games else "<cartella giochi>\\addcont"
            self.addonsCard.setContent(f"Predefinita: {default}")

    def _choose_games(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Cartella dei giochi", cfg.get(cfg.gamesDir))
        if folder:
            cfg.set(cfg.gamesDir, os.path.normpath(folder))

    def _choose_addons(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Cartella DLC", cfg.get(cfg.addonsDir))
        if folder:
            cfg.set(cfg.addonsDir, os.path.normpath(folder))


class LogPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPage")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 24, 36, 24)
        lay.setSpacing(14)
        lay.addWidget(TitleLabel("Registro", self))
        self.text = PlainTextEdit(self)
        self.text.setReadOnly(True)
        font = QFont()
        font.setFamilies(["Cascadia Mono", "Consolas", "DejaVu Sans Mono"])
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(9)
        self.text.setFont(font)
        lay.addWidget(self.text, 1)

    def append(self, line: str) -> None:
        self.text.appendPlainText(line)
