from __future__ import annotations

import base64
import csv
import hashlib
import io
import zipfile
from pathlib import Path

DIST = "living_context_engine-2.1.0"
NAME = "living-context-engine"
SUMMARY = "Local-first reality delta compiler: turns observations into traceable state, contradictions, and next validation actions"
PACKAGE = "living_context"
ENTRY_POINT = "lce = living_context.cli:main"
GENERATOR = "lce-build"


def _record(path: str, data: bytes) -> tuple[str, str, str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return path, f"sha256={digest}", str(len(data))


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {NAME}\n"
        "Version: 2.1.0\n"
        f"Summary: {SUMMARY}\n"
        "Requires-Python: >=3.10\n"
        "License-Expression: MIT\n"
        "License-File: LICENSE\n"
        "Provides-Extra: llm\n"
        'Requires-Dist: anthropic>=0.69; extra == "llm"\n'
    ).encode()


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    root = Path(__file__).parent
    wheel_name = f"{DIST}-py3-none-any.whl"
    wheel_path = Path(wheel_directory) / wheel_name
    timestamp = (2026, 1, 1, 0, 0, 0)
    records: list[tuple[str, str, str]] = []

    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path: str, data: bytes) -> None:
            info = zipfile.ZipInfo(path, timestamp)
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
            records.append(_record(path, data))

        for source in sorted((root / "src" / PACKAGE).rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts:
                add(str(source.relative_to(root / "src")), source.read_bytes())

        dist_info = f"{DIST}.dist-info"
        add(f"{dist_info}/METADATA", _metadata())
        add(
            f"{dist_info}/WHEEL",
            f"Wheel-Version: 1.0\nGenerator: {GENERATOR}\nRoot-Is-Purelib: true\nTag: py3-none-any\n".encode(),
        )
        add(f"{dist_info}/entry_points.txt", f"[console_scripts]\n{ENTRY_POINT}\n".encode())
        add(f"{dist_info}/licenses/LICENSE", (root / "LICENSE").read_bytes())

        record_path = f"{dist_info}/RECORD"
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerows([*records, (record_path, "", "")])
        info = zipfile.ZipInfo(record_path, timestamp)
        info.external_attr = 0o644 << 16
        archive.writestr(info, buffer.getvalue().encode())

    return wheel_name


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    directory = Path(metadata_directory) / f"{DIST}.dist-info"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "METADATA").write_bytes(_metadata())
    licenses = directory / "licenses"
    licenses.mkdir(exist_ok=True)
    (licenses / "LICENSE").write_bytes((Path(__file__).parent / "LICENSE").read_bytes())
    return directory.name
