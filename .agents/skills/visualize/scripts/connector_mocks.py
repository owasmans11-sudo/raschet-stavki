"""Validate bindings and supply explicitly requested local preview data."""

import base64
import json
import mimetypes
import os
import re
import stat
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
from typing import NamedTuple, cast
from urllib.parse import urlsplit

_MAX_JSON_BYTES = 32_768
_MAX_BINDINGS = 8
_MAX_DASHBOARD_BINDINGS = 256
_MAX_FILE_BYTES = 256 * 1024
_MAX_FILE_TOTAL_BYTES = 2 * 1024 * 1024
_PASSIVE_FILE_TYPES = {
    "application/json",
    "application/octet-stream",
    "text/csv",
    "text/markdown",
    "text/plain",
    "text/tab-separated-values",
}
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_PREFIX = "<!-- vis-bindings\n"
_SUFFIX = "\n-->\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _read_json(text: str, label: str):
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
        # Python accepts NaN and Infinity. The guest and binding protocol require JSON.
        json.dumps(value, allow_nan=False)
        return value
    except (ValueError, RecursionError) as error:
        raise ValueError(f"invalid {label}: {error}") from error


def _valid_interval(value, minimum: int) -> bool:
    return type(value) in (int, float) and minimum <= value <= 86_400 and value % 1 == 0


def _valid_non_tool(binding: dict[str, object]) -> bool:
    # The app rejects the entire vis-bindings header if a sibling source is malformed.
    binding_type = binding.get("type")
    if binding_type == "json":
        return set(binding) == {"type", "value"}
    if binding_type == "file":
        path = binding.get("path")
        return (
            set(binding) == {"type", "path"}
            and isinstance(path, str)
            and len(path) <= 512
            and re.fullmatch(
                r"\./(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)*[A-Za-z0-9_-][A-Za-z0-9._-]*", path
            )
            is not None
        )
    if binding_type == "library":
        file_id = binding.get("libraryFileId")
        return (
            set(binding) == {"type", "libraryFileId", "refreshIntervalSeconds"}
            and isinstance(file_id, str)
            and re.fullmatch(r"libfile_[A-Za-z0-9_-]{1,128}", file_id) is not None
            and _valid_interval(binding.get("refreshIntervalSeconds"), 15)
        )
    if binding_type == "image":
        url = binding.get("url")
        if (
            set(binding) != {"type", "url"}
            or not isinstance(url, str)
            or len(url) > 8192
            or re.search(r"[#\\\s]", url)
        ):
            return False
        parts = urlsplit(url)
        return bool(
            parts.scheme == "https"
            and parts.hostname
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
        )
    return False


def _declared_bindings(
    fragment: str, option: str = "--connector-mocks", *, dashboard: bool = False
) -> dict[str, dict[str, object]]:
    # Dashboard declarations share the byte budget of the entire source file.
    end = fragment.find(_SUFFIX, len(_PREFIX), None if dashboard else _MAX_JSON_BYTES)
    if not fragment.startswith(_PREFIX) or end < 0:
        raise ValueError(f"{option} requires a leading vis-bindings declaration")
    header = fragment[: end + len(_SUFFIX)]
    declaration = fragment[len(_PREFIX) : end]
    if (not dashboard and len(header.encode()) > _MAX_JSON_BYTES) or re.search(
        r"[<>]", declaration
    ):
        raise ValueError("invalid vis-bindings header")
    bindings = _read_json(declaration, "vis-bindings")
    max_bindings = _MAX_DASHBOARD_BINDINGS if dashboard else _MAX_BINDINGS
    if not isinstance(bindings, dict) or len(bindings) > max_bindings:
        raise ValueError(f"vis-bindings must declare at most {max_bindings} named bindings")
    for name, binding in bindings.items():
        if (
            not _NAME.fullmatch(name)
            or name in {"constructor", "prototype"}
            or not isinstance(binding, dict)
        ):
            raise ValueError(f"invalid vis-bindings entry {name!r}")
        if binding.get("type") != "tool":
            if not _valid_non_tool(binding):
                raise ValueError(f"invalid vis-bindings entry {name!r}")
            continue
        tool = binding.get("tool")
        fields = {"type", "tool", "arguments"}
        without_interval = dashboard and binding.keys() == fields
        with_interval = binding.keys() == fields | {"refreshIntervalSeconds"} and _valid_interval(
            binding.get("refreshIntervalSeconds"), 900 if dashboard else 60
        )
        if (
            not (without_interval or with_interval)
            or not isinstance(tool, str)
            or not 1 <= len(tool) <= 256
            or not isinstance(binding.get("arguments"), dict)
        ):
            raise ValueError(f"invalid connector declaration for {name!r}")
    return bindings


def _mock_values(bindings: dict[str, dict[str, object]], fixture: Path) -> dict[str, object]:
    tools = {
        name: binding["tool"] for name, binding in bindings.items() if binding["type"] == "tool"
    }
    if not tools:
        raise ValueError("--connector-mocks requires at least one tool binding")
    if fixture.is_symlink() or not fixture.is_file() or fixture.stat().st_size > 1_000_000:
        raise ValueError("connector mock file must be a regular UTF-8 JSON file of at most 1 MB")
    mocks = _read_json(fixture.read_text(encoding="utf-8"), "connector mocks")
    if not isinstance(mocks, dict):
        raise ValueError("connector mocks must be an object keyed by binding name")  # noqa: TRY004
    if missing := sorted(tools.keys() - mocks.keys()):
        raise ValueError(f"missing connector mocks for: {', '.join(missing)}")
    if unknown := sorted(mocks.keys() - tools.keys()):
        raise ValueError(f"no declared tool binding for mock: {', '.join(unknown)}")
    values = {}
    for name, tool in tools.items():
        mock = mocks[name]
        if not isinstance(mock, dict) or set(mock) != {"tool", "value"} or mock["tool"] != tool:
            raise ValueError(f"mock {name!r} must contain tool {tool!r} and a JSON value")
        encoded = json.dumps(
            mock["value"], allow_nan=False, ensure_ascii=False, separators=(",", ":")
        )
        # JSON.stringify escapes lone surrogates while preserving other Unicode.
        if len(encoded.encode("utf-8", errors="backslashreplace")) > _MAX_JSON_BYTES:
            raise ValueError(f"mock {name!r} exceeds the 32 KiB connector result limit")
        values[name] = mock["value"]
    return values


def _passive_mime(name: str, data: bytes) -> str:
    mime, encoding = mimetypes.guess_type(name)
    if not mime or encoding is not None:
        return "application/octet-stream"
    if mime in _PASSIVE_FILE_TYPES:
        return mime
    if (
        (mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff"))
        or (mime == "image/gif" and data.startswith((b"GIF87a", b"GIF89a")))
        or (mime == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    ):
        return mime
    return "application/octet-stream"


def _reparse_point(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _directory_info(directory: Path) -> os.stat_result:
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or _reparse_point(info) or not info.st_ino:
        raise ValueError(f"unsafe preview file directory: {directory.name!r}")
    return info


def _same_file(expected: os.stat_result, actual: os.stat_result) -> bool:
    return (
        os.path.samestat(expected, actual)
        and stat.S_ISREG(actual.st_mode)
        and not _reparse_point(actual)
        and actual.st_nlink == 1
        and expected.st_size == actual.st_size
        and expected.st_mtime_ns == actual.st_mtime_ns
        and expected.st_ctime_ns == actual.st_ctime_ns
    )


class PreviewRoot(NamedTuple):
    supplied_parent: Path
    directory: Path
    entrypoint: str
    identity: os.stat_result


def pin_preview_root(source: Path) -> PreviewRoot:
    if os.open not in os.supports_dir_fd or not all(
        hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    ):
        raise ValueError(
            "--preview-files is unavailable without directory-relative no-follow access"
        )
    # A symlinked entrypoint must never choose the directory supplying its bindings.
    parent = source.absolute().parent
    directory = parent.resolve(strict=True)
    return PreviewRoot(parent, directory, source.name, _directory_info(directory))


def _check_root(root: PreviewRoot) -> None:
    if root.supplied_parent.resolve(strict=True) != root.directory or not os.path.samestat(
        root.identity, _directory_info(root.directory)
    ):
        raise ValueError("preview file root changed while reading")


def _read_local_member(
    root: PreviewRoot, relative: Path, reserved: list[os.stat_result], limit: int
) -> tuple[bytes, os.stat_result]:
    path = root.directory / relative
    # Walk from the authorized root so a link or junction is rejected before its children.
    directories = [root.directory / parent for parent in reversed(relative.parents)]
    identities = [_directory_info(directory) for directory in directories]
    if not os.path.samestat(root.identity, identities[0]):
        raise ValueError("preview file root changed while reading")
    expected = path.lstat()
    if (
        not expected.st_ino
        or not stat.S_ISREG(expected.st_mode)
        or _reparse_point(expected)
        or expected.st_nlink != 1
    ):
        raise ValueError(
            f"preview input must be a verified regular file with a single link: {relative}"
        )
    if expected.st_size == 0:
        raise ValueError(f"preview input must contain at least one byte: {relative}")
    if expected.st_size > limit:
        raise ValueError(f"preview input exceeds the {limit}-byte limit: {relative}")
    if any(os.path.samestat(expected, item) for item in reserved):
        raise ValueError(f"preview input must differ from the fragment and destination: {relative}")

    def verify_path() -> None:
        _check_root(root)
        if (
            path.resolve(strict=True) != path
            or not _same_file(expected, path.lstat())
            or any(
                not os.path.samestat(identity, _directory_info(directory))
                for directory, identity in zip(directories, identities, strict=True)
            )
        ):
            raise ValueError(f"preview file changed while reading: {relative}")

    verify_path()
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with ExitStack() as stack:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent_fd = os.open(root.directory, directory_flags)
        stack.callback(os.close, parent_fd)
        if not os.path.samestat(root.identity, os.fstat(parent_fd)):
            raise ValueError(f"preview file root changed while reading: {relative}")
        for part, identity in zip(relative.parts[:-1], identities[1:], strict=True):
            parent_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            stack.callback(os.close, parent_fd)
            if not os.path.samestat(identity, os.fstat(parent_fd)):
                raise ValueError(f"preview file directory changed while reading: {relative}")
        descriptor = os.open(relative.name, flags, dir_fd=parent_fd)
        handle = stack.enter_context(os.fdopen(descriptor, "rb"))
        opened = os.fstat(descriptor)
        if not _same_file(expected, opened):
            raise ValueError(f"preview file changed before reading: {relative}")
        verify_path()
        contents = handle.read(limit + 1)
        if len(contents) != expected.st_size or not _same_file(expected, os.fstat(descriptor)):
            raise ValueError(f"preview file changed while reading: {relative}")
        verify_path()
    return contents, opened


def _file_paths(bindings: dict[str, dict[str, object]]) -> list[str]:
    paths = {
        cast(str, binding["path"]) for binding in bindings.values() if binding["type"] == "file"
    }
    logical = {path[2:] for path in paths}
    folded = {path.lower() for path in logical}
    if "index.html" in folded:
        raise ValueError("the Dashboard entrypoint cannot be a static file binding")
    folded.add("index.html")
    if len(folded) != len(logical) + 1 or any(
        str(parent) in folded for path in folded for parent in PurePosixPath(path).parents
    ):
        raise ValueError("Dashboard static file paths cannot collide by case or directory")
    return sorted(paths)


def _data_script(element_id: str, data: Mapping[str, object]) -> str:
    payload = json.dumps(data, separators=(",", ":")).replace("<", r"\u003c")
    return f'<script type="application/json" id="{element_id}">{payload}</script>\n'


def _binding_script(
    bindings: dict[str, dict[str, object]],
    fixture: Path | None,
    files: dict[str, dict[str, str]] | None = None,
) -> str:
    result = _data_script("codex-visualization-bindings", bindings)
    if fixture is not None:
        result += _data_script("codex-connector-mocks", _mock_values(bindings, fixture))
    if files:
        result += _data_script("codex-preview-files", files)
    return result


def preview_binding_data(fragment: str, fixture: Path | None, *, dashboard: bool = False) -> str:
    try:
        bindings = _declared_bindings(fragment, dashboard=dashboard)
    except ValueError:
        if fixture is not None or dashboard:
            raise
        # Ordinary previews can render a fragment even when its sources are unavailable.
        return ""
    return _binding_script(bindings, fixture)


def read_local_preview(
    root: PreviewRoot,
    fixture: Path | None,
    max_fragment_bytes: int,
    *,
    dashboard: bool = False,
    destination: Path | None = None,
    destination_identity: os.stat_result | None = None,
) -> tuple[str, str]:
    _check_root(root)
    reserved = [destination_identity] if destination_identity is not None else []
    if destination is not None and destination.exists():
        reserved.append(destination.stat())
    entrypoint = Path(root.entrypoint)
    fragment, source_info = _read_local_member(root, entrypoint, reserved, max_fragment_bytes)
    reserved.append(source_info)
    observed = {entrypoint: source_info}
    # Match the ordinary fragment reader's universal-newline decoding.
    text = fragment.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    bindings = _declared_bindings(text, "--preview-files", dashboard=dashboard)
    remaining = _MAX_FILE_TOTAL_BYTES
    files: dict[str, dict[str, str]] = {}
    for path in _file_paths(bindings):
        relative = Path(path[2:])
        data, identity = _read_local_member(
            root, relative, reserved, min(_MAX_FILE_BYTES, remaining)
        )
        remaining -= len(data)
        observed[relative] = identity
        files[path] = {
            "name": relative.name,
            "mimeType": _passive_mime(relative.name, data),
            "base64": base64.b64encode(data).decode("ascii"),
        }
    script = _binding_script(bindings, fixture, files)
    _check_root(root)
    for relative, identity in observed.items():
        member = root.directory / relative
        if member.resolve(strict=True) != member or not _same_file(identity, member.lstat()):
            raise ValueError(f"preview file changed while assembling inputs: {relative}")
    if destination is not None and destination.exists():
        output = destination.stat()
        if any(os.path.samestat(output, identity) for identity in observed.values()):
            raise ValueError(
                "preview destination must differ from the fragment and declared inputs"
            )
    return text, script
