"""Command line interface."""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__, installer
from .pkg import Cancelled, PkgError, PkgFile

KIND_LABEL = {"game": "Gioco base", "patch": "Aggiornamento", "dlc": "DLC", "other": "Sconosciuto"}


def _cmd_info(args) -> int:
    for path in args.pkg:
        with PkgFile(path) as pkg:
            i = pkg.info
            print(f"{path}")
            print(f"  Tipo:       {KIND_LABEL[i.kind]} ({i.category})")
            print(f"  Content ID: {i.content_id}")
            print(f"  Title ID:   {installer.title_id_of(i)}")
            print(f"  Titolo:     {i.title}")
            print(f"  Versione:   {i.app_ver or i.version}")
            if args.debug:
                print(f"  PFS:        offset=0x{i.pfs_image_offset:X} size=0x{i.pfs_image_size:X} "
                      f"flags=0x{i.pfs_image_flags:016X}")
                print(f"  Content:    type=0x{i.content_type:X} flags=0x{i.content_flags:08X}")
                if pkg.has_pfs:
                    try:
                        pfs = pkg.pfs()
                        print(f"  Decifrato:  {pfs.key_used}, PFSC a 0x{pfs._pfsc:X}, "
                              f"mode esterno=0x{pfs.outer_mode:X}")
                    except PkgError as ex:
                        print(f"  ERRORE:     {ex}")
            if args.files:
                for node in pkg.list_files():
                    print(f"    {node.path}{'/' if node.is_dir else f'  ({node.size} B)'}")
    return 0


def _cmd_install(args) -> int:
    games = os.path.abspath(args.output)
    addons = os.path.abspath(args.addons or os.path.join(games, "addcont"))
    infos = [installer.read_info(p) for p in args.pkg]
    plan = installer.build_plan(infos, games, title_folder=not args.no_title_folder)
    for w in plan.warnings:
        print(f"ATTENZIONE: {w}")
    if plan.downgrades and not args.force:
        print("ERRORE: verrebbe installata una versione più vecchia di quella presente. "
              "Usa --force per procedere comunque.", file=sys.stderr)
        return 1

    last = [0.0]

    def progress(idx, count, done, total, name):
        now = time.monotonic()
        finished = not name  # the extractor signals the end with an empty name
        if now - last[0] < 0.2 and not finished:
            return
        last[0] = now
        pct = 100 * done // total if total else 100
        sys.stdout.write(f"\r    {pct:3d}%  {name[-60:]:<60}")
        if finished:
            sys.stdout.write("\n")
        sys.stdout.flush()

    installer.install(plan, games, addons, args.separate_update, log=print, progress=progress)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pkgfree",
        description="Estrae PKG PS4 (fPKG) in cartelle per shadPS4, unendo gioco, patch e DLC.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="mostra le informazioni di uno o più PKG")
    p_info.add_argument("pkg", nargs="+")
    p_info.add_argument("--files", action="store_true", help="elenca anche i file contenuti")
    p_info.add_argument("--debug", action="store_true",
                        help="mostra dettagli tecnici (utili per segnalare problemi)")
    p_info.set_defaults(func=_cmd_info)

    p_inst = sub.add_parser("install", help="estrae e unisce gioco base, aggiornamenti e DLC")
    p_inst.add_argument("pkg", nargs="+", help="file PKG (in qualsiasi ordine)")
    p_inst.add_argument("-o", "--output", required=True, help="cartella dei giochi")
    p_inst.add_argument("--addons", help="cartella DLC (predefinita: <output>/addcont)")
    p_inst.add_argument("--separate-update", action="store_true",
                        help="estrai gli aggiornamenti in <TITLE_ID>-UPDATE invece di unirli")
    p_inst.add_argument("--no-title-folder", action="store_true",
                        help="estrai in <output>/<TITLE_ID> invece di <output>/<titolo>/<TITLE_ID>")
    p_inst.add_argument("--force", action="store_true",
                        help="procedi anche se sul disco c'è una versione più recente")
    p_inst.set_defaults(func=_cmd_install)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (PkgError, OSError) as ex:
        print(f"ERRORE: {ex}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, Cancelled):
        print("\nAnnullato.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
