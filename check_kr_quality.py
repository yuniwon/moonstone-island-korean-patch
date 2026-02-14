import argparse
import json
import re
import sys
from pathlib import Path


CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
LATIN_RE = re.compile(r"[A-Za-z]")


KNOWN_BAD_PATTERNS = {
    "정령 헛간를": "정령 헛간을",
    "제작 도안와": "제작 도안과",
    "제작 도안야": "제작 도안이야",
    "도안는": "도안은",
    "정령 헛간로": "정령 헛간으로",
}


# Intentional character-voice foreign expressions in social KR slot (data[17]).
WHITELIST_COORDS = {
    ("strings_social_carpenter.json", 5, 0),
    ("strings_social_carpenter.json", 6, 0),
    ("strings_social_carpenter.json", 9, 0),
    ("strings_social_carpenter.json", 11, 0),
    ("strings_social_carpenter.json", 127, 1),
    ("strings_social_botanist.json", 81, 2),
}


def get_kr_dim(filename: str) -> int | None:
    if filename == "strings.json":
        return 9
    if filename == "stringsDialogue.json":
        return 8
    if filename.startswith("strings_social_"):
        return 17
    return None


def looks_like_untranslated_english(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 12:
        return False
    if stripped.startswith("//"):
        return False
    if stripped.startswith("{string:"):
        return False
    if stripped.startswith("{npc:"):
        return False
    if stripped.startswith("{mood:"):
        return False
    return bool(LATIN_RE.search(stripped))


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoded = text.encode("cp949", errors="replace").decode("cp949", errors="replace")
        print(encoded)


def scan_file(path: Path) -> list[str]:
    issues: list[str] = []

    data = json.loads(path.read_text(encoding="utf-8"))
    matrix = data.get("data")
    if not isinstance(matrix, list):
        return issues

    kr_dim = get_kr_dim(path.name)
    if kr_dim is None or kr_dim >= len(matrix):
        return issues

    kr_rows = matrix[kr_dim]
    en_rows = matrix[1] if len(matrix) > 1 else []

    if not isinstance(kr_rows, list):
        return issues

    for row_idx, row in enumerate(kr_rows):
        if not isinstance(row, list):
            continue
        for col_idx, value in enumerate(row):
            if not isinstance(value, str):
                continue

            coord = (path.name, row_idx, col_idx)

            if CYRILLIC_RE.search(value):
                issues.append(
                    f"[CYRILLIC] {path.name}:{row_idx}:{col_idx} -> {value[:140]}"
                )

            for bad, good in KNOWN_BAD_PATTERNS.items():
                if bad in value:
                    issues.append(
                        f"[KNOWN_JOSA] {path.name}:{row_idx}:{col_idx} has '{bad}' (suggest '{good}')"
                    )

            if coord in WHITELIST_COORDS:
                continue

            # EN carryover check is limited to dialogue files to avoid
            # false positives in credits/system labels.
            if path.name == "strings.json":
                continue

            if (
                isinstance(en_rows, list)
                and row_idx < len(en_rows)
                and isinstance(en_rows[row_idx], list)
                and col_idx < len(en_rows[row_idx])
                and isinstance(en_rows[row_idx][col_idx], str)
            ):
                en_value = en_rows[row_idx][col_idx]
                if value == en_value and looks_like_untranslated_english(value):
                    issues.append(
                        f"[EN_CARRYOVER] {path.name}:{row_idx}:{col_idx} -> {value[:140]}"
                    )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="KR quality gate for patch_data Data files")
    parser.add_argument(
        "--root",
        default="patch_data/Data",
        help="Root directory containing game data JSON files",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"error: root path not found: {root}")
        return 2

    targets = [
        root / "strings.json",
        root / "Dialogues" / "stringsDialogue.json",
    ]
    targets.extend(sorted((root / "Dialogues").glob("strings_social_*.json")))

    issues: list[str] = []
    for target in targets:
        if target.exists():
            issues.extend(scan_file(target))

    if issues:
        safe_print("KR quality gate: FAIL")
        safe_print(f"issues: {len(issues)}")
        for line in issues[:200]:
            safe_print(line)
        if len(issues) > 200:
            safe_print(f"... truncated {len(issues) - 200} more issues")
        return 1

    safe_print("KR quality gate: PASS")
    safe_print(f"checked files: {len(targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
