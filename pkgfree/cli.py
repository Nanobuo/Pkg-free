"""Command line interface."""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import __version__, i18n, installer
from .i18n import tr
from .pkg import Cancelled, PkgError, PkgFile


def _cmd_info(args) -> int:
    for path in args.pkg:
        with PkgFile(path) as pkg:
            i = pkg.info
            print(f"{path}")
            print(f"  {tr('Tipo:'):<11} {installer.kind_label(i.kind)} ({i.category})")
            print(f"  {'Content ID:':<11} {i.content_id}")
            print(f"  {'Title ID:':<11} {installer.title_id_of(i)}")
            print(f"  {tr('Titolo:'):<11} {i.title}")
            print(f"  {tr('Versione:'):<11} {i.app_ver or i.version}")
            if args.debug:
                print(f"  {'PFS:':<11} offset=0x{i.pfs_image_offset:X} "
                      f"size=0x{i.pfs_image_size:X} flags=0x{i.pfs_image_flags:016X}")
                print(f"  {'Content:':<11} type=0x{i.content_type:X} flags=0x{i.content_flags:08X}")
                if pkg.has_pfs:
                    try:
                        pfs = pkg.pfs()
                        print(f"  {tr('Decifrato:'):<11} " + tr(
                            "{key}, PFSC a 0x{pfsc:X}, mode esterno=0x{mode:X}",
                            key=pfs.key_used, pfsc=pfs._pfsc, mode=pfs.outer_mode))
                    except PkgError as ex:
                        print(f"  {tr('ERRORE:'):<11} {ex}")
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
        print(tr("ATTENZIONE: {message}", message=w))
    if plan.downgrades and not args.force:
        print(tr("ERRORE: verrebbe installata una versione più vecchia di quella presente. "
                 "Usa --force per procedere comunque."), file=sys.stderr)
        return 1
    shortages = installer.check_space(plan, games, addons, args.separate_update)
    for sh in shortages:
        print(tr("ATTENZIONE: spazio insufficiente su {path}: servono {needed}, liberi {free}.",
                 path=sh.path, needed=_gb(sh.needed), free=_gb(sh.free)))
    if shortages and not args.force:
        print(tr("ERRORE: spazio su disco insufficiente. Libera spazio o usa --force."),
              file=sys.stderr)
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

    def verify_progress(idx, done, total):
        now = time.monotonic()
        if now - last[0] < 0.2 and done != total:
            return
        last[0] = now
        pct = 100 * done // total if total else 100
        sys.stdout.write("\r    " + tr("verifica {pct:3d}%", pct=pct))
        if done == total:
            sys.stdout.write("\n")
        sys.stdout.flush()

    installer.install(plan, games, addons, args.separate_update, log=print, progress=progress,
                      resume=not args.no_resume, verify=args.verify,
                      verify_progress=verify_progress,
                      remove_pkg=os.remove if args.delete_pkg else None)
    return 0


def _gb(n: int) -> str:
    return f"{n / (1 << 30):.1f} GB"


def _cmd_verify(args) -> int:
    bad = False
    labels = {"ok": "OK", "mismatch": tr("NON CORRISPONDE"),
              "absent": tr("assente (non verificabile)")}
    for path in args.pkg:
        with PkgFile(path) as pkg:
            print(path)
            for check in pkg.verify():
                print(f"  {check.name:<7} {labels[check.status]}")
                bad |= check.status == "mismatch"
    return 2 if bad else 0


def main(argv=None) -> int:
    i18n.set_language(i18n.resolve(os.environ.get("PKGFREE_LANG", "auto")))
    parser = argparse.ArgumentParser(
        prog="pkgfree",
        description=tr("Estrae PKG PS4 (fPKG) in cartelle per shadPS4, unendo gioco, patch e DLC."),
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help=tr("mostra le informazioni di uno o più PKG"))
    p_info.add_argument("pkg", nargs="+")
    p_info.add_argument("--files", action="store_true", help=tr("elenca anche i file contenuti"))
    p_info.add_argument("--debug", action="store_true",
                        help=tr("mostra dettagli tecnici (utili per segnalare problemi)"))
    p_info.set_defaults(func=_cmd_info)

    p_ver = sub.add_parser("verify", help=tr("verifica l'integrità (SHA-256) di uno o più PKG"))
    p_ver.add_argument("pkg", nargs="+")
    p_ver.set_defaults(func=_cmd_verify)

    p_inst = sub.add_parser("install",
                            help=tr("estrae e unisce gioco base, aggiornamenti e DLC"))
    p_inst.add_argument("pkg", nargs="+", help=tr("file PKG (in qualsiasi ordine)"))
    p_inst.add_argument("-o", "--output", required=True, help=tr("cartella dei giochi"))
    p_inst.add_argument("--addons", help=tr("cartella DLC (predefinita: <output>/addcont)"))
    p_inst.add_argument("--separate-update", action="store_true",
                        help=tr("estrai gli aggiornamenti in <TITLE_ID>-UPDATE invece di unirli"))
    p_inst.add_argument("--no-title-folder", action="store_true",
                        help=tr("estrai in <output>/<TITLE_ID> invece di "
                                "<output>/<titolo>/<TITLE_ID>"))
    p_inst.add_argument("--force", action="store_true",
                        help=tr("procedi anche se sul disco c'è una versione più recente "
                                "o lo spazio libero non basta"))
    p_inst.add_argument("--verify", action="store_true",
                        help=tr("verifica le impronte SHA-256 di ogni PKG prima di estrarlo"))
    p_inst.add_argument("--delete-pkg", action="store_true",
                        help=tr("cancella i PKG dopo un'estrazione completata senza errori"))
    p_inst.add_argument("--no-resume", action="store_true",
                        help=tr("non riprendere un'estrazione interrotta: estrai tutto da capo"))
    p_inst.set_defaults(func=_cmd_install)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (PkgError, OSError) as ex:
        print(tr("ERRORE: {message}", message=ex), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, Cancelled):
        print("\n" + tr("Annullato."), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
