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

from .pkg import PkgError, PkgFile, PkgInfo

LogCallback = Callable[[str], None]
# (pkg_index, pkg_count, bytes_done, bytes_total, current_file)
InstallProgress = Callable[[int, int, int, int, str], None]


def read_info(path: str) -> PkgInfo:
    with PkgFile(path) as pkg:
        return pkg.info


def _version_key(ver: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", ver)) or (0,)


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


@dataclass
class Plan:
    groups: dict[str, TitleGroup] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

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
            if info.is_delta_patch:
                plan.warnings.append(
                    f"{name}: è una patch 'delta' (incrementale). Non contiene i file completi "
                    "e il risultato potrebbe non funzionare."
                )
        elif kind == "dlc":
            group.dlcs.append(info)
        else:
            raise PkgError(f"Tipo di PKG non riconosciuto ({info.category or '?'}): {name}")

    for tid, group in plan.groups.items():
        if group.base is None and group.patches:
            if not os.path.isfile(os.path.join(games_dir, tid, "eboot.bin")):
                plan.warnings.append(
                    f"{tid}: nessun gioco base selezionato e nessuna cartella esistente in "
                    f"'{games_dir}'. L'aggiornamento verrà estratto da solo."
                )
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
) -> None:
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

        with PkgFile(info.path) as pkg:
            if pkg.has_pfs:
                pkg.extract(dest, cb, should_cancel)
            else:
                os.makedirs(dest, exist_ok=True)
                pkg.extract_sce_sys(dest)
                log("    (nessun file di gioco: solo licenza/metadati)")
    log("Completato.")
