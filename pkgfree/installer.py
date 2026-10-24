"""Combine base game, updates and DLC PKGs into shadPS4-ready folders.

Resulting layout::

    <games_dir>/<TITLE_ID>/                  base game with every update applied on top
    <addons_dir>/<TITLE_ID>/<LABEL>/         one folder per DLC (shadPS4 "addcont" folder)
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable, Optional

from .pkg import ICON0_ID, PkgError, PkgFile, PkgInfo, long_path
from .i18n import tr
from .sfo import parse_sfo

LogCallback = Callable[[str], None]
# (pkg_index, pkg_count, bytes_done, bytes_total, current_file)
InstallProgress = Callable[[int, int, int, int, str], None]


def read_info(path: str) -> PkgInfo:
    with PkgFile(path) as pkg:
        return pkg.info


def read_icon(path: str) -> Optional[bytes]:
    """icon0.png of a PKG, if present."""
    try:
        with PkgFile(path) as pkg:
            return pkg.read_entry(ICON0_ID)
    except (PkgError, OSError):
        return None


def _version_key(ver: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", ver)) or (0,)


_INVALID_NAME_CHARS = re.compile(r'[<>"?*]')
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}


def safe_folder_name(title: str, fallback: str) -> str:
    """A game title usable as a folder name on Windows, Linux and macOS."""
    name = re.sub(r"[\x00-\x1f]", " ", title).replace(":", " -")
    name = re.sub(r"[/\\|]", "-", name)
    name = _INVALID_NAME_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")[:80].rstrip(". ")
    if not name:
        return fallback
    if name.upper() in _WINDOWS_RESERVED:
        name += "_"
    return name


def find_game_dir(games_dir: str, title_id: str) -> Optional[str]:
    """Folder of title_id already in games_dir: <games>/<ID> or <games>/<any name>/<ID>."""
    if not games_dir:
        return None
    direct = os.path.join(games_dir, title_id)
    if os.path.isdir(direct):
        return direct
    try:
        entries = sorted(os.scandir(games_dir), key=lambda e: e.name)
    except OSError:
        return None
    for entry in entries:
        if entry.is_dir() and os.path.isdir(os.path.join(entry.path, title_id)):
            return os.path.join(entry.path, title_id)
    return None


def installed_version(game_dir: Optional[str]) -> Optional[str]:
    """APP_VER of the game installed in game_dir, if any.

    A separate update folder next to it (as shadPS4 uses it) wins over the base folder.
    """
    if not game_dir:
        return None
    for folder in (f"{game_dir}-UPDATE", f"{game_dir}-patch", game_dir):
        sfo_path = os.path.join(folder, "sce_sys", "param.sfo")
        try:
            with open(sfo_path, "rb") as f:
                ver = parse_sfo(f.read()).get("APP_VER")
        except (OSError, ValueError):
            continue
        if ver:
            return str(ver)
    return None


def kind_label(kind: str) -> str:
    return {"game": tr("Gioco base"), "patch": tr("Aggiornamento"), "dlc": "DLC"}.get(
        kind, tr("Sconosciuto"))


def title_id_of(info: PkgInfo) -> str:
    return str(info.sfo.get("TITLE_ID") or info.title_id)


@dataclass
class TitleGroup:
    title_id: str
    base: Optional[PkgInfo] = None
    patches: list[PkgInfo] = field(default_factory=list)
    dlcs: list[PkgInfo] = field(default_factory=list)
    title_folder: bool = False

    def ordered(self) -> list[PkgInfo]:
        items = [self.base] if self.base else []
        items += sorted(self.patches, key=lambda p: _version_key(p.app_ver))
        items += self.dlcs
        return items

    @property
    def title(self) -> str:
        for info in self.ordered():
            if info.kind != "dlc" and info.title:
                return info.title
        return self.title_id

    @property
    def final_version(self) -> str:
        games = [i for i in self.ordered() if i.kind in ("game", "patch")]
        return games[-1].app_ver if games else ""

    def game_dir(self, games_dir: str) -> str:
        """Where the game goes: an existing copy wins, else <games>[/<title>]/<ID>."""
        existing = find_game_dir(games_dir, self.title_id)
        if existing:
            return existing
        if self.title_folder:
            folder = safe_folder_name(self.title, self.title_id)
            return os.path.join(games_dir, folder, self.title_id)
        return os.path.join(games_dir, self.title_id)

    def downgrade(self, games_dir: str) -> Optional[str]:
        """Message when extracting would replace an installed copy with an older version."""
        installed = installed_version(find_game_dir(games_dir, self.title_id))
        final = self.final_version
        if installed and final and _version_key(final) < _version_key(installed):
            return tr("Sul disco è già installata la versione {installed}: dopo l'estrazione il "
                      "gioco tornerebbe alla {final}.", installed=installed, final=final)
        return None

    def warnings(self, games_dir: str) -> list[str]:
        """Problems worth showing for this title (in Italian)."""
        out = []
        down = self.downgrade(games_dir)
        if down:
            out.append(down)
        elif self.patches and not self.base:
            installed = installed_version(find_game_dir(games_dir, self.title_id))
            if installed and _version_key(installed) == _version_key(self.final_version):
                out.append(tr("La versione {installed} è già installata: la patch verrà "
                              "riapplicata sopra quella esistente.", installed=installed))
        for p in self.patches:
            if p.is_delta_patch:
                out.append(tr(
                    "{name} è una patch 'delta' (incrementale): non contiene i file completi "
                    "e il risultato potrebbe non funzionare.", name=os.path.basename(p.path)))
        if self.base is None and self.patches:
            existing = find_game_dir(games_dir, self.title_id)
            if not existing or not os.path.isfile(os.path.join(existing, "eboot.bin")):
                out.append(tr(
                    "Manca il gioco base e nella destinazione non c'è già una cartella "
                    "{title_id}: l'aggiornamento verrà estratto da solo.", title_id=self.title_id))
        return out


@dataclass
class Plan:
    groups: dict[str, TitleGroup] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    downgrades: list[str] = field(default_factory=list)

    def all_items(self) -> list[PkgInfo]:
        return [i for g in self.groups.values() for i in g.ordered()]

    def target_dir(self, info: PkgInfo, games_dir: str, addons_dir: str,
                   separate_update: bool) -> str:
        group = self.groups[title_id_of(info)]
        return target_dir(info, games_dir, addons_dir, separate_update, group.game_dir(games_dir))


def build_plan(infos: list[PkgInfo], games_dir: str, title_folder: bool = False) -> Plan:
    """Group PKGs by game. title_folder: put new games in <games>/<title>/<ID>."""
    plan = Plan()
    for info in infos:
        tid = title_id_of(info)
        group = plan.groups.setdefault(tid, TitleGroup(tid, title_folder=title_folder))
        kind = info.kind
        name = os.path.basename(info.path)
        if kind == "game":
            if group.base is not None:
                raise PkgError(tr("Più di un gioco base per {tid}: {name}", tid=tid, name=name))
            group.base = info
        elif kind == "patch":
            group.patches.append(info)
        elif kind == "dlc":
            group.dlcs.append(info)
        else:
            raise PkgError(tr("Tipo di PKG non riconosciuto ({category}): {name}",
                                  category=info.category or "?", name=name))

    for tid, group in plan.groups.items():
        plan.warnings += [f"{tid}: {w}" for w in group.warnings(games_dir)]
        down = group.downgrade(games_dir)
        if down:
            plan.downgrades.append(f"{tid}: {down}")
    return plan


def target_dir(info: PkgInfo, games_dir: str, addons_dir: str, separate_update: bool,
               game_dir: Optional[str] = None) -> str:
    """Destination of one PKG. DLC always use shadPS4's <addons>/<ID>/<label> layout."""
    tid = title_id_of(info)
    if info.kind == "dlc":
        label = info.entitlement_label or info.content_id
        return os.path.join(addons_dir, tid, label)
    game_dir = game_dir or os.path.join(games_dir, tid)
    if info.kind == "patch" and separate_update:
        return f"{game_dir}-UPDATE"
    return game_dir


# -- library ---------------------------------------------------------------------

@dataclass
class LibraryEntry:
    title: str
    title_id: str
    path: str                  # the game folder
    version: str               # installed APP_VER, update folder included
    update_dir: Optional[str]  # separate <game>-UPDATE / -patch folder, if any
    icon: Optional[str]        # path of icon0.png
    dlcs: list[str] = field(default_factory=list)


def _read_sfo_file(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            return parse_sfo(f.read())
    except (OSError, ValueError):
        return {}


def scan_library(games_dir: str, addons_dir: str, max_depth: int = 2) -> list[LibraryEntry]:
    """Games already extracted in games_dir (up to max_depth folders down)."""
    found: list[LibraryEntry] = []

    def visit(folder: str, depth: int) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name.lower())
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.name.endswith(("-UPDATE", "-patch")):
                continue
            sfo_path = os.path.join(entry.path, "sce_sys", "param.sfo")
            if os.path.isfile(os.path.join(entry.path, "eboot.bin")) and os.path.isfile(sfo_path):
                found.append(_library_entry(entry.path, addons_dir))
            elif depth < max_depth:
                visit(entry.path, depth + 1)

    if games_dir and os.path.isdir(games_dir):
        visit(games_dir, 1)
    found.sort(key=lambda e: (e.title.lower(), e.title_id))
    return found


def _library_entry(path: str, addons_dir: str) -> LibraryEntry:
    update_dir = next((d for d in (f"{path}-UPDATE", f"{path}-patch")
                       if os.path.isfile(os.path.join(d, "sce_sys", "param.sfo"))), None)
    base_sfo = _read_sfo_file(os.path.join(path, "sce_sys", "param.sfo"))
    sfo = _read_sfo_file(os.path.join(update_dir, "sce_sys", "param.sfo")) if update_dir else {}
    title_id = str(base_sfo.get("TITLE_ID") or os.path.basename(path))
    title = str(sfo.get("TITLE") or base_sfo.get("TITLE") or title_id)
    icon = None
    for folder in filter(None, (update_dir, path)):
        candidate = os.path.join(folder, "sce_sys", "icon0.png")
        if os.path.isfile(candidate):
            icon = candidate
            break
    dlcs = []
    dlc_root = os.path.join(addons_dir, title_id) if addons_dir else ""
    if dlc_root and os.path.isdir(dlc_root):
        for entry in sorted(os.scandir(dlc_root), key=lambda e: e.name):
            if entry.is_dir():
                dlc_sfo = _read_sfo_file(os.path.join(entry.path, "sce_sys", "param.sfo"))
                dlcs.append(str(dlc_sfo.get("TITLE") or entry.name))
    return LibraryEntry(title, title_id, path, installed_version(path) or "", update_dir,
                        icon, dlcs)


# -- resuming ------------------------------------------------------------------

JOURNAL_COMPLETE = "COMPLETE"


def plan_signature(plan: Plan) -> list:
    """Identifies a plan, so a resume only happens for the same set of PKGs."""
    sig = []
    for info in plan.all_items():
        try:
            size = os.path.getsize(info.path)
        except OSError:
            size = -1
        sig.append([os.path.basename(info.path), size])
    return sig


def journal_path(dest: str, info: PkgInfo) -> str:
    ver = info.app_ver or info.version or "0"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{info.content_id}-{ver}")
    return os.path.join(dest, f".pkgfree-{name}.resume")


@dataclass
class JournalState:
    signature: list
    done: set
    complete: bool


def read_journal(path: str) -> Optional[JournalState]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        header = json.loads(lines[0])
    except (OSError, ValueError, IndexError):
        return None
    done = {line[2:] for line in lines[1:] if line.startswith("F ")}
    return JournalState(header.get("plan", []), done, JOURNAL_COMPLETE in lines[1:])


class Journal:
    """Append-only record of the files of one PKG already written to disk."""

    def __init__(self, path: str, signature: list, keep: bool):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        if keep and os.path.exists(path):
            self._f = open(path, "a", encoding="utf-8")
        else:
            self._f = open(path, "w", encoding="utf-8")
            self._f.write(json.dumps({"plan": signature}) + "\n")
            self._f.flush()

    def file_done(self, rel_path: str) -> None:
        self._f.write(f"F {rel_path}\n")
        self._f.flush()

    def complete(self) -> None:
        self._f.write(JOURNAL_COMPLETE + "\n")
        self._f.close()

    def close(self) -> None:
        if not self._f.closed:
            self._f.close()


# -- free space ------------------------------------------------------------------

@dataclass
class SpaceShortage:
    path: str     # a folder on the disk that is too small
    needed: int   # bytes the extraction will add
    free: int     # bytes currently free


def _existing_ancestor(path: str) -> str:
    path = os.path.abspath(path)
    while not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def space_needed(plan: Plan, games_dir: str, addons_dir: str,
                 separate_update: bool) -> dict:
    """Bytes each destination disk must gain: {folder on that disk: bytes}.

    Files written twice (an update replacing a base file) count once, with their
    final size; files already on disk count only for the size difference.
    """
    final_sizes: dict[str, int] = {}
    for info in plan.all_items():
        dest = plan.target_dir(info, games_dir, addons_dir, separate_update)
        with PkgFile(info.path) as pkg:
            for node in pkg.list_files():
                if not node.is_dir:
                    final_sizes[os.path.join(dest, *node.path.split("/"))] = node.size
    per_disk: dict = {}
    for target, size in final_sizes.items():
        try:
            size -= os.path.getsize(long_path(target))
        except OSError:
            pass
        anchor = _existing_ancestor(os.path.dirname(target))
        try:
            dev = os.stat(anchor).st_dev
        except OSError:
            dev = anchor
        entry = per_disk.setdefault(dev, [anchor, 0])
        entry[1] += max(size, 0)
    return {anchor: needed for anchor, needed in per_disk.values()}


def check_space(plan: Plan, games_dir: str, addons_dir: str,
                separate_update: bool) -> list[SpaceShortage]:
    shortages = []
    for anchor, needed in space_needed(plan, games_dir, addons_dir, separate_update).items():
        free = shutil.disk_usage(anchor).free
        if needed > free:
            shortages.append(SpaceShortage(anchor, needed, free))
    return shortages


# -- extraction -------------------------------------------------------------------

def install(
    plan: Plan,
    games_dir: str,
    addons_dir: str,
    separate_update: bool = False,
    log: LogCallback = print,
    progress: Optional[InstallProgress] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    item_status: Optional[Callable[[int, str], None]] = None,
    resume: bool = True,
    verify: bool = False,
    verify_progress: Optional[Callable[[int, int, int], None]] = None,
    remove_pkg: Optional[Callable[[str], None]] = None,
) -> None:
    """Extract every PKG of the plan.

    item_status(index, state) reports "verify", "start", "skipped" and "done".
    resume: continue an interrupted run of the same plan (see Journal).
    verify: check the PKG digests first (verify_progress(index, done, total)).
    remove_pkg: called for each PKG once the whole plan succeeded.
    """
    items = plan.all_items()
    signature = plan_signature(plan)
    dests = [plan.target_dir(i, games_dir, addons_dir, separate_update) for i in items]
    journals = [journal_path(d, i) for d, i in zip(dests, items)]

    states: list[Optional[JournalState]] = []
    for jpath in journals:
        state = read_journal(jpath) if resume else None
        if state and state.signature != signature:
            state = None
        states.append(state)
    # Only a leading run of finished PKGs is skipped: the interrupted run stopped after them.
    skip_upto = 0
    while skip_upto < len(items) and states[skip_upto] and states[skip_upto].complete:
        skip_upto += 1

    for idx, (info, dest, jpath) in enumerate(zip(items, dests, journals)):
        label = kind_label(info.kind)
        ver = info.app_ver or info.version
        log(f"[{idx + 1}/{len(items)}] {label} {title_id_of(info)} v{ver}: "
            f"{os.path.basename(info.path)}")
        log(f"    -> {dest}")
        if idx < skip_upto:
            log("    " + tr("già estratto nell'esecuzione interrotta: saltato"))
            if item_status:
                item_status(idx, "skipped")
            continue

        def cb(done: int, total: int, name: str, _i=idx) -> None:
            if progress:
                progress(_i, len(items), done, total, name)

        with PkgFile(info.path) as pkg:
            if verify:
                if item_status:
                    item_status(idx, "verify")
                results = pkg.verify(
                    (lambda d, t, _i=idx: verify_progress(_i, d, t)) if verify_progress else None,
                    should_cancel)
                bad = [r.name for r in results if r.status == "mismatch"]
                if bad:
                    raise PkgError(tr(
                        "{name} è danneggiato: le impronte SHA-256 ({digests}) non "
                        "corrispondono. Scaricalo di nuovo.",
                        name=os.path.basename(info.path), digests=", ".join(bad)))
                if all(r.status == "absent" for r in results):
                    log("    " + tr("verifica: il PKG non contiene impronte, non verificabile"))
                else:
                    log("    " + tr("verifica integrità: OK"))
            if item_status:
                item_status(idx, "start")
            state = states[idx]
            partial = state is not None and not state.complete
            journal = Journal(jpath, signature, keep=partial)
            try:
                if pkg.has_pfs:
                    skipped = pkg.extract(dest, cb, should_cancel,
                                          skip=state.done if partial else None,
                                          on_file_done=journal.file_done)
                    if skipped:
                        log("    " + tr("ripresa: {size:.1f} GB già estratti, saltati",
                                               size=skipped / (1 << 30)))
                else:
                    os.makedirs(dest, exist_ok=True)
                    pkg.extract_sce_sys(dest)
                    log("    " + tr("(nessun file di gioco: solo licenza/metadati)"))
                journal.complete()
            finally:
                journal.close()
        if item_status:
            item_status(idx, "done")

    for jpath in journals:
        try:
            os.remove(jpath)
        except OSError:
            pass
    if remove_pkg:
        for info in items:
            try:
                remove_pkg(info.path)
                log(tr("Rimosso {name}", name=os.path.basename(info.path)))
            except OSError as ex:
                log(tr("Impossibile rimuovere {name}: {error}",
                       name=os.path.basename(info.path), error=ex))
    log(tr("Completato."))
