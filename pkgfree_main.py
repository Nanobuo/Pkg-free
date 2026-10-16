"""Single entry point (Linux AppImage, macOS app): GUI without arguments, CLI with them."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from pkgfree.cli import main
    else:
        from pkgfree.gui import main
    sys.exit(main())
