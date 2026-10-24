"""'Impostazioni' and 'Registro' pages."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, HyperlinkCard, OptionsSettingCard, PlainTextEdit,
                            PushSettingCard, ScrollArea, SettingCardGroup, SwitchSettingCard,
                            TitleLabel)

from .. import __version__
from .config import cfg

REPO_URL = "https://github.com/nanobuo/pkg-free"


class ItalianSwitchSettingCard(SwitchSettingCard):
    """SwitchSettingCard writes "On"/"Off" on every change; show Italian labels instead."""

    def setValue(self, isChecked: bool):
        super().setValue(isChecked)
        self.switchButton.setText("Attivo" if isChecked else "Disattivo")


class SettingsPage(QWidget):
    checkUpdatesRequested = Signal()

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
        paths.addSettingCard(self.gamesCard)
        paths.addSettingCard(self.addonsCard)
        lay.addWidget(paths)

        extraction = SettingCardGroup("Estrazione", view)
        self.mergeCard = self._switch(
            extraction, cfg.mergeUpdates, FluentIcon.SYNC, "Unisci gli aggiornamenti al gioco",
            "Se disattivato, gli aggiornamenti vengono estratti a parte in <TITLE_ID>-UPDATE")
        self.titleCard = self._switch(
            extraction, cfg.titleFolder, FluentIcon.TAG, "Cartella con il nome del gioco",
            "Es. Giochi\\Driveclub\\CUSA00003: shadPS4 trova il gioco anche nella sottocartella. "
            "I DLC restano in addcont\\<TITLE_ID>.")
        self.verifyCard = self._switch(
            extraction, cfg.verifyPkgs, FluentIcon.CERTIFICATE, "Verifica i PKG prima di estrarli",
            "Controlla le impronte SHA-256 per scoprire download danneggiati. Rilegge tutto il "
            "PKG: circa un minuto in più ogni 50 GB.")
        self.deleteCard = self._switch(
            extraction, cfg.deletePkgs, FluentIcon.DELETE, "Sposta i PKG nel Cestino al termine",
            "Solo se l'estrazione di tutti i PKG è riuscita.")
        self.notifyCard = self._switch(
            extraction, cfg.notifyDone, FluentIcon.RINGER, "Notifica a fine estrazione",
            "Mostra una notifica di sistema se nel frattempo stai usando un'altra finestra.")
        lay.addWidget(extraction)

        look = SettingCardGroup("Aspetto", view)
        self.themeCard = OptionsSettingCard(
            cfg.themeMode, FluentIcon.BRUSH, "Tema", "Chiaro, scuro o come Windows",
            texts=["Chiaro", "Scuro", "Usa impostazione di sistema"], parent=look)
        self.languageCard = OptionsSettingCard(
            cfg.language, FluentIcon.LANGUAGE, "Lingua", "Si applica al prossimo avvio",
            texts=["Automatica (lingua del sistema)", "Italiano", "English"], parent=look)
        look.addSettingCard(self.themeCard)
        look.addSettingCard(self.languageCard)
        lay.addWidget(look)

        updates = SettingCardGroup("Aggiornamenti", view)
        self.updateSwitch = self._switch(
            updates, cfg.checkUpdates, FluentIcon.UPDATE, "Controlla gli aggiornamenti all'avvio",
            "Cerca una nuova versione su GitHub quando apri il programma.")
        self.updateCard = PushSettingCard("Controlla ora", FluentIcon.SYNC, "Versione installata",
                                          f"PKG Free {__version__}", updates)
        self.updateCard.clicked.connect(self.checkUpdatesRequested)
        updates.addSettingCard(self.updateCard)
        lay.addWidget(updates)

        about = SettingCardGroup("Informazioni", view)
        about.addSettingCard(HyperlinkCard(
            REPO_URL, "Codice sorgente", FluentIcon.INFO, "PKG Free",
            f"Versione {__version__} · GPL-3.0 · supporta solo PKG fake (fPKG)", about))
        lay.addWidget(about)
        lay.addStretch(1)

        cfg.gamesDir.valueChanged.connect(lambda _: self._refresh())
        cfg.addonsDir.valueChanged.connect(lambda _: self._refresh())
        self._refresh()

    @staticmethod
    def _switch(group, item, icon, title, content):
        card = ItalianSwitchSettingCard(icon, title, content, configItem=item, parent=group)
        card.setValue(cfg.get(item))
        group.addSettingCard(card)
        return card

    def set_update_status(self, text: str) -> None:
        self.updateCard.setContent(text)

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
