"""Build the installable extension ZIP into dist/.

Usage:
    python build.py              # dist/send_to_slicer-<version>.zip
    python build.py --tag v1.2.0 # additionally fails if the tag does not match the manifest version
"""

import argparse
import pathlib
import sys
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "send_to_slicer"
DIST = ROOT / "dist"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="git tag to compare with the manifest version (e.g. v1.0.0)")
    args = parser.parse_args()

    manifest = tomllib.loads((SRC / "blender_manifest.toml").read_text(encoding="utf-8"))
    version = manifest["version"]
    if args.tag and args.tag.lstrip("v") != version:
        sys.exit(f"Tag {args.tag} does not match manifest version {version}")

    DIST.mkdir(exist_ok=True)
    out = DIST / f"{manifest['id']}-{version}.zip"
    # Files go to the ZIP root, the same layout as `blender --command extension build`
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                zf.write(path, path.relative_to(SRC).as_posix())
    print(out)


if __name__ == "__main__":
    main()
