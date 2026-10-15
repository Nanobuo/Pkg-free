"""'Avanzamento' page and the background extraction thread."""

from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, IconWidget, InfoBar,
                            InfoBarIcon, InfoBarPosition, LargeTitleLabel, ProgressBar,
                            ProgressRing, PushButton, ScrollArea, SimpleCardWidget, TitleLabel)

from .. import installer
from ..pkg import Cancelled, PkgError, PkgInfo
from .widgets import KIND_LABEL, elastic, fmt_size, secondary


class ExtractWorker(QThread):
    logged = Signal(str)
    progressed = Signal(int, object, object, str)  # index, done bytes, total bytes, file
    itemStatus = Signal(int, str)
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, plan, games_dir, addons_dir, separate_update, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.games_dir = games_dir
        self.addons_dir = addons_dir
        self.separate_update = separate_update
        self.cancel_event = threading.Event()
        self._last_emit = 0.0

    def cancel(self) -> None:
        self.cancel_event.set()

    def _progress(self, idx, _count, done, total, name):
        now = time.monotonic()
        if name and now - self._last_emit < 0.1:
            return
        self._last_emit = now
        self.progressed.emit(idx, done, total, name)

    def run(self) -> None:
        try:
            installer.install(
                self.plan, self.games_dir, self.addons_dir, self.separate_update,
                log=self.logged.emit, progress=self._progress,
                should_cancel=self.cancel_event.is_set, item_status=self.itemStatus.emit)
            self.succeeded.emit()
        except Cancelled:
            self.failed.emit("Operazione annullata. I file già estratti potrebbero essere incompleti.")
        except (PkgError, OSError) as ex:
            self.failed.emit(str(ex))
        except Exception as ex:  # keep the UI alive and tell the user
            self.failed.emit(f"Errore inatteso: {ex!r}")


class QueueRow(SimpleCardWidget):
    def __init__(self, info: PkgInfo, dest: str, games_dir: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(14)
        self.ring = ProgressRing(self)
        self.ring.setFixedSize(22, 22)
        self.ring.setStrokeWidth(3)
        self.ring.setTextVisible(False)
        self.icon = IconWidget(FluentIcon.STOP_WATCH, self)
        self.icon.setFixedSize(20, 20)
        self.ring.hide()
        lay.addWidget(self.ring)
        lay.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        ver = info.app_ver or info.version
        name = KIND_LABEL[info.kind]
        if info.kind == "dlc":
            name += f" {info.entitlement_label}"
        elif ver:
            name += f" v{ver}"
        col.addWidget(BodyLabel(name, self))
        size = fmt_size(os.path.getsize(info.path))
        shown = dest
        rel = os.path.relpath(dest, games_dir) if games_dir else dest
        if not rel.startswith(".."):
            shown = rel
        col.addWidget(elastic(secondary(CaptionLabel(
            f"{os.path.basename(info.path)} · {size} → {shown}", self)), dest))
        lay.addLayout(col, 1)
        self.state = secondary(BodyLabel("In attesa", self))
        lay.addWidget(self.state)

    def set_running(self, frac: float) -> None:
        self.icon.hide()
        self.ring.show()
        self.ring.setValue(int(frac * 100))
        self.state.setText(f"{int(frac * 100)}%")

    def set_done(self) -> None:
        self.ring.hide()
        self.icon.setIcon(InfoBarIcon.SUCCESS)
        self.icon.show()
        self.state.setText("Completato")

    def set_failed(self, text: str) -> None:
        self.ring.hide()
        self.icon.setIcon(InfoBarIcon.ERROR)
        self.icon.show()
        self.state.setText(text)


class ProgressPage(QWidget):
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("progressPage")
        self.rows: list[QueueRow] = []
        self.weights: list[int] = []
        self.current = -1
        self.result_bar = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view = QWidget()
        view.setObjectName("progressView")
        view.setStyleSheet("#progressView{background: transparent}")
        scroll.setWidget(view)
        outer.addWidget(scroll)

        self.body = QVBoxLayout(view)
        self.body.setContentsMargins(36, 24, 36, 24)
        self.body.setSpacing(14)
        head = QVBoxLayout()
        head.setSpacing(2)
        self.title = TitleLabel("Nessuna estrazione in corso", view)
        self.subtitle = secondary(BodyLabel("Aggiungi i PKG nella pagina Estrai e premi "
                                            "«Estrai tutto».", view))
        head.addWidget(self.title)
        head.addWidget(elastic(self.subtitle))
        self.body.addLayout(head)

        self.card = SimpleCardWidget(view)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        self.percent = LargeTitleLabel("0%", self.card)
        top.addWidget(self.percent)
        self.stats = secondary(BodyLabel("", self.card))
        top.addWidget(self.stats, 1, Qt.AlignVCenter)
        self.cancelButton = PushButton(FluentIcon.CLOSE, "Annulla", self.card)
        self.cancelButton.clicked.connect(self.cancelRequested)
        top.addWidget(self.cancelButton, 0, Qt.AlignVCenter)
        cl.addLayout(top)
        self.bar = ProgressBar(self.card)
        self.bar.setRange(0, 1000)
        cl.addWidget(self.bar)
        self.fileLabel = secondary(CaptionLabel("", self.card))
        cl.addWidget(self.fileLabel)
        self.body.addWidget(self.card)
        self.card.hide()

        self.queue = QVBoxLayout()
        self.queue.setSpacing(4)
        self.body.addLayout(self.queue)
        self.resultLayout = QVBoxLayout()
        self.body.addLayout(self.resultLayout)
        self.body.addStretch(1)

    # -- lifecycle -----------------------------------------------------------------
    def start(self, plan: installer.Plan, games_dir: str, addons_dir: str,
              separate_update: bool) -> None:
        for r in self.rows:
            self.queue.removeWidget(r)
            r.deleteLater()
        if self.result_bar:
            self.result_bar.deleteLater()
            self.result_bar = None
        items = plan.all_items()
        self.rows = []
        for info in items:
            dest = installer.target_dir(info, games_dir, addons_dir, separate_update)
            row = QueueRow(info, dest, games_dir, self)
            self.queue.addWidget(row)
            self.rows.append(row)
        self.weights = [max(os.path.getsize(i.path), 1) for i in items]
        self.games_dir = games_dir
        self.addons_dir = addons_dir
        self.current = -1
        self.base_bytes = 0
        self.item_bytes = 0
        self.started = time.monotonic()
        titles = ", ".join(g.title for g in plan.groups.values())
        self.title.setText("Estrazione in corso")
        self.subtitle.setText(f"{titles} → {games_dir}")
        self.subtitle.setToolTip(self.subtitle.text())
        self.card.show()
        self.cancelButton.setEnabled(True)
        self.cancelButton.show()
        self._set_fraction(0.0)
        self.stats.setText("Preparazione…")
        self.fileLabel.setText("")

    def _set_fraction(self, frac: float) -> None:
        self.percent.setText(f"{int(frac * 100)}%")
        self.bar.setValue(int(frac * 1000))

    def on_status(self, idx: int, state: str) -> None:
        if state == "start":
            self.current = idx
            self.base_bytes += self.item_bytes
            self.item_bytes = 0
            self.rows[idx].set_running(0.0)
        elif state == "done":
            self.rows[idx].set_done()
            self._update(idx, 1.0)

    def on_progress(self, idx: int, done, total, name: str) -> None:
        frac_item = done / total if total else 1.0
        self.item_bytes = done
        self.rows[idx].set_running(frac_item)
        if name:
            self.fileLabel.setText(f"Sto scrivendo: {name}")
        self._update(idx, frac_item)

    def _update(self, idx: int, frac_item: float) -> None:
        total_w = sum(self.weights)
        frac = (sum(self.weights[:idx]) + self.weights[idx] * frac_item) / total_w
        self._set_fraction(frac)
        elapsed = time.monotonic() - self.started
        written = self.base_bytes + self.item_bytes
        parts = [f"{fmt_size(written)} scritti"]
        if elapsed > 1:
            parts.append(f"{fmt_size(written / elapsed)}/s")
        if 0.02 < frac < 1 and elapsed > 3:
            left = elapsed * (1 - frac) / frac
            parts.append(f"circa {int(left // 60)} min {int(left % 60)} s rimanenti"
                         if left >= 60 else f"circa {int(left)} s rimanenti")
        self.stats.setText(" · ".join(parts))

    def finish(self, ok: bool, message: str = "") -> None:
        self.cancelButton.hide()
        self.fileLabel.setText("")
        if ok:
            self._set_fraction(1.0)
            self.title.setText("Estrazione completata")
            self.stats.setText(f"Tempo impiegato: {int(time.monotonic() - self.started)} s")
            bar = InfoBar(InfoBarIcon.SUCCESS, "Pronto per shadPS4",
                          "Aggiungi la cartella dei giochi in shadPS4 e imposta la cartella DLC "
                          "nelle sue impostazioni.",
                          Qt.Horizontal, isClosable=False, duration=-1,
                          position=InfoBarPosition.NONE, parent=self)
            btn = PushButton(FluentIcon.FOLDER, "Apri cartella", bar)
            btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.games_dir)))
            bar.addWidget(btn)
        else:
            self.title.setText("Estrazione interrotta")
            if 0 <= self.current < len(self.rows):
                self.rows[self.current].set_failed("Interrotto")
            bar = InfoBar(InfoBarIcon.ERROR, "Errore", message, Qt.Horizontal, isClosable=False,
                          duration=-1, position=InfoBarPosition.NONE, parent=self)
        self.result_bar = bar
        self.resultLayout.addWidget(bar)
