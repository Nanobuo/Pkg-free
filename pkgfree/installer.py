"""Combine base game, updates and DLC PKGs into shadPS4-ready folders.

Resulting layout::

    <games_dir>/<TITLE_ID>/                  base game with every update applied on top
    <addons_dir>/<TITLE_ID>/<LABEL>/         one folder per DLC (shadPS4 "addcont" folder)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .pkg import ICON0_ID, PkgError, PkgFile, PkgInfo
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


def installed_version(games_dir: str, title_id: str) -> Optional[str]:
    """APP_VER of the copy of title_id already in games_dir, if any.

    A separate update folder (as shadPS4 uses it) wins over the base folder.
    """
    if not games_dir:
        return None
    for folder in (f"{title_id}-UPDATE", f"{title_id}-patch", title_id):
        sfo_path = os.path.join(games_dir, folder, "sce_sys", "param.sfo")
        try:
            with open(sfo_path, "rb") as f:
                ver = parse_sfo(f.read()).get("APP_VER")
        except (OSError, ValueError):
            continue
        if ver:
            return str(ver)
    return None


def title_id_of(info: PkgInfo) -> str:
    return str(info.sfo.get("TITLE_ID") or info.title_id)


@dataclass
class TitleGroup:
    title_id: str
    base: Optional[PkgInfo] = None
    patches: list[PkgInfo] = field(default_factory=list)
    dlcs: list[PkgInfo] = field(default_factory=list)

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

    def downgrade(self, games_dir: str) -> Optional[str]:
        """Message when extracting would replace an installed copy with an older version."""
        installed = installed_version(games_dir, self.title_id)
        final = self.final_version
        if installed and final and _version_key(final) < _version_key(installed):
            return (f"Sul disco è già installata la versione {installed}: dopo l'estrazione il "
                    f"gioco tornerebbe alla {final}.")
        return None

    def warnings(self, games_dir: str) -> list[str]:
        """Problems worth showing for this title (in Italian)."""
        out = []
        down = self.downgrade(games_dir)
        if down:
            out.append(down)
        elif self.patches and not self.base:
            installed = installed_version(games_dir, self.title_id)
            if installed and _version_key(installed) == _version_key(self.final_version):
                out.append(f"La versione {installed} è già installata: la patch verrà "
                           "riapplicata sopra quella esistente.")
        for p in self.patches:
            if p.is_delta_patch:
                out.append(
                    f"{os.path.basename(p.path)} è una patch 'delta' (incrementale): non "
                    "contiene i file completi e il risultato potrebbe non funzionare."
                )
        if self.base is None and self.patches:
            if not os.path.isfile(os.path.join(games_dir, self.title_id, "eboot.bin")):
                out.append(
                    f"Manca il gioco base e non esiste già una cartella {self.title_id} nella "
                    "destinazione: l'aggiornamento verrà estratto da solo."
                )
        return out


@dataclass
class Plan:
    groups: dict[str, TitleGroup] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    downgrades: list[str] = field(default_factory=list)

    def all_items(self) -> list[PkgInfo]:
        return [i for g in self.groups.values() for i in g.ordered()]


def build_plan(infos: list[PkgInfo], games_dir: str) -> Plan:
    plan = Plan()
    for info in infos:
        tid = title_id_of(info)
        group = plan.groups.setdefault(tid, TitleGroup(tid))
        kind = info.kind
        name = os.path.basename(info.path)
        if kind == "game":
            if group.base is not None:
                raise PkgError(f"Più di un gioco base per {tid}: {name}")
            group.base = info
        elif kind == "patch":
            group.patches.append(info)
        elif kind == "dlc":
            group.dlcs.append(info)
        else:
            raise PkgError(f"Tipo di PKG non riconosciuto ({info.category or '?'}): {name}")

    for tid, group in plan.groups.items():
        plan.warnings += [f"{tid}: {w}" for w in group.warnings(games_dir)]
        down = group.downgrade(games_dir)
        if down:
            plan.downgrades.append(f"{tid}: {down}")
    return plan


def target_dir(info: PkgInfo, games_dir: str, addons_dir: str, separate_update: bool) -> str:
    tid = title_id_of(info)
    if info.kind == "dlc":
        label = info.entitlement_label or info.content_id
        return os.path.join(addons_dir, tid, label)
    if info.kind == "patch" and separate_update:
        return os.path.join(games_dir, f"{tid}-UPDATE")
    return os.path.join(games_dir, tid)


def install(
    plan: Plan,
    games_dir: str,
    addons_dir: str,
    separate_update: bool = False,
    log: LogCallback = print,
    progress: Optional[InstallProgress] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    item_status: Optional[Callable[[int, str], None]] = None,
) -> None:
    """Extract every PKG of the plan. item_status(index, "start"|"done") marks each step."""
    items = plan.all_items()
    for idx, info in enumerate(items):
        dest = target_dir(info, games_dir, addons_dir, separate_update)
        label = {"game": "Gioco base", "patch": "Aggiornamento", "dlc": "DLC"}[info.kind]
        ver = info.app_ver or info.version
        log(f"[{idx + 1}/{len(items)}] {label} {title_id_of(info)} v{ver}: "
            f"{os.path.basename(info.path)}")
        log(f"    -> {dest}")

        def cb(done: int, total: int, name: str, _i=idx) -> None:
            if progress:
                progress(_i, len(items), done, total, name)

        if item_status:
            item_status(idx, "start")
        with PkgFile(info.path) as pkg:
            if pkg.has_pfs:
                pkg.extract(dest, cb, should_cancel)
            else:
                os.makedirs(dest, exist_ok=True)
                pkg.extract_sce_sys(dest)
                log("    (nessun file di gioco: solo licenza/metadati)")
        if item_status:
            item_status(idx, "done")
    log("Completato.")
