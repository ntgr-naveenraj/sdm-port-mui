"""
File transfer via vendored sshcommand (pexpect jump host + base64 upload/download),
matching sdm_manager_gui.py batch behaviour: sessions, reconnect option, pauses, cancel.
"""

from __future__ import annotations

import logging
import posixpath
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SSHCOMMAND: Any = None
_SSHCOMMAND_ERR: str = ""


def _load_sshcommand() -> Tuple[Any, str]:
    global _SSHCOMMAND, _SSHCOMMAND_ERR
    if _SSHCOMMAND is not None:
        return _SSHCOMMAND, ""
    if _SSHCOMMAND_ERR:
        return None, _SSHCOMMAND_ERR
    root = Path(__file__).resolve().parent.parent / "sshCommander"
    p = str(root)
    if p not in sys.path:
        sys.path.insert(0, p)
    try:
        import sshcommand as sc  # noqa: PLC0415

        _SSHCOMMAND = sc
        return sc, ""
    except Exception as e:
        _SSHCOMMAND_ERR = str(e)
        logger.exception("sshcommand import failed")
        return None, _SSHCOMMAND_ERR


def sshcommand_available() -> Tuple[bool, str]:
    sc, err = _load_sshcommand()
    return (sc is not None, err or "")


def load_sshcommand_module():
    """Return imported sshcommand module or None."""
    return _load_sshcommand()[0]


def session_key(ip: str, sdm_port: int) -> str:
    return f"{(ip or '').strip()}:{int(sdm_port)}"


def _is_transient_connect_error(err: str) -> bool:
    if not err or err.strip().lower() == "cancelled":
        return False
    el = err.lower()
    if "cancelled" in el:
        return False
    needles = (
        "timeout",
        "unexpected eof",
        "milestone=port_prompt",
        "milestone=device_shell",
        "milestone=attach",
        "ping:",
    )
    return any(n in el for n in needles)


@dataclass
class FtReliability:
    extra_connect_retries: int = 2
    backoff_base_sec: float = 0.5
    pause_after_connect_sec: float = 0.2
    pause_between_batch_aps_sec: float = 0.15
    ping_shell_after_connect: bool = False
    reconnect_if_session_dead: bool = False


class FileTransferSessionManager:
    """
    In-process pexpect sessions (one Flask worker). Keys: session_key(ip, port).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Any] = {}
        self._row_locks: Dict[str, threading.Lock] = {}
        self.connect_cancel = threading.Event()
        self.transfer_cancel = threading.Event()
        self._conn_status: Dict[str, str] = {}

    def row_lock(self, key: str) -> threading.Lock:
        with self._lock:
            if key not in self._row_locks:
                self._row_locks[key] = threading.Lock()
            return self._row_locks[key]

    def status_snapshot(self) -> List[Dict[str, str]]:
        with self._lock:
            return [{"key": k, "status": self._conn_status.get(k, "—")} for k in self._sessions.keys()]

    def set_status(self, key: str, text: str) -> None:
        with self._lock:
            self._conn_status[key] = text

    def get_child(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._sessions.get(key)

    def put_child(self, key: str, child: Any) -> None:
        with self._lock:
            self._sessions[key] = child

    def pop_child(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._sessions.pop(key, None)

    def clear_status_all(self) -> None:
        with self._lock:
            self._conn_status.clear()

    def disconnect_all(self, sc: Any) -> None:
        self.connect_cancel.set()

        def _noop(_m: str) -> None:
            return None

        with self._lock:
            keys = list(self._sessions.keys())
        for key in keys:
            lk = self.row_lock(key)
            with lk:
                ch = self.pop_child(key)
            if ch is None:
                continue
            try:
                if sc is not None:
                    sc.detach_device_shell(ch, 120.0, _noop)
            except Exception:
                pass
            try:
                ch.close(force=True)
            except Exception:
                pass
            self.set_status(key, "Disconnected")

        with self._lock:
            self._sessions.clear()
        self.connect_cancel.clear()

    def _shell_alive(self, sc: Any, ch: Any) -> bool:
        if ch is None:
            return False
        try:
            if getattr(ch, "closed", False):
                return False
        except Exception:
            pass
        try:
            if hasattr(ch, "isalive") and not ch.isalive():
                return False
        except Exception:
            pass
        return True

    def ensure_channel(
        self,
        sc: Any,
        ssh_cmd: List[str],
        key: str,
        name: str,
        sdm_port: int,
        rel: FtReliability,
        log: Callable[[str], None],
    ) -> Tuple[Optional[Any], str]:
        lk = self.row_lock(key)
        with lk:
            ch = self.get_child(key)
        if self._shell_alive(sc, ch):
            return ch, ""

        had = ch is not None
        if had:
            with lk:
                old = self.pop_child(key)
            if old is not None:
                try:
                    sc.detach_device_shell(old, 45.0, lambda _m: None)
                except Exception:
                    pass
                try:
                    old.close(force=True)
                except Exception:
                    pass

        if not rel.reconnect_if_session_dead:
            if not had:
                return None, "Connect first (no session; enable reconnect or use Connect)."
            return None, "Session dead (enable Reconnect or Connect again)."

        log("milestone: reconnecting dead session")
        child, err = sc.attach_device_shell(
            ssh_cmd,
            sdm_port,
            120.0,
            300.0,
            log,
            False,
            cancel_event=self.transfer_cancel,
        )
        if child:
            self.put_child(key, child)
            self.set_status(key, "Connected")
            return child, ""
        self.set_status(key, "Error")
        return None, err or "reconnect failed"

    def connect_devices(
        self,
        devices: List[Dict[str, Any]],
        jump_host: str,
        jump_port: int,
        key_path: Path,
        rel: FtReliability,
        log_lines: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        sc, imp_err = _load_sshcommand()
        out: List[Dict[str, Any]] = []
        if sc is None:
            for d in devices:
                out.append(
                    {
                        "key": session_key(d.get("ip_address", ""), int(d.get("sdm_port", 0))),
                        "name": d.get("name"),
                        "success": False,
                        "error": imp_err or "sshcommand unavailable",
                    }
                )
            return out

        self.connect_cancel.clear()
        user, host = sc.parse_user_at_host(jump_host.strip())
        ssh_cmd = sc.build_ssh_cmd(
            user,
            host,
            int(jump_port),
            key_path.expanduser(),
            strict_host_key_checking=True,
            accept_new_host_key=True,
        )

        extra_retries = max(0, min(8, int(rel.extra_connect_retries)))
        backoff_base = max(0.05, min(10.0, float(rel.backoff_base_sec)))
        pause_ok = max(0.0, min(5.0, float(rel.pause_after_connect_sec)))
        want_ping = bool(rel.ping_shell_after_connect)

        for d in devices:
            if self.connect_cancel.is_set():
                break
            ip = (d.get("ip_address") or "").strip()
            name = (d.get("name") or ip or "ap").strip()
            try:
                port = int(d.get("sdm_port"))
            except (TypeError, ValueError):
                out.append({"key": session_key(ip, 0), "name": name, "success": False, "error": "invalid SDM port"})
                continue
            key = session_key(ip, port)

            def append_log(msg: str) -> None:
                line = f"[{name} port={port}] {msg}"
                logger.info(line)
                if log_lines is not None:
                    log_lines.append(line)

            lk = self.row_lock(key)
            got = False
            backoff_used = 0.0
            max_backoff_per_ap = 4.0

            for attempt in range(extra_retries + 1):
                if self.connect_cancel.is_set():
                    append_log("Connect cancelled.")
                    break
                remaining_cap = max(0.0, max_backoff_per_ap - backoff_used)
                if attempt > 0:
                    append_log(f"connect retry attempt {attempt + 1}/{extra_retries + 1}")

                old: Any = None
                try:
                    with lk:
                        old = self.pop_child(key)
                        if old is not None:
                            sc.detach_device_shell(old, 120.0, lambda _m: None)
                except Exception:
                    try:
                        if old is not None:
                            old.close(force=True)
                    except Exception:
                        pass

                self.set_status(key, "Connecting…")
                err = ""
                child: Any = None
                try:
                    with lk:
                        child, err = sc.attach_device_shell(
                            ssh_cmd,
                            port,
                            120.0,
                            300.0,
                            append_log,
                            False,
                            cancel_event=self.connect_cancel,
                        )
                except Exception as e:
                    err = f"milestone=attach: {e}"

                if err == "cancelled" or (not child and err and "cancelled" in (err or "").lower()):
                    self.pop_child(key)
                    self.set_status(key, "Disconnected")
                    append_log("Connect cancelled.")
                    out.append({"key": key, "name": name, "success": False, "error": "cancelled"})
                    got = False
                    break

                if child and want_ping:
                    okp, erp = sc.ping_open_device_shell(child, append_log, 12.0, self.connect_cancel)
                    if not okp:
                        try:
                            sc.detach_device_shell(child, 45.0, lambda _m: None)
                        except Exception:
                            pass
                        try:
                            child.close(force=True)
                        except Exception:
                            pass
                        child = None
                        err = erp or "ping failed"

                if child:
                    self.put_child(key, child)
                    self.set_status(key, "Connected")
                    append_log("Connected.")
                    out.append({"key": key, "name": name, "success": True, "error": ""})
                    got = True
                    if pause_ok > 0:
                        time.sleep(pause_ok)
                    break

                err_txt = err or "unknown error"
                may_retry = (
                    attempt < extra_retries
                    and _is_transient_connect_error(err_txt)
                    and not self.connect_cancel.is_set()
                )
                if may_retry and remaining_cap > 0:
                    append_log(f"{err_txt} (will retry)")
                    sleep_t = min(backoff_base * (2**attempt), remaining_cap, 2.0)
                    if sleep_t > 0:
                        time.sleep(sleep_t)
                        backoff_used += sleep_t
                    continue

                append_log(err_txt)
                self.set_status(key, "Error")
                out.append({"key": key, "name": name, "success": False, "error": err_txt})
                break

        return out

    def transfer_batch(
        self,
        devices: List[Dict[str, Any]],
        operation: str,
        *,
        jump_host: str,
        jump_port: int,
        key_path: Path,
        upload_local_paths: Optional[List[str]] = None,
        upload_remote_dir: Optional[str] = None,
        download_remote_paths: Optional[List[str]] = None,
        download_local_root: Optional[str] = None,
        download_timeout_sec: int = 900,
        chmod_x_after_upload: bool = False,
        rel: FtReliability,
        log_lines: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        sc, imp_err = _load_sshcommand()
        results: List[Dict[str, Any]] = []
        if sc is None:
            return [{"device": "—", "success": False, "error": imp_err or "sshcommand unavailable", "bytes": 0}]

        self.transfer_cancel.clear()
        user, host = sc.parse_user_at_host(jump_host.strip())
        ssh_cmd = sc.build_ssh_cmd(
            user,
            host,
            int(jump_port),
            key_path.expanduser(),
            strict_host_key_checking=True,
            accept_new_host_key=True,
        )

        batch_pause = max(0.0, min(5.0, float(rel.pause_between_batch_aps_sec)))
        cmd_t = 300.0
        dl_t = float(max(30, min(86400, int(download_timeout_sec))))

        def append_log(msg: str) -> None:
            logger.info(msg)
            if log_lines is not None:
                log_lines.append(msg)

        op = operation.strip().lower()
        for d in devices:
            if self.transfer_cancel.is_set():
                break
            ip = (d.get("ip_address") or "").strip()
            name = (d.get("name") or ip or "ap").strip()
            try:
                port = int(d.get("sdm_port"))
            except (TypeError, ValueError):
                results.append({"device": name, "success": False, "error": "invalid SDM port", "bytes": 0})
                continue
            key = session_key(ip, port)
            tag = f"[{name} port={port}]"

            def lg(m: str) -> None:
                append_log(f"{tag} {m}")

            if op == "upload":
                dest_base = (upload_remote_dir or "").strip().rstrip("/")
                paths = upload_local_paths or []
                uploads: List[Any] = []
                for lp in paths:
                    pth = Path(lp).expanduser()
                    if not pth.is_file():
                        results.append(
                            {
                                "device": f"{name} ({pth.name})",
                                "success": False,
                                "error": f"Local file not found: {pth}",
                                "bytes": 0,
                            }
                        )
                        continue
                    spec = sc.parse_upload_arg(f"{pth}:{posixpath.join(dest_base, pth.name)}")
                    if chmod_x_after_upload:
                        spec = replace(spec, chmod_mode="+x")
                    uploads.append(spec)

                if not uploads:
                    if batch_pause > 0 and not self.transfer_cancel.is_set():
                        time.sleep(batch_pause)
                    continue

                for spec in uploads:
                    if self.transfer_cancel.is_set():
                        break
                    ch2, e2 = self.ensure_channel(sc, ssh_cmd, key, name, port, rel, lg)
                    if not ch2:
                        results.append(
                            {"device": f"{name} ({spec.local_path.name})", "success": False, "error": e2, "bytes": 0}
                        )
                        break
                    ok, det = sc.run_ops_on_open_shell(
                        ch2,
                        [spec],
                        [],
                        [],
                        cmd_t,
                        lg,
                        lg,
                        cancel_event=self.transfer_cancel,
                    )
                    if ok:
                        sz = spec.local_path.stat().st_size if spec.local_path.is_file() else 0
                        results.append(
                            {
                                "device": f"{name} ({spec.local_path.name})",
                                "success": True,
                                "error": "",
                                "bytes": sz,
                            }
                        )
                        append_log(f"{tag} upload ok: {spec.local_path.name}")
                    else:
                        results.append(
                            {
                                "device": f"{name} ({spec.local_path.name})",
                                "success": False,
                                "error": det,
                                "bytes": 0,
                            }
                        )
                        if det == "cancelled":
                            break
                    if getattr(ch2, "closed", False):
                        with self.row_lock(key):
                            if self.get_child(key) is ch2:
                                self.pop_child(key)
                        self.set_status(key, "Disconnected")
                        break

            else:  # download
                root = Path((download_local_root or "").strip()).expanduser()
                if not root.is_dir():
                    results.append(
                        {"device": name, "success": False, "error": f"Local folder missing: {root}", "bytes": 0}
                    )
                    if batch_pause > 0 and not self.transfer_cancel.is_set():
                        time.sleep(batch_pause)
                    continue
                rpaths = download_remote_paths or []
                if not rpaths:
                    if batch_pause > 0 and not self.transfer_cancel.is_set():
                        time.sleep(batch_pause)
                    continue
                sub = root / _sanitize_dir_name(name)
                try:
                    sub.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    results.append(
                        {"device": name, "success": False, "error": f"Cannot mkdir {sub}: {e}", "bytes": 0}
                    )
                    if batch_pause > 0 and not self.transfer_cancel.is_set():
                        time.sleep(batch_pause)
                    continue

                for remote_file in rpaths:
                    if self.transfer_cancel.is_set():
                        break
                    rf = remote_file.strip()
                    if not rf:
                        continue
                    base_name = posixpath.basename(rf) or "download"
                    local_path = sub / base_name
                    one_dl = [sc.parse_download_arg(f"{rf}:{local_path}")]
                    ch2, e2 = self.ensure_channel(sc, ssh_cmd, key, name, port, rel, lg)
                    if not ch2:
                        results.append({"device": f"{name} ← {rf}", "success": False, "error": e2, "bytes": 0})
                        break
                    ok, det = sc.run_ops_on_open_shell(
                        ch2,
                        [],
                        [],
                        one_dl,
                        cmd_t,
                        lg,
                        lg,
                        download_timeout=dl_t,
                        cancel_event=self.transfer_cancel,
                    )
                    if ok:
                        sz = local_path.stat().st_size if local_path.is_file() else 0
                        results.append({"device": f"{name} ← {rf}", "success": True, "error": "", "bytes": sz})
                        append_log(f"{tag} saved {rf} -> {sub}")
                    else:
                        results.append({"device": f"{name} ← {rf}", "success": False, "error": det, "bytes": 0})
                        if det == "cancelled":
                            break
                    if getattr(ch2, "closed", False):
                        with self.row_lock(key):
                            if self.get_child(key) is ch2:
                                self.pop_child(key)
                        self.set_status(key, "Disconnected")
                        break

            if batch_pause > 0 and not self.transfer_cancel.is_set():
                time.sleep(batch_pause)

        return results

    def remote_list(
        self,
        ip: str,
        sdm_port: int,
        remote_path: str,
        jump_host: str,
        jump_port: int,
        key_path: Path,
        rel: FtReliability,
    ) -> Tuple[bool, str, List[str]]:
        sc, err = _load_sshcommand()
        if sc is None:
            return False, err or "sshcommand unavailable", []
        key = session_key(ip, sdm_port)
        import shlex

        rp = remote_path.strip() or "/"
        cmd = f"ls -1A {shlex.quote(rp)}"
        user, host = sc.parse_user_at_host(jump_host.strip())
        ssh_cmd = sc.build_ssh_cmd(
            user,
            host,
            int(jump_port),
            key_path.expanduser(),
            strict_host_key_checking=True,
            accept_new_host_key=True,
        )

        def lg(m: str) -> None:
            logger.info(f"[remote] {m}")

        rel_nav = replace(rel, reconnect_if_session_dead=True)
        ch, emsg = self.ensure_channel(sc, ssh_cmd, key, name, int(sdm_port), rel_nav, lg)
        if not ch:
            return False, emsg, []
        outputs: List[str] = []
        ok, err2 = sc.run_ops_on_open_shell(
            ch,
            [],
            [cmd],
            [],
            120.0,
            lg,
            lg,
            command_outputs=outputs,
        )
        if not ok:
            return False, err2 or "remote list failed", []
        text = outputs[0] if outputs else ""
        strip_ansi = getattr(sc, "_strip_ansi", lambda s: s)
        lines = [strip_ansi(ln) for ln in text.splitlines() if ln.strip()]
        if ".." not in lines and rp not in ("/", ""):
            lines = [".."] + lines
        return True, "", lines

    def local_list_dir(self, path: str) -> Tuple[bool, str, List[str]]:
        p = Path(path).expanduser()
        if not p.is_dir():
            return False, f"Not a directory: {p}", []
        try:
            names = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = [".."] if p.resolve() != p.resolve().parent else []
            lines += [f"{c.name}{'/' if c.is_dir() else ''}" for c in names]
            return True, "", lines
        except OSError as e:
            return False, str(e), []


def _sanitize_dir_name(name: str) -> str:
    import re

    s = re.sub(r"[^\w\-.]+", "_", (name or "ap").strip())[:120]
    return s or "ap"


# Process-wide singleton (single worker)
_manager: Optional[FileTransferSessionManager] = None
_manager_lock = threading.Lock()


def get_ft_manager() -> FileTransferSessionManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = FileTransferSessionManager()
        return _manager
