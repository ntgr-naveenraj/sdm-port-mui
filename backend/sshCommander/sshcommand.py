#!/usr/bin/env python3
"""
Batch SSH via Netgear SMB Shells: connect to jump host, enter SDM port per CSV row, run commands.

``--command`` may be:
  - A path to a UTF-8 text file (one shell command per line; ``#`` comments; blank lines skipped).
  - Otherwise treated as a single inline command (quote for ``;`` chaining).

Usage:
  python3 sshcommand.py --url vvdn@smbshells.netgear.com --rsa ~/key --csv saveetha.csv \\
    --command 'uptime; date; echo hi'
  python3 sshcommand.py ... --command cmds.txt

Each command is sent as-is; completion is detected when a **new** shell prompt appears as its
own line (so echoed ``root@host:# cmd`` lines do not count as the end of output).
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import re
import shlex
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, TextIO

import pexpect

# Jump host menu (tune if the server string changes)
PATTERN_PORT_PROMPT = re.compile(r"Enter port number:\s*", re.IGNORECASE)
# Optional CSI / escape sequences between end-of-line and prompt (colored PS1, cursor mode, etc.).
# Each CSI is ESC [ params intermediates final-byte (@ through ~).
# Matches zero or more ANSI/VT escape sequences:
#   CSI:  ESC [ <params> <final>   (cursor, color, etc.)
#   OSC:  ESC ] <text> BEL         (xterm window-title; BusyBox PS1 emits this before the visible prompt)
#   Fe:   ESC <letter>             (single-char escapes like ESC M, ESC c)
_ANSI_ESCAPE_OPT = r"(?:\x1b(?:\[[0-9:;<=>?]*[ -/]*[@-~]|\][^\x07\x1b]*\x07|[0-9A-Za-z]))*"
# Optional control characters (e.g. Ctrl+C) after ``#`` before CRLF. Excludes ``\\n``/``\\r`` so we do not eat the line terminator.
_CTRL_BEFORE_EOL = r"(?:[ \t\x00-\x08\x0b\x0c\x0e-\x1f\x7f]{0,32})?"
# Device shell prompt after a new line or CR. Two shapes:
#   root@host:/path#
#   SERIAL:/path/to/cwd#   (BusyBox on APs often omits the ``root@`` prefix in the PS1 we see)
# The second branch requires ``:/`` after the first colon so lines like ``Firmware: 1.2#`` do not match.
PATTERN_DEVICE_PROMPT_LINE = re.compile(
    r"(?:^|[\r\n])"
    + _ANSI_ESCAPE_OPT
    + r"\s*(?:"
    r"root@[^\r\n]+[#\$]"
    r"|[A-Za-z0-9][A-Za-z0-9.-]{2,63}:/[^\r\n]{0,220}[#\$]"
    r")"
    + _CTRL_BEFORE_EOL
    + r"(?:[\r\n]|\Z)",
    re.IGNORECASE,
)
# Fallback: ``root@...#`` at line start with CSI, last ``#`` on line is prompt (rejects ``# cmd`` on same line).
PATTERN_DEVICE_PROMPT_LOOSE = re.compile(
    r"(?:^|[\r\n])"
    + _ANSI_ESCAPE_OPT
    + r"\s*root@[^\r\n]*#"
    + _CTRL_BEFORE_EOL
    + r"(?:[\r\n]|\Z)",
    re.IGNORECASE,
)
# After leaving device shell
PATTERN_SESSION_ENDED = re.compile(
    r"(Session on port \d+ ended|Enter port number:|Connection to .+ closed)",
    re.IGNORECASE,
)


def _normalize_terminal_text(s: str) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _pexpect_tail_for_error(s: str, max_len: int = 1200) -> str:
    """Short tail for timeout/EOF diagnostics (strip ANSI, cap length)."""
    t = _strip_ansi(s or "")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    if len(t) > max_len:
        t = "…" + t[-max_len:]
    return t.replace("\n", " ").strip()


_ANSI_STRIP_RE = re.compile(
    r"(?:\x1b|\x9b)(?:\[[0-9:;<=>?]*[ -/]*[@-~]|\][^\x07\x1b]*\x07|[0-9A-Za-z])"
)


def _strip_ansi(s: str) -> str:
    """Remove all ANSI/VT escape sequences (CSI, OSC, Fe) from ``s``."""
    return _ANSI_STRIP_RE.sub("", s)


def _expect_until_interruptible(
    child: Any,
    patterns: list,
    total_timeout: float,
    cancel_event: Any,
) -> tuple[str, Optional[int]]:
    """
    Poll ``expect`` with short timeouts until one of ``patterns`` matches, the
    overall deadline passes, or ``cancel_event`` is set.

    ``patterns`` must not include ``pexpect.TIMEOUT``; it is appended for polling.

    Returns ``("match", index)``, ``("timeout", None)``, or ``("cancelled", None)``.
    """
    deadline = time.monotonic() + total_timeout
    poll_patterns = list(patterns) + [pexpect.TIMEOUT]
    timeout_pat_idx = len(patterns)
    while time.monotonic() < deadline:
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled", None
        remain = deadline - time.monotonic()
        slice_t = min(0.5, remain)
        if slice_t <= 0:
            break
        child.timeout = max(0.05, slice_t)
        idx = child.expect(poll_patterns)
        if idx != timeout_pat_idx:
            return "match", idx
    return "timeout", None


def _wait_for_shell_prompt(
    child: pexpect.spawn,
    overall_timeout: float,
    log: Callable[[str], None],
    phase: str,
    cancel_event: Any = None,
) -> tuple[bool, str]:
    """
    Wait until a device shell prompt matches (strict or loose regex).

    Uses short polling expects so a ``threading.Event`` can abort promptly
    (e.g. GUI disconnect while connecting).
    """
    remain = max(0.5, overall_timeout)
    log(
        f"milestone: {phase} waiting up to {overall_timeout}s for shell prompt "
        f"(root@...# or SERIAL:/...#; ANSI + Ctrl+C after # allowed)..."
    )
    outcome, idx = _expect_until_interruptible(
        child,
        [
            PATTERN_DEVICE_PROMPT_LINE,
            PATTERN_DEVICE_PROMPT_LOOSE,
            pexpect.EOF,
        ],
        remain,
        cancel_event,
    )
    if outcome == "cancelled":
        return False, f"{phase}: cancelled"
    if outcome == "timeout":
        tail = repr((child.before or "")[-4000:])
        return False, f"{phase}: timeout after {overall_timeout}s waiting for shell prompt; tail={tail}"
    if idx == 2:
        tail = repr((child.before or "")[-4000:])
        return False, f"{phase}: unexpected EOF; tail={tail}"
    return True, ""


_B64_LINE_RE = re.compile(r"^[A-Za-z0-9+/]+=*\s*$")

# Markers for delimiter-based download capture (underscore not in base64 alphabet).
_B64_MARK_BEGIN = "__SDM_B64_B__"
_B64_MARK_END = "__SDM_B64_E__"

# Bound PTY write size for base64 heredoc lines (MIME width 76); larger batches cut syscalls.
_UPLOAD_HEREDOC_BATCH_BYTES = 8192


def _batched_upload_heredoc_lines(lines: list[str]) -> list[str]:
    """
    Split ``lines`` into newline-terminated strings for ``child.send``, each
    batch roughly capped by ``_UPLOAD_HEREDOC_BATCH_BYTES`` when joined (a
    single line longer than that limit is sent alone).
    """
    if not lines:
        return []
    out: list[str] = []
    buf: list[str] = []
    joined_len = 0
    for line in lines:
        extra = 1 if buf else 0
        if buf and joined_len + extra + len(line) > _UPLOAD_HEREDOC_BATCH_BYTES:
            out.append("\n".join(buf) + "\n")
            buf = []
            joined_len = 0
            extra = 0
        buf.append(line)
        joined_len += extra + len(line)
    if buf:
        out.append("\n".join(buf) + "\n")
    return out


def _extract_between_markers(text: str, begin: str, end: str) -> str:
    """
    Return payload between marker lines after stripping ANSI.

    Markers must appear as their own lines (as from ``printf '%s\\n' marker``).
    A plain ``str.find`` match is unsafe: the echoed command line also contains
    the marker strings and would capture shell text instead of base64.
    """
    t = _strip_ansi(text)
    re_block = re.compile(
        r"(?:^|\n)\s*"
        + re.escape(begin)
        + r"\s*\r?\n([\s\S]*?)(?:\r?\n)\s*"
        + re.escape(end)
        + r"\s*(?:\r?\n|$)",
    )
    m = re_block.search(t)
    if not m:
        return ""
    return m.group(1).strip()


def _remote_byte_count(
    child: pexpect.spawn,
    device_path: str,
    command_timeout: float,
) -> tuple[Optional[int], str]:
    """Best-effort file size from ``wc -c`` (BusyBox / GNU)."""
    quoted = shlex.quote(device_path)
    cmd = f"wc -c {quoted}"
    child.sendline(cmd)
    idx = child.expect(
        [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
        timeout=command_timeout,
    )
    raw_before = child.before or ""
    if idx not in (0, 1):
        return None, "timeout or EOF after wc -c"
    text = _strip_leading_echo_line(_strip_ansi(raw_before), cmd)
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^(\d+)\s", ln)
        if m:
            return int(m.group(1)), ""
        m2 = re.match(r"^(\d+)$", ln)
        if m2:
            return int(m2.group(1)), ""
    return None, f"unparseable wc -c: {text[:200]!r}"


def _extract_base64_strict_joined(text: str) -> str:
    """
    Join wrapped base64 lines that are ``base64``-alphabet only on each line.
    Strips ANSI on **each** line so CSI injected mid-stream (common on PTYs)
    does not cause us to drop valid payload lines (which corrupts binaries).
    """
    base = _normalize_terminal_text(text)
    if not base:
        return ""
    parts: list[str] = []
    for ln in base.split("\n"):
        s = _strip_ansi(ln).strip()
        if s and _B64_LINE_RE.fullmatch(s):
            parts.append(s)
    return "".join(parts)


def _extract_base64_loose(text: str) -> str:
    """Strip non-base64 characters from the whole capture (legacy path)."""
    base = _normalize_terminal_text(_strip_ansi(text))
    if not base:
        return ""
    return re.sub(r"[^A-Za-z0-9+/=]", "", base)


def _extract_base64_payload_from_text(text: str) -> str:
    """
    Prefer strict wrapped lines (with per-line ANSI strip); else loose scrape.
    """
    s = _extract_base64_strict_joined(text)
    if s:
        return s
    return _extract_base64_loose(text)


def _pad_base64_data_only(s: str) -> str:
    """Strip trailing padding, then re-pad so length is a multiple of 4."""
    t = s.rstrip("=")
    pad = (-len(t)) % 4
    return t + ("=" * pad)


def _b64_decode_robust(b64_clean: str) -> tuple[bytes, str]:
    """
    Decode base64 from a cleaned string, trimming up to 3 trailing garbage
    characters when length mod 4 is wrong (common with prompt fragments).
    """
    if not b64_clean:
        return b"", "no base64 data"
    last_err = ""
    for trim in range(0, 4):
        cand = b64_clean[:-trim] if trim else b64_clean
        if not cand:
            break
        padded = _pad_base64_data_only(cand)
        try:
            return base64.b64decode(padded, validate=True), ""
        except Exception as exc:
            last_err = str(exc)
            continue
    return b"", last_err or "base64 decode failed"


_MD5SUM_HEX_RE = re.compile(r"\b([0-9a-fA-F]{32})\b")


def parse_md5sum_output(text: str) -> Optional[str]:
    """First 32-hex digest on the first substantial line of ``md5sum`` output."""
    t = _normalize_terminal_text(_strip_ansi(text))
    for ln in t.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = _MD5SUM_HEX_RE.search(ln)
        if m:
            return m.group(1).lower()
    return None


def _remote_md5sum_hex(
    child: pexpect.spawn,
    device_path: str,
    command_timeout: float,
) -> tuple[Optional[str], str]:
    quoted = shlex.quote(device_path)
    cmd = f"md5sum {quoted}"
    child.sendline(cmd)
    idx = child.expect(
        [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
        timeout=command_timeout,
    )
    raw_before = child.before or ""
    if idx not in (0, 1):
        return None, "timeout or EOF waiting for prompt after md5sum"
    text = _strip_leading_echo_line(_strip_ansi(raw_before), cmd)
    hexd = parse_md5sum_output(text)
    if hexd:
        return hexd, ""
    return None, f"unparseable md5sum output: {text[:240]!r}"


def _strip_leading_echo_line(before: str, cmd: str) -> str:
    """
    Drop the first line when it looks like the pty echo of ``root@...# <cmd>...``.
    """
    s = _normalize_terminal_text(before)
    if not s:
        return s
    lines = s.split("\n")
    first = lines[0].strip()
    c = cmd.strip()
    if not c or "#" not in first:
        return s
    _pre, post_hash = first.split("#", 1)
    post = post_hash.strip()
    if post == c or post.startswith(c + " ") or post.startswith(c + ";"):
        return "\n".join(lines[1:]).strip()
    return s


@dataclass
class DeviceRow:
    name: str
    sdm_port: int
    raw: dict


@dataclass(frozen=True)
class CommandSource:
    """How ``--command`` was resolved."""

    kind: str  # "inline" | "file"
    path: Optional[Path]  # set when kind == "file"
    commands: list[str]


@dataclass(frozen=True)
class UploadSpec:
    """One ``--upload local_path:device_path`` entry."""

    local_path: Path
    device_path: str
    chmod_mode: str  # e.g. "755" (preserved from local stat) or "+x" (--bin override)


@dataclass(frozen=True)
class DownloadSpec:
    """One ``--download device_path:local_path`` entry."""

    device_path: str
    local_path: Path


def parse_user_at_host(url: str) -> tuple[str, str]:
    if "@" not in url:
        raise argparse.ArgumentTypeError("--url must be user@hostname")
    user, _, host = url.partition("@")
    if not user or not host:
        raise argparse.ArgumentTypeError("--url must be user@hostname")
    return user, host


def is_valid_sdm_port(value: str) -> Optional[int]:
    s = value.strip()
    if not s or not s.isdigit():
        return None
    n = int(s)
    if 1 <= n <= 65535:
        return n
    return None


def parse_commands_from_file_text(text: str) -> list[str]:
    """One command per line; strip; skip empty; skip comment lines (leading # after strip)."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


def resolve_command_arg(raw: str) -> CommandSource:
    """
    If ``raw`` expands to an existing regular file, read UTF-8 commands from it.
    Otherwise treat ``raw`` as a single inline command string.
    """
    path = Path(raw).expanduser()
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        cmds = parse_commands_from_file_text(text)
        return CommandSource(kind="file", path=path.resolve(), commands=cmds)
    return CommandSource(kind="inline", path=None, commands=[raw])


def parse_upload_arg(raw: str) -> UploadSpec:
    """Parse ``local_path:device_path`` from ``--upload``."""
    if ":" not in raw:
        raise argparse.ArgumentTypeError(
            f"--upload must be local_path:device_path, got: {raw!r}"
        )
    local_str, _, device_str = raw.partition(":")
    if not local_str or not device_str:
        raise argparse.ArgumentTypeError(
            f"--upload must be local_path:device_path, got: {raw!r}"
        )
    local = Path(local_str).expanduser().resolve()
    if not local.is_file():
        raise argparse.ArgumentTypeError(f"--upload: local file not found: {local}")
    # Preserve local file permissions (rwxrwxrwx bits) as octal string, e.g. "755".
    mode_octal = oct(local.stat().st_mode & 0o777)[2:]
    return UploadSpec(local_path=local, device_path=device_str, chmod_mode=mode_octal)


def parse_download_arg(raw: str) -> DownloadSpec:
    """Parse ``device_path:local_path`` from ``--download``."""
    if ":" not in raw:
        raise argparse.ArgumentTypeError(
            f"--download must be device_path:local_path, got: {raw!r}"
        )
    device_str, _, local_str = raw.partition(":")
    if not device_str or not local_str:
        raise argparse.ArgumentTypeError(
            f"--download must be device_path:local_path, got: {raw!r}"
        )
    return DownloadSpec(device_path=device_str, local_path=Path(local_str).expanduser())


def iter_target_devices(
    csv_path: Path,
    port_column: str,
    name_column: str,
    require_sdm_enabled: bool,
    status_column: str = "SDM Status",
) -> Iterator[DeviceRow]:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return
        for row in reader:
            name = (row.get(name_column) or "").strip() or "(unnamed)"
            if require_sdm_enabled:
                st = (row.get(status_column) or "").strip()
                if st != "Enabled":
                    continue
            raw_port = row.get(port_column) or ""
            port = is_valid_sdm_port(raw_port)
            if port is None:
                if raw_port.strip():
                    print(
                        f"skip: invalid SDM port for {name!r}: {raw_port!r}",
                        file=sys.stderr,
                    )
                continue
            yield DeviceRow(name=name, sdm_port=port, raw=dict(row))


def build_ssh_cmd(
    user: str,
    host: str,
    ssh_port: int,
    identity_file: Path,
    strict_host_key_checking: bool,
    accept_new_host_key: bool,
) -> list[str]:
    if accept_new_host_key:
        kh = "accept-new"
    elif strict_host_key_checking:
        kh = "yes"
    else:
        kh = "no"
    return [
        "ssh",
        "-p",
        str(ssh_port),
        "-i",
        str(identity_file),
        "-o",
        f"StrictHostKeyChecking={kh}",
        f"{user}@{host}",
    ]


def build_progress_logger(quiet: bool, stream: TextIO = sys.stdout) -> Callable[[str], None]:
    if quiet:

        def _noop(_msg: str) -> None:
            return None

        return _noop

    def _log(msg: str) -> None:
        print(msg, file=stream, flush=True)

    return _log


def _do_upload(
    child: pexpect.spawn,
    spec: UploadSpec,
    command_timeout: float,
    log: Callable[[str], None],
    output_log: Callable[[str], None],
) -> tuple[bool, str]:
    """
    Base64-encode a local file and write it to the device via a PTY heredoc.

    Safe for all file types (binary, .so, .sh, text). The heredoc sentinel
    ``__UPLOAD_B64EOF__`` cannot appear in standard base64 output.
    """
    data = spec.local_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    chunks = [b64[i : i + 76] for i in range(0, len(b64), 76)]
    quoted_dst = shlex.quote(spec.device_path)
    log(
        f"upload: {spec.local_path} -> {spec.device_path}"
        f" ({len(data)} bytes, {len(chunks)} base64 lines)"
    )
    child.sendline(f"base64 -d > {quoted_dst} <<'__UPLOAD_B64EOF__'")
    had_delay = hasattr(child, "delaybeforesend")
    prev_delay = child.delaybeforesend if had_delay else None
    try:
        if had_delay:
            child.delaybeforesend = 0
        for block in _batched_upload_heredoc_lines(chunks):
            child.send(block)
        child.sendline("__UPLOAD_B64EOF__")
    finally:
        if had_delay:
            child.delaybeforesend = prev_delay
    idx = child.expect(
        [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
        timeout=command_timeout,
    )
    if idx not in (0, 1):
        return False, f"upload {spec.device_path!r}: timeout or EOF after heredoc transfer"
    # Apply permissions: chmod_mode is either the preserved octal (e.g. "755") or "+x" (--bin).
    child.sendline(f"chmod {shlex.quote(spec.chmod_mode)} {quoted_dst}")
    idx2 = child.expect(
        [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
        timeout=command_timeout,
    )
    if idx2 not in (0, 1):
        return False, f"upload {spec.device_path!r}: timeout or EOF after chmod {spec.chmod_mode!r}"
    output_log(f"upload ok: {spec.local_path.name} -> {spec.device_path} (chmod {spec.chmod_mode})")
    local_md5 = hashlib.md5(data).hexdigest()
    rhex, rerr = _remote_md5sum_hex(child, spec.device_path, command_timeout)
    if rhex and rhex == local_md5:
        output_log(
            f"MD5 OK: {local_md5}  ({spec.device_path} matches {spec.local_path})"
        )
    elif rhex:
        output_log(
            f"MD5 MISMATCH: local={local_md5} remote={rhex}  ({spec.device_path})"
        )
    else:
        output_log(f"MD5 skip ({spec.device_path}): {rerr}")
    return True, ""


def _do_download(
    child: pexpect.spawn,
    spec: DownloadSpec,
    download_timeout: float,
    log: Callable[[str], None],
    output_log: Callable[[str], None],
) -> tuple[bool, str]:
    """
    ``md5sum`` and ``wc -c`` on the device, then stream ``base64`` bounded by
    unique line markers (underscore is not in the base64 alphabet) so PTY noise
    cannot be scraped into the payload. Falls back to strict/loose line scraping
    if markers are missing. Chooses the decoded candidate that matches the
    pre-transfer MD5 and/or ``wc`` size when possible.
    """
    quoted = shlex.quote(spec.device_path)
    md5_t = min(120.0, max(15.0, download_timeout))
    mb, me = _B64_MARK_BEGIN, _B64_MARK_END

    pre_hex, pre_err = _remote_md5sum_hex(child, spec.device_path, md5_t)
    wc_n, wc_err = _remote_byte_count(child, spec.device_path, md5_t)

    cmd = (
        f"printf '%s\\n' '{mb}'; "
        f"base64 {quoted} 2>/dev/null; "
        f"printf '%s\\n' '{me}'"
    )
    log(f"download: {spec.device_path} -> {spec.local_path}")
    child.sendline(cmd)
    idx = child.expect(
        [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
        timeout=download_timeout,
    )
    raw_before = child.before or ""
    if idx not in (0, 1):
        tail = _pexpect_tail_for_error(raw_before)
        reason = "EOF" if idx == 2 else "timeout"
        return (
            False,
            f"download {spec.device_path!r}: {reason} waiting for prompt "
            f"(expect_index={idx}); tail={tail!r}; cmd={cmd!r}",
        )
    text = _strip_leading_echo_line(_strip_ansi(raw_before), cmd)

    inner = _extract_between_markers(text, mb, me)
    b64_m = re.sub(r"[^A-Za-z0-9+/=]", "", inner) if inner else ""
    b64_s = _extract_base64_strict_joined(text)
    b64_l = _extract_base64_loose(text)

    def _try_decode(blob: str) -> tuple[Optional[bytes], str]:
        if not blob:
            return None, "empty"
        data, err = _b64_decode_robust(blob)
        if err:
            return None, err
        return data, ""

    seen_blob: set[str] = set()
    blobs: list[tuple[str, str]] = []
    for label, blob in (
        ("marker", b64_m),
        ("strict", b64_s),
        ("loose", b64_l),
    ):
        if not blob or blob in seen_blob:
            continue
        seen_blob.add(blob)
        blobs.append((label, blob))

    if not blobs:
        tail = _pexpect_tail_for_error(text)
        return (
            False,
            f"download {spec.device_path!r}: no base64 data in captured output; tail={tail!r}",
        )

    pri_map = {"marker": 3, "loose": 2, "strict": 1}
    ranked: list[tuple[int, int, str, bytes]] = []
    for label, blob in blobs:
        data, err = _try_decode(blob)
        if data is None:
            continue
        score = 0
        if pre_hex and hashlib.md5(data).hexdigest() == pre_hex:
            score += 100
        if wc_n is not None and len(data) == wc_n:
            score += 50
        ranked.append((score, pri_map.get(label, 0), label, data))

    if not ranked:
        _, err0 = _try_decode(blobs[0][1])
        return False, f"download {spec.device_path!r}: base64 decode error: {err0}"

    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    _sc, _pri, pick, file_data = ranked[0]

    if not b64_m and pick != "marker" and (b64_s or b64_l):
        output_log(
            "download note: marker-delimited capture was empty; used strict/loose fallback extractors."
        )
    elif pick == "loose" and pre_hex and hashlib.md5(file_data).hexdigest() == pre_hex:
        output_log(
            "download note: loose extraction matched pre-transfer md5sum (marker/strict did not)."
        )

    spec.local_path.parent.mkdir(parents=True, exist_ok=True)
    spec.local_path.write_bytes(file_data)
    output_log(
        f"download ok: {spec.device_path} -> {spec.local_path} ({len(file_data)} bytes)"
    )
    local_md5 = hashlib.md5(file_data).hexdigest()

    if pre_hex and pre_hex == local_md5:
        output_log(f"MD5 OK: {local_md5}  ({spec.device_path} matches streamed bytes)")
        return True, ""

    post_hex, post_err = _remote_md5sum_hex(child, spec.device_path, md5_t)

    if pre_hex and post_hex and pre_hex != post_hex:
        output_log(
            "MD5: remote digest changed during transfer (typical of live logs under "
            f"/tmp/log, etc.). Streamed {len(file_data)} bytes to {spec.local_path.name}; "
            f"digest moved {pre_hex} -> {post_hex}. Local file is the streamed snapshot."
        )
        return True, ""

    if post_hex and post_hex == local_md5:
        output_log(
            f"MD5 OK: {local_md5}  ({spec.device_path}; verified after transfer)"
        )
        return True, ""

    if pre_hex and post_hex and pre_hex == post_hex and pre_hex != local_md5:
        output_log(
            f"MD5 MISMATCH: local={local_md5} remote={pre_hex} ({spec.device_path}) "
            "(remote digest unchanged before/after transfer; check decode or line noise)"
        )
        return True, ""

    if pre_hex or post_hex:
        rh = post_hex or pre_hex
        output_log(
            f"MD5 MISMATCH: local={local_md5} remote={rh} ({spec.device_path})"
        )
    else:
        output_log(
            f"MD5 skip ({spec.device_path}): before={pre_err!r}; after={post_err!r}"
        )
    return True, ""


def attach_device_shell(
    ssh_cmd: list[str],
    sdm_port: int,
    connect_timeout: float,
    command_timeout: float,
    log: Callable[[str], None],
    debug_pty: bool = False,
    cancel_event: Any = None,
) -> tuple[Optional[Any], str]:
    """
    Spawn SSH to jump host, enter ``sdm_port``, wait until device shell is ready.

    Returns ``(child, "")`` on success; ``(None, error_detail)`` on failure.
    Caller must ``detach_device_shell`` when done (or close the child).

    If ``cancel_event`` is set while waiting, closes the child and returns
    ``(None, "cancelled")``.
    """
    child = pexpect.spawn(
        ssh_cmd[0],
        ssh_cmd[1:],
        encoding="utf-8",
        codec_errors="replace",
        timeout=connect_timeout,
    )
    if debug_pty:
        child.logfile_read = sys.stderr
    try:
        if cancel_event is not None and cancel_event.is_set():
            try:
                child.close(force=True)
            except Exception:
                pass
            return None, "cancelled"

        log("milestone: waiting for jump host port menu (Enter port number)...")
        outcome, idx = _expect_until_interruptible(
            child,
            [PATTERN_PORT_PROMPT, pexpect.EOF],
            connect_timeout,
            cancel_event,
        )
        if outcome == "cancelled":
            try:
                child.close(force=True)
            except Exception:
                pass
            return None, "cancelled"
        if outcome == "timeout":
            rest = (child.before or "") + (child.after or "")
            return None, f"milestone=port_prompt: timeout waiting for port prompt: {rest[-500:]}"
        if idx == 1:
            rest = (child.before or "") + (child.after or "")
            return None, f"milestone=port_prompt: unexpected EOF (expect index {idx}): {rest[-500:]}"

        log(f"milestone: sending SDM tunnel port {sdm_port}")
        child.sendline(str(sdm_port))
        time.sleep(0.25)
        ok_prompt, err = _wait_for_shell_prompt(
            child, connect_timeout, log, phase="device_shell", cancel_event=cancel_event
        )
        if not ok_prompt:
            try:
                child.close(force=True)
            except Exception:
                pass
            if err.endswith("cancelled") or "cancelled" in err:
                return None, "cancelled"
            return None, f"milestone=device_shell: {err}"

        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    child.close(force=True)
                except Exception:
                    pass
                return None, "cancelled"
            idx2 = child.expect(
                [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.TIMEOUT],
                timeout=0.5,
            )
            if idx2 not in (0, 1):
                break

        log("milestone: device shell ready")
        child.timeout = command_timeout
        return child, ""
    except Exception as exc:
        try:
            child.close(force=True)
        except Exception:
            pass
        return None, f"milestone=attach: {exc}"


def ping_open_device_shell(
    child: Any,
    log: Callable[[str], None],
    overall_timeout: float = 12.0,
    cancel_event: Any = None,
) -> tuple[bool, str]:
    """
    Send a trivial echo and wait for the device prompt again.

    Catches shells that looked ready but immediately drop or never echo a prompt
    after a command.
    """
    if child is None:
        return False, "ping: no child"
    try:
        if getattr(child, "closed", False):
            return False, "ping: closed"
    except Exception:
        pass
    try:
        if hasattr(child, "isalive") and not child.isalive():
            return False, "ping: not alive"
    except Exception:
        pass
    log("milestone: ping shell (echo)")
    try:
        child.sendline("echo __SDM_FT_PING__")
    except Exception as exc:
        return False, f"ping: send: {exc}"
    ok, err = _wait_for_shell_prompt(
        child, overall_timeout, log, phase="ping", cancel_event=cancel_event
    )
    if not ok:
        return False, err or "ping: no prompt"
    return True, ""


def run_ops_on_open_shell(
    child: Any,
    uploads: list[UploadSpec],
    commands: list[str],
    downloads: list[DownloadSpec],
    command_timeout: float,
    log: Callable[[str], None],
    output_log: Callable[[str], None],
    transcript: Optional[Callable[[str], None]] = None,
    command_outputs: Optional[list[str]] = None,
    download_timeout: Optional[float] = None,
    cancel_event: Any = None,
) -> tuple[bool, str]:
    """
    On an already-attached device shell, run uploads, then commands, then downloads.

    ``command_outputs``, if provided, receives one stripped stdout string per ``commands`` entry.

    ``download_timeout``: if set, used for each download (and its md5sum); else ``command_timeout``.
    ``cancel_event``: optional ``threading.Event``; if set, checked between operations.
    """
    child.timeout = command_timeout
    dl_t = download_timeout if download_timeout is not None else command_timeout

    def _cancelled() -> bool:
        return cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)()

    for spec in uploads:
        if _cancelled():
            return False, "cancelled"
        ok_up, err_up = _do_upload(child, spec, command_timeout, log, output_log)
        if not ok_up:
            return False, f"milestone=upload: {err_up}"
        if transcript:
            transcript(f"upload ok: {spec.local_path} -> {spec.device_path}")

    for i, cmd in enumerate(commands, start=1):
        if _cancelled():
            return False, "cancelled"
        log(f"running command {i}/{len(commands)}: {cmd!r}")
        output_log(f"--- command {i}/{len(commands)}: {cmd!r} ---")
        if transcript:
            transcript(f"--- command {i}/{len(commands)}: {cmd!r} ---")
        child.sendline(cmd)
        child.timeout = command_timeout
        idx = child.expect(
            [PATTERN_DEVICE_PROMPT_LINE, PATTERN_DEVICE_PROMPT_LOOSE, pexpect.EOF, pexpect.TIMEOUT],
            timeout=child.timeout,
        )
        raw_before = child.before or ""
        if idx not in (0, 1):
            tail = _normalize_terminal_text(raw_before[-2000:])
            return (
                False,
                f"milestone=command_{i}: did not see next shell prompt line (index {idx}): {tail!r}",
            )

        output_before = _strip_leading_echo_line(raw_before, cmd)
        if command_outputs is not None:
            command_outputs.append(_normalize_terminal_text(output_before))
        output_log("----- command output -----")
        if output_before:
            for line in output_before.splitlines():
                output_log(f"  {line}")
        else:
            output_log("  (no stdout before prompt)")
        output_log("----- end command output -----")
        if transcript:
            transcript("----- output -----")
            transcript(output_before if output_before else "(no output)")
            transcript("----- end output -----")

    for spec in downloads:
        if _cancelled():
            return False, "cancelled"
        ok_dl, err_dl = _do_download(child, spec, dl_t, log, output_log)
        if not ok_dl:
            return False, f"milestone=download: {err_dl}"
        if transcript:
            transcript(f"download ok: {spec.device_path} -> {spec.local_path}")

    return True, ""


def detach_device_shell(
    child: Optional[Any],
    connect_timeout: float,
    log: Callable[[str], None],
) -> tuple[bool, str]:
    """Send ``exit`` on device shell, wait for session end, and close ``child``."""
    if child is None:
        return True, ""
    try:
        if getattr(child, "closed", False):
            return True, ""
    except Exception:
        pass
    try:
        log("milestone: closing device session (exit)")
        child.sendline("exit")
        child.timeout = connect_timeout
        idx = child.expect([PATTERN_SESSION_ENDED, pexpect.EOF, pexpect.TIMEOUT])
        if idx == pexpect.TIMEOUT:
            return False, "milestone=post_exit: timeout waiting for session end"
        return True, ""
    except Exception as exc:
        return False, f"milestone=detach: {exc}"
    finally:
        try:
            child.close(force=True)
        except Exception:
            pass


def run_remote_ssh_session(
    ssh_cmd: list[str],
    sdm_port: int,
    uploads: list[UploadSpec],
    commands: list[str],
    downloads: list[DownloadSpec],
    connect_timeout: float,
    command_timeout: float,
    log: Callable[[str], None],
    output_log: Callable[[str], None],
    debug_pty: bool = False,
) -> tuple[bool, str]:
    """
    One jump login, one SDM port: upload files → run commands → download files.

    Pass empty lists for unused operations. ``log`` is for milestones/progress
    (may be quiet). ``output_log`` always prints transfer results and command output.

    Returns ``(ok, detail)``. On failure ``detail`` includes ``milestone=...``.
    """
    transcript: list[str] = []

    def _t(msg: str) -> None:
        transcript.append(msg)

    _t(f"SSH login: {' '.join(ssh_cmd)}")
    log(f"SSH login: {' '.join(ssh_cmd)}")
    child, err = attach_device_shell(
        ssh_cmd, sdm_port, connect_timeout, command_timeout, log, debug_pty
    )
    if not child:
        return False, err
    try:
        ok, err2 = run_ops_on_open_shell(
            child,
            uploads,
            commands,
            downloads,
            command_timeout,
            log,
            output_log,
            transcript=_t,
        )
        if not ok:
            detach_device_shell(child, connect_timeout, log)
            return False, err2
        ok3, err3 = detach_device_shell(child, connect_timeout, log)
        if not ok3:
            return False, err3
        return True, "\n".join(transcript).strip()
    except Exception as exc:
        try:
            detach_device_shell(child, connect_timeout, log)
        except Exception:
            pass
        return False, f"milestone=session: {exc}"


def run_sdm_port_shell_commands(
    ssh_cmd: list[str],
    sdm_port: int,
    commands: list[str],
    connect_timeout: float,
    command_timeout: float,
    log: Callable[[str], None],
    debug_pty: bool = False,
) -> tuple[bool, str | list[str]]:
    """
    One jump login, one SDM port: run shell commands only (no upload/download).

    Returns ``(True, outputs)`` where ``outputs`` has one stripped string per command
    (device stdout between echoed command and the next prompt). On failure returns
    ``(False, error_detail)`` with ``milestone=...`` style messages.
    """
    if not commands:
        return True, []

    outputs: list[str] = []
    child, err = attach_device_shell(
        ssh_cmd, sdm_port, connect_timeout, command_timeout, log, debug_pty
    )
    if not child:
        return False, err
    try:

        def _noop_out(_msg: str) -> None:
            return None

        ok, err2 = run_ops_on_open_shell(
            child,
            [],
            commands,
            [],
            command_timeout,
            log,
            _noop_out,
            transcript=None,
            command_outputs=outputs,
        )
        if not ok:
            detach_device_shell(child, connect_timeout, log)
            return False, err2
        detach_device_shell(child, connect_timeout, log)
        return True, outputs
    except Exception as exc:
        detach_device_shell(child, connect_timeout, log)
        return False, f"milestone=shell_commands: {exc}"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="SSH to SMB Shells jump host and run command(s) on each CSV device (by SDM port).",
        epilog=(
            "--command may be a path to a UTF-8 file (one command per line; # comments) or one inline command. "
            "Quote inline commands for the shell, e.g. --command 'uptime; date'. "
            "Each command completes when the device prints a new prompt line (root@...# or ...$) alone on a line. "
            "Host keys: default strict checking; use --accept-new-host-key once to learn a new host."
        ),
    )
    p.add_argument("--url", required=True, help="SSH user@hostname (e.g. vvdn@smbshells.netgear.com)")
    p.add_argument("--rsa", required=True, type=Path, help="Path to SSH private key (-i)")
    p.add_argument("--csv", required=True, type=Path, help="Inventory CSV path")
    p.add_argument(
        "--command",
        default=None,
        help="Inline shell command, or path to a text file with one command per line",
    )
    p.add_argument(
        "--upload",
        action="append",
        type=parse_upload_arg,
        metavar="LOCAL:DEVICE",
        help=(
            "Upload a file: local_path:device_path. "
            "Uses base64-over-PTY; safe for all file types (binary, .so, .sh, etc.). "
            "May be specified multiple times."
        ),
    )
    p.add_argument(
        "--bin",
        action="store_true",
        help=(
            "After each upload, run chmod +x on the device instead of preserving "
            "the local file's permission bits (useful for executables and scripts)."
        ),
    )
    p.add_argument(
        "--download",
        action="append",
        type=parse_download_arg,
        metavar="DEVICE:LOCAL",
        help=(
            "Download a file: device_path:local_path. "
            "Uses base64-over-PTY; safe for all file types. "
            "May be specified multiple times."
        ),
    )
    p.add_argument("--ssh-port", type=int, default=443, help="SSH port for jump host (default: 443)")
    p.add_argument("--sdm-port-column", default="SDM Port", help="CSV column for tunnel port")
    p.add_argument("--name-column", default="Name", help="CSV column for device label in logs")
    p.add_argument(
        "--require-sdm-enabled",
        action="store_true",
        help="Only process rows where SDM Status column is exactly Enabled",
    )
    p.add_argument(
        "--connect-timeout",
        type=float,
        default=120.0,
        help="Seconds: jump login, port attach, and post-exit (default: 120)",
    )
    p.add_argument(
        "--command-timeout",
        type=float,
        default=300.0,
        help="Seconds: wait for device prompt after each command (default: 300)",
    )
    p.add_argument(
        "--no-strict-host-key-checking",
        dest="strict_host_key_checking",
        action="store_false",
        default=True,
        help="Pass StrictHostKeyChecking=no instead of yes (insecure)",
    )
    p.add_argument(
        "--accept-new-host-key",
        action="store_true",
        help="Pass StrictHostKeyChecking=accept-new for first-time host keys only",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress CSV/SSH progress logs on stdout; command output and a one-line 'ok' per device still print",
    )
    p.add_argument(
        "--debug-pty",
        action="store_true",
        help="Log raw bytes from the remote PTY to stderr (noisy; for diagnosing prompt/hang issues)",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    user, host = parse_user_at_host(args.url)
    key = Path(args.rsa).expanduser()
    if not key.is_file():
        print(f"error: key file not found: {key}", file=sys.stderr)
        return 2

    csv_path = args.csv.expanduser().resolve()
    if not csv_path.is_file():
        print(f"error: csv not found: {csv_path}", file=sys.stderr)
        return 2

    uploads: list[UploadSpec] = args.upload or []
    if args.bin and uploads:
        uploads = [replace(u, chmod_mode="+x") for u in uploads]
    downloads: list[DownloadSpec] = args.download or []

    cmd_src: Optional[CommandSource] = None
    if args.command:
        cmd_src = resolve_command_arg(args.command)
        if not cmd_src.commands:
            print(
                "error: --command resolved to no runnable lines (empty file or only blanks/comments).",
                file=sys.stderr,
            )
            return 2

    if not uploads and not downloads and not (cmd_src and cmd_src.commands):
        print(
            "error: specify at least one of --command, --upload, or --download.",
            file=sys.stderr,
        )
        return 2

    log = build_progress_logger(args.quiet)

    if cmd_src is not None:
        log(f"Resolved --command as: {cmd_src.kind}")
        if cmd_src.kind == "file":
            log(f"  commands file: {cmd_src.path}")
            log(f"  runnable lines: {len(cmd_src.commands)}")
        else:
            log("  inline single command")

    if uploads:
        log(f"Uploads ({len(uploads)}):")
        for u in uploads:
            log(f"  {u.local_path} -> {u.device_path}  [chmod {u.chmod_mode}]")
    if downloads:
        log(f"Downloads ({len(downloads)}):")
        for d in downloads:
            log(f"  {d.device_path} -> {d.local_path}")

    log(f"CSV: {csv_path}")
    log(f"  columns: SDM port={args.sdm_port_column!r}, name={args.name_column!r}")
    log(f"  require_sdm_enabled={args.require_sdm_enabled}")
    log(f"  jump host SSH port (-p): {args.ssh_port}")

    ssh_cmd = build_ssh_cmd(
        user=user,
        host=host,
        ssh_port=args.ssh_port,
        identity_file=key,
        strict_host_key_checking=args.strict_host_key_checking,
        accept_new_host_key=args.accept_new_host_key,
    )

    devices = list(
        iter_target_devices(
            csv_path,
            port_column=args.sdm_port_column,
            name_column=args.name_column,
            require_sdm_enabled=args.require_sdm_enabled,
        )
    )
    if not devices:
        print("No rows with a valid SDM port (and optional SDM Enabled filter).", file=sys.stderr)
        return 1

    log(f"Found {len(devices)} device(s) with valid SDM tunnel port id(s):")
    for dev in devices:
        log(f"  - {dev.name!r}  SDM port (tunnel id) {dev.sdm_port}")
    log(f"SDM port id list: [{', '.join(str(d.sdm_port) for d in devices)}]")
    log("")

    any_failed = False
    for dev in devices:
        tag = f"[{dev.name} port={dev.sdm_port}]"
        log("=" * 72)
        log(f"{tag} start")
        log("=" * 72)

        def dev_log(msg: str, *, _tag: str = tag) -> None:
            log(f"{_tag} {msg}")

        def output_log(msg: str, *, _tag: str = tag) -> None:
            print(f"{_tag} {msg}", flush=True)

        ok, detail = run_remote_ssh_session(
            ssh_cmd=ssh_cmd,
            sdm_port=dev.sdm_port,
            uploads=uploads,
            commands=cmd_src.commands if cmd_src else [],
            downloads=downloads,
            connect_timeout=args.connect_timeout,
            command_timeout=args.command_timeout,
            log=dev_log,
            output_log=output_log,
            debug_pty=args.debug_pty,
        )
        if ok:
            print(f"{tag} ok", flush=True)
        else:
            any_failed = True
            print(f"{tag} FAILED: {detail}", file=sys.stderr)
        log("")

    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
