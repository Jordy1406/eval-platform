"""Install hooks/pre-push into the target repository (default ../finassist-app). Uninstall: delete the file."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(target: str | None = None) -> int:
    repo = Path(target or ROOT.parent / "finassist-app").resolve()
    dest = repo / ".git" / "hooks" / "pre-push"
    text = (ROOT / "hooks" / "pre-push").read_text(encoding="utf-8").replace("__EVALPLAT_DIR__", ROOT.as_posix())
    dest.write_text(text, encoding="utf-8", newline="\n")
    dest.chmod(0o755)
    print(f"installed {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
