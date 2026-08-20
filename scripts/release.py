from __future__ import annotations

import argparse
import json
import re
import sys
from enum import Enum, auto
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class TagState(Enum):
    ABSENT = auto()
    MATCHING = auto()
    CONFLICT = auto()
    LIGHTWEIGHT_OR_MALFORMED = auto()


class ReleaseState(Enum):
    ABSENT = auto()
    COMPLETE = auto()
    INVALID = auto()


def parse_version(version: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise ValueError(f"invalid stable version: {version!r}")
    return tuple(int(component) for component in match.groups())  # type: ignore[return-value]


def compare_versions(left: str, right: str) -> int:
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def candidate_manifest_changes_only_version(
    baseline: str, candidate: str, requested_version: str
) -> bool:
    try:
        baseline_data = json.loads(baseline)
        candidate_data = json.loads(candidate)
    except json.JSONDecodeError:
        return False

    if not isinstance(baseline_data, dict) or not isinstance(candidate_data, dict):
        return False

    expected = dict(baseline_data)
    expected["version"] = requested_version
    return candidate_data == expected and candidate_data.get("version") == requested_version


def classify_tag_state(
    object_sha: str | None, peeled_sha: str | None, candidate_sha: str
) -> TagState:
    if object_sha is None and peeled_sha is None:
        return TagState.ABSENT
    if object_sha is None or peeled_sha is None:
        return TagState.LIGHTWEIGHT_OR_MALFORMED
    if object_sha == peeled_sha:
        return TagState.LIGHTWEIGHT_OR_MALFORMED
    if peeled_sha != candidate_sha:
        return TagState.CONFLICT
    return TagState.MATCHING


def classify_release_state(
    release: dict[str, Any] | None, tag_name: str
) -> ReleaseState:
    if release is None:
        return ReleaseState.ABSENT
    if (
        release.get("tagName") != tag_name
        or release.get("isDraft") is not False
        or release.get("isPrerelease") is not False
    ):
        return ReleaseState.INVALID
    return ReleaseState.COMPLETE


def _manifest_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"manifest is not a JSON object: {path}")
    return data


def update_manifest(path: Path, version: str) -> None:
    parse_version(version)
    raw = path.read_text()
    data = _manifest_data(path)
    current = data.get("version")
    if not isinstance(current, str):
        raise ValueError("manifest version is missing or not a string")
    replacement = re.compile(r'("version"\s*:\s*)"[^"]*"')
    updated, count = replacement.subn(rf'\1"{version}"', raw, count=1)
    if count != 1:
        raise ValueError("manifest must contain exactly one version field")
    path.write_text(updated)


def manifest_version(path: Path) -> str:
    version = _manifest_data(path).get("version")
    if not isinstance(version, str):
        raise ValueError("manifest version is missing or not a string")
    parse_version(version)
    return version


def _tag_state(value: str) -> str | None:
    return value or None


def _release_from_stdin() -> dict[str, Any] | None:
    payload = sys.stdin.read().strip()
    if not payload:
        return None
    value = json.loads(payload)
    return value if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("version")

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("left")
    compare_parser.add_argument("right")

    manifest_parser = subparsers.add_parser("manifest-version")
    manifest_parser.add_argument("path", type=Path)

    update_parser = subparsers.add_parser("update-manifest")
    update_parser.add_argument("path", type=Path)
    update_parser.add_argument("version")

    candidate_parser = subparsers.add_parser("check-candidate")
    candidate_parser.add_argument("baseline", type=Path)
    candidate_parser.add_argument("candidate", type=Path)
    candidate_parser.add_argument("version")

    tag_parser = subparsers.add_parser("tag-state")
    tag_parser.add_argument("object_sha")
    tag_parser.add_argument("peeled_sha")
    tag_parser.add_argument("candidate_sha")

    release_parser = subparsers.add_parser("release-state")
    release_parser.add_argument("tag_name")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            parse_version(args.version)
            print(args.version)
        elif args.command == "compare":
            print(compare_versions(args.left, args.right))
        elif args.command == "manifest-version":
            print(manifest_version(args.path))
        elif args.command == "update-manifest":
            update_manifest(args.path, args.version)
        elif args.command == "check-candidate":
            baseline = args.baseline.read_text()
            candidate = args.candidate.read_text()
            if not candidate_manifest_changes_only_version(
                baseline, candidate, args.version
            ):
                raise ValueError("candidate changes more than the manifest version")
        elif args.command == "tag-state":
            print(
                classify_tag_state(
                    _tag_state(args.object_sha),
                    _tag_state(args.peeled_sha),
                    args.candidate_sha,
                ).name
            )
        elif args.command == "release-state":
            state = classify_release_state(_release_from_stdin(), args.tag_name)
            print(state.name)
    except (ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
