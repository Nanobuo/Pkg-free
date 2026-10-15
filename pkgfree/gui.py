"""Tkinter GUI."""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, installer
from .pkg import Cancelled, PkgError, PkgInfo

KIND_LABEL = {"game": "Gioco base", "patch": "Aggiornamento", "dlc": "DLC", "other": "Sconosciuto"}


def _settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "PkgFree", "settings.json")


def _load_settings() -> dict:
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_settings_path()), exist_ok=True)
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return str(n)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"PKG Free {__version__} – Estrattore PKG PS4 per shadPS4")
        self.geometry("900x620")
        self.minsize(720, 500)

        self.infos: dict[str, PkgInfo] = {}
        self.events: queue.Queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker: threading.Thread | None = None

        settings = _load_settings()
        self.games_var = tk.StringVar(value=settings.get("games_dir", ""))
        self.addons_var = tk.StringVar(value=settings.get("addons_dir", ""))
        self.separate_var = tk.BooleanVar(value=settings.get("separate_update", False))
        self.status_var = tk.StringVar(value="Aggiungi i file PKG (gioco, aggiornamenti, DLC).")
        self.last_dir = settings.get("last_dir", "")

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)

    # -- layout ----------------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        frm_list = ttk.LabelFrame(self, text="PKG da estrarre")
        frm_list.pack(fill="both", expand=True, **pad)

        cols = ("file", "tipo", "titleid", "versione", "titolo")
        self.tree = ttk.Treeview(frm_list, columns=cols, show="headings", height=8)
        for col, label, width in [("file", "File", 260), ("tipo", "Tipo", 110),
                                  ("titleid", "Title ID", 90), ("versione", "Versione", 70),
                                  ("titolo", "Titolo", 220)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        sb = ttk.Scrollbar(frm_list, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        # Pack the buttons first so the wide list cannot squeeze them.
        btns = ttk.Frame(frm_list)
        btns.pack(side="right", fill="y", padx=6, pady=6)
        sb.pack(side="right", fill="y", pady=6)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        self.btn_add = ttk.Button(btns, text="Aggiungi PKG…", command=self._add_files)
        self.btn_add_dir = ttk.Button(btns, text="Aggiungi cartella…", command=self._add_folder)
        self.btn_remove = ttk.Button(btns, text="Rimuovi", command=self._remove_selected)
        self.btn_clear = ttk.Button(btns, text="Svuota", command=self._clear)
        for b in (self.btn_add, self.btn_add_dir, self.btn_remove, self.btn_clear):
            b.configure(width=18)
            b.pack(fill="x", pady=2)

        frm_out = ttk.LabelFrame(self, text="Destinazione")
        frm_out.pack(fill="x", **pad)
        frm_out.columnconfigure(1, weight=1)
        ttk.Label(frm_out, text="Cartella giochi:").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frm_out, textvariable=self.games_var).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(frm_out, text="Sfoglia…", command=lambda: self._browse(self.games_var)).grid(
            row=0, column=2, padx=6, pady=3)
        ttk.Label(frm_out, text="Cartella DLC:").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(frm_out, textvariable=self.addons_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(frm_out, text="Sfoglia…", command=lambda: self._browse(self.addons_var)).grid(
            row=1, column=2, padx=6, pady=3)
        ttk.Label(frm_out, foreground="gray",
                  text="Se vuota: <cartella giochi>\\addcont. In shadPS4 impostala come "
                       "cartella DLC (\"addon install dir\").").grid(
            row=2, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(frm_out, variable=self.separate_var,
                        text="Non unire gli aggiornamenti: estraili in <TITLE_ID>-UPDATE").grid(
            row=3, column=0, columnspan=3, sticky="w", padx=6, pady=3)

        frm_run = ttk.Frame(self)
        frm_run.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(frm_run, maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True)
        self.btn_start = ttk.Button(frm_run, text="Estrai", command=self._start)
        self.btn_start.pack(side="left", padx=(8, 0))
        self.btn_cancel = ttk.Button(frm_run, text="Annulla", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(4, 0))
        ttk.Label(self, textvariable=self.status_var).pack(fill="x", padx=10)

        frm_log = ttk.LabelFrame(self, text="Registro")
        frm_log.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(frm_log, height=8, state="disabled", wrap="word")
        lsb = ttk.Scrollbar(frm_log, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        lsb.pack(side="left", fill="y", pady=6)

    # -- list management ---------------------------------------------------------
    def _add_paths(self, paths) -> None:
        errors = []
        for path in paths:
            path = os.path.abspath(path)
            if path in self.infos:
                continue
            try:
                info = installer.read_info(path)
            except (PkgError, OSError) as ex:
                errors.append(f"{os.path.basename(path)}: {ex}")
                continue
            self.infos[path] = info
            self.tree.insert("", "end", iid=path, values=(
                os.path.basename(path), KIND_LABEL[info.kind], installer.title_id_of(info),
                info.app_ver or info.version, info.title))
        if errors:
            messagebox.showwarning("PKG non validi", "\n".join(errors))
        if paths:
            self.last_dir = os.path.dirname(os.path.abspath(paths[0]))

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleziona i file PKG", initialdir=self.last_dir or None,
            filetypes=[("PKG PS4", "*.pkg"), ("Tutti i file", "*.*")])
        self._add_paths(list(paths))

    def _add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Cartella con file PKG",
                                         initialdir=self.last_dir or None)
        if not folder:
            return
        found = []
        for root, _dirs, files in os.walk(folder):
            found += [os.path.join(root, f) for f in files if f.lower().endswith(".pkg")]
        if not found:
            messagebox.showinfo("Nessun PKG", "Nessun file .pkg trovato nella cartella.")
        self._add_paths(sorted(found))

    def _remove_selected(self) -> None:
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.infos.pop(iid, None)

    def _clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.infos.clear()

    def _browse(self, var: tk.StringVar) -> None:
        folder = filedialog.askdirectory(initialdir=var.get() or None)
        if folder:
            var.set(os.path.normpath(folder))

    # -- running -------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for b in (self.btn_add, self.btn_add_dir, self.btn_remove, self.btn_clear, self.btn_start):
            b.configure(state=state)
        self.btn_cancel.configure(state="normal" if running else "disabled")

    def _start(self) -> None:
        if not self.infos:
            messagebox.showinfo("Nessun PKG", "Aggiungi almeno un file PKG.")
            return
        games = self.games_var.get().strip()
        if not games:
            messagebox.showinfo("Destinazione", "Scegli la cartella dei giochi.")
            return
        games = os.path.abspath(games)
        addons = os.path.abspath(self.addons_var.get().strip() or os.path.join(games, "addcont"))
        try:
            plan = installer.build_plan([self.infos[i] for i in self.tree.get_children()], games)
        except PkgError as ex:
            messagebox.showerror("Errore", str(ex))
            return
        if plan.warnings and not messagebox.askyesno(
                "Attenzione", "\n\n".join(plan.warnings) + "\n\nContinuare comunque?"):
            return
        existing = [g.title_id for g in plan.groups.values()
                    if g.base and os.path.isdir(os.path.join(games, g.title_id))]
        if existing and not messagebox.askyesno(
                "Cartella esistente",
                "Esiste già una cartella per: " + ", ".join(existing) +
                "\nI file verranno sovrascritti. Continuare?"):
            return

        _save_settings({"games_dir": games, "addons_dir": self.addons_var.get().strip(),
                        "separate_update": self.separate_var.get(), "last_dir": self.last_dir})
        self.cancel_flag.clear()
        self._set_running(True)
        self.progress["value"] = 0
        separate = self.separate_var.get()
        self.worker = threading.Thread(
            target=self._run, args=(plan, games, addons, separate), daemon=True)
        self.worker.start()

    def _run(self, plan, games, addons, separate) -> None:
        post = self.events.put
        try:
            installer.install(
                plan, games, addons, separate,
                log=lambda m: post(("log", m)),
                progress=lambda i, n, d, t, name: post(("progress", i, n, d, t, name)),
                should_cancel=self.cancel_flag.is_set,
            )
            post(("done", games, addons))
        except Cancelled:
            post(("error", "Operazione annullata. I file estratti potrebbero essere incompleti."))
        except (PkgError, OSError) as ex:
            post(("error", str(ex)))
        except Exception as ex:  # unexpected: show it instead of dying silently
            post(("error", f"Errore inatteso: {ex!r}"))

    def _poll(self) -> None:
        last_progress = None
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "log":
                    self._append_log(ev[1])
                elif kind == "progress":
                    last_progress = ev
                elif kind == "done":
                    self._set_running(False)
                    self.progress["value"] = 1000
                    self.status_var.set("Completato.")
                    messagebox.showinfo(
                        "Completato",
                        f"Estrazione completata.\n\nGiochi: {ev[1]}\nDLC: {ev[2]}\n\n"
                        "In shadPS4 aggiungi la cartella dei giochi e imposta la cartella "
                        "dei DLC nelle impostazioni.")
                elif kind == "error":
                    self._set_running(False)
                    self._append_log("ERRORE: " + ev[1])
                    self.status_var.set("Errore.")
                    messagebox.showerror("Errore", ev[1])
        except queue.Empty:
            pass
        if last_progress:
            _, i, n, done, total, name = last_progress
            frac = (i + (done / total if total else 1)) / max(n, 1)
            self.progress["value"] = int(frac * 1000)
            self.status_var.set(
                f"PKG {i + 1}/{n} – {_fmt_size(done)} / {_fmt_size(total)}  {name}")
        self.after(100, self._poll)

    def _cancel(self) -> None:
        self.cancel_flag.set()
        self.status_var.set("Annullamento…")

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Uscire?", "Estrazione in corso. Interrompere e uscire?"):
                return
            self.cancel_flag.set()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()
