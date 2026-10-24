"""'Libreria' page: games already extracted in the games folder."""

from __future__ import annotations


from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, IconWidget, ImageLabel,
                            PushButton, ScrollArea, SimpleCardWidget, StrongBodyLabel,
                            TitleLabel, ToolTipFilter, TransparentToolButton)

from .. import installer
from ..i18n import tr
from .config import cfg
from .widgets import elastic, secondary


class GameRow(SimpleCardWidget):
    def __init__(self, entry: installer.LibraryEntry, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)
        pix = QPixmap(entry.icon) if entry.icon else QPixmap()
        if not pix.isNull():
            img = ImageLabel(pix, self)
            img.scaledToHeight(52)
            img.setBorderRadius(4, 4, 4, 4)
            lay.addWidget(img)
        else:
            icon = IconWidget(FluentIcon.GAME, self)
            icon.setFixedSize(52, 52)
            lay.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(StrongBodyLabel(entry.title, self))
        parts = [entry.title_id]
        if entry.version:
            parts.append(f"v{entry.version}")
        if entry.update_dir:
            parts.append(tr("aggiornamento separato"))
        if entry.dlcs:
            parts.append("1 DLC" if len(entry.dlcs) == 1 else f"{len(entry.dlcs)} DLC")
        info = secondary(CaptionLabel(" · ".join(parts), self))
        if entry.dlcs:
            info.setToolTip("DLC: " + ", ".join(entry.dlcs))
            info.installEventFilter(ToolTipFilter(info))
        col.addWidget(info)
        col.addWidget(elastic(secondary(CaptionLabel(entry.path, self))))
        lay.addLayout(col, 1)

        btn = TransparentToolButton(FluentIcon.FOLDER, self)
        btn.setToolTip(tr("Apri la cartella del gioco"))
        btn.installEventFilter(ToolTipFilter(btn))
        btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(entry.path)))
        lay.addWidget(btn)


class LibraryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("libraryPage")
        self.rows: list[QWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view = QWidget()
        view.setObjectName("libraryView")
        view.setStyleSheet("#libraryView{background: transparent}")
        scroll.setWidget(view)
        outer.addWidget(scroll)

        self.body = QVBoxLayout(view)
        self.body.setContentsMargins(36, 24, 36, 24)
        self.body.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(TitleLabel(tr("Libreria"), view))
        self.summary = secondary(BodyLabel("", view))
        titles.addWidget(elastic(self.summary))
        head.addLayout(titles, 1)
        refresh = PushButton(FluentIcon.SYNC, tr("Aggiorna"), view)
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh, 0, Qt.AlignTop)
        self.body.addLayout(head)
        self.list = QVBoxLayout()
        self.list.setSpacing(6)
        self.body.addLayout(self.list)
        self.body.addStretch(1)

    def refresh(self) -> None:
        for row in self.rows:
            self.list.removeWidget(row)
            row.deleteLater()
        self.rows = []
        games = cfg.get(cfg.gamesDir)
        if not games:
            self.summary.setText(tr("Scegli la cartella dei giochi nella pagina Estrai o nelle "
                                    "Impostazioni."))
            return
        addons = cfg.addons_dir_for(games)
        entries = installer.scan_library(games, addons)
        if not entries:
            self.summary.setText(tr("Nessun gioco estratto in {folder}", folder=games))
        else:
            n = len(entries)
            self.summary.setText(tr("{n} giochi in {folder}", n=n, folder=games) if n != 1
                                 else tr("1 gioco in {folder}", folder=games))
        for entry in entries:
            row = GameRow(entry, self)
            self.list.addWidget(row)
            self.rows.append(row)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
