import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  TextField,
  CircularProgress,
  Alert,
  Stack,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Checkbox,
  Typography,
  ToggleButton,
  ToggleButtonGroup,
  FormControlLabel,
  Switch,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItemButton,
  ListItemText,
  Grid,
  Tooltip,
  IconButton,
  TablePagination,
  InputAdornment,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import LinkIcon from "@mui/icons-material/Link";
import LinkOffIcon from "@mui/icons-material/LinkOff";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import type { Device } from "../utils/constants";
import api from "../services/api";
import {
  fileInputAbsolutePath,
  pickFolderPath,
  pickMultipleFilePaths,
  pickSshPrivateKeyPath,
} from "../utils/nativeDialogs";

export interface FtDevice {
  name: string;
  ip_address: string;
  sdm_port: number;
  serial_no?: string;
  model?: string;
  sdm_status?: string;
}

function sessionKey(d: FtDevice): string {
  return `${(d.ip_address || "").trim()}:${d.sdm_port}`;
}

function insightDeviceToFt(d: Device): FtDevice | null {
  const raw = d.sdm_port;
  const port =
    raw === null || raw === undefined || String(raw).trim() === ""
      ? NaN
      : parseInt(String(raw).trim(), 10);
  if (!port || Number.isNaN(port)) {
    return null;
  }
  return {
    name: (d.name || d.serial_no || d.device_id || "AP").trim(),
    ip_address: (d.ip_address || "").trim(),
    sdm_port: port,
    serial_no: d.serial_no,
    model: d.model,
    sdm_status: d.sdm_status === "1" ? "Enabled" : d.sdm_status === "0" ? "Disabled" : String(d.sdm_status ?? "—"),
  };
}

export interface FileTransferBatchProps {
  managerDevices?: Device[];
}

export default function FileTransferBatch({ managerDevices = [] }: FileTransferBatchProps) {
  const [devices, setDevices] = useState<FtDevice[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [sshcommandOk, setSshcommandOk] = useState<boolean | null>(null);
  const [sshcommandErr, setSshcommandErr] = useState<string | null>(null);
  const [connMap, setConnMap] = useState<Record<string, string>>({});

  const [jumpHost, setJumpHost] = useState("user@smbshells.netgear.com");
  const [sshPort, setSshPort] = useState("443");
  const [sshKeyPath, setSshKeyPath] = useState("");

  const [extraConnectRetries, setExtraConnectRetries] = useState("2");
  const [backoffBaseSec, setBackoffBaseSec] = useState("0.5");
  const [pauseAfterConnectSec, setPauseAfterConnectSec] = useState("0.2");
  const [pauseBetweenBatchApsSec, setPauseBetweenBatchApsSec] = useState("0.15");
  const [pingShellAfterConnect, setPingShellAfterConnect] = useState(false);
  const [reconnectIfSessionDead, setReconnectIfSessionDead] = useState(false);

  const [mode, setMode] = useState<"upload" | "download">("upload");
  const [downloadTimeoutSec, setDownloadTimeoutSec] = useState("900");

  const [uploadRemoteDir, setUploadRemoteDir] = useState("/tmp");
  const [uploadLocalPathsText, setUploadLocalPathsText] = useState("");
  const [uploadBinary, setUploadBinary] = useState(false);

  const [downloadRemotePathsText, setDownloadRemotePathsText] = useState("");
  const [downloadLocalRoot, setDownloadLocalRoot] = useState("");

  const [logLines, setLogLines] = useState<string[]>([]);
  const appendLog = useCallback((line: string) => {
    setLogLines((prev) => [...prev.slice(-400), `[${new Date().toLocaleTimeString()}] ${line}`]);
  }, []);

  const sshKeyFileInputRef = useRef<HTMLInputElement>(null);
  const uploadLocalFilesInputRef = useRef<HTMLInputElement>(null);

  const onSshKeyFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    const p = fileInputAbsolutePath(f);
    if (p) {
      setSshKeyPath(p);
      setMessage(null);
      return;
    }
    if (f) {
      setMessage(
        "This browser did not expose the key file path. Paste the full path on the API host, or use the Tauri desktop app."
      );
    }
  };

  const onUploadLocalFilesInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    e.target.value = "";
    if (!files?.length) return;
    const paths: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const p = fileInputAbsolutePath(files[i]);
      if (p) paths.push(p);
    }
    if (!paths.length) {
      setMessage("Paths not exposed; paste full paths on the API host or use the desktop app.");
      return;
    }
    setUploadLocalPathsText((prev) => {
      const existing = prev
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      return [...existing, ...paths].join("\n");
    });
    setMessage(null);
  };

  /** Same idea as CSV: hidden `<input type="file">`; only the icon triggers it (not the text field). Tauri dialog is used when available. */
  const onBrowseSshKeyIconClick = useCallback(async (ev: React.MouseEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    const p = await pickSshPrivateKeyPath();
    if (p) {
      setSshKeyPath(p);
      setMessage(null);
      return;
    }
    sshKeyFileInputRef.current?.click();
  }, []);

  const onBrowseUploadLocalFilesClick = useCallback(async (ev: React.MouseEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    const picked = await pickMultipleFilePaths();
    if (picked?.length) {
      setUploadLocalPathsText((prev) => {
        const existing = prev
          .split(/\r?\n/)
          .map((s) => s.trim())
          .filter(Boolean);
        return [...existing, ...picked].join("\n");
      });
      setMessage(null);
      return;
    }
    uploadLocalFilesInputRef.current?.click();
  }, []);

  const onBrowseDownloadLocalRootClick = useCallback(async (ev: React.MouseEvent) => {
    ev.preventDefault();
    ev.stopPropagation();
    const p = await pickFolderPath();
    if (p) {
      setDownloadLocalRoot(p);
      setMessage(null);
    }
  }, []);

  const [batchCommand, setBatchCommand] = useState("");

  const [addOpen, setAddOpen] = useState(false);
  const [addName, setAddName] = useState("");
  const [addIp, setAddIp] = useState("");
  const [addPort, setAddPort] = useState("");

  const [exLocalPath, setExLocalPath] = useState("");
  const [exRemotePath, setExRemotePath] = useState("/");
  const [exLocalEntries, setExLocalEntries] = useState<string[]>([]);
  const [exRemoteEntries, setExRemoteEntries] = useState<string[]>([]);
  const [exBusy, setExBusy] = useState(false);

  const [ftTablePage, setFtTablePage] = useState(0);
  const [ftRowsPerPage, setFtRowsPerPage] = useState(50);

  const reliabilityPayload = useMemo(() => {
    const er = Math.max(0, Math.min(8, parseInt(extraConnectRetries, 10) || 2));
    const bb = Math.max(0.05, Math.min(10, parseFloat(backoffBaseSec) || 0.5));
    const pac = Math.max(0, Math.min(5, parseFloat(pauseAfterConnectSec) || 0));
    const pba = Math.max(0, Math.min(5, parseFloat(pauseBetweenBatchApsSec) || 0));
    return {
      extra_connect_retries: er,
      backoff_base_sec: bb,
      pause_after_connect_sec: pac,
      pause_between_batch_aps_sec: pba,
      ping_shell_after_connect: pingShellAfterConnect,
      reconnect_if_session_dead: reconnectIfSessionDead,
    };
  }, [
    extraConnectRetries,
    backoffBaseSec,
    pauseAfterConnectSec,
    pauseBetweenBatchApsSec,
    pingShellAfterConnect,
    reconnectIfSessionDead,
  ]);

  const baseRequest = useMemo(
    () => ({
      jump_host: jumpHost,
      jump_port: parseInt(sshPort, 10) || 443,
      ssh_key_path: sshKeyPath.trim(),
      reliability: reliabilityPayload,
    }),
    [jumpHost, sshPort, sshKeyPath, reliabilityPayload]
  );

  useEffect(() => {
    let cancelled = false;
    void api
      .ftCapabilities()
      .then((c) => {
        if (cancelled) return;
        setSshcommandOk(!!c.sshcommand_available);
        setSshcommandErr(c.sshcommand_error || null);
      })
      .catch(() => {
        if (!cancelled) {
          setSshcommandOk(false);
          setSshcommandErr("Could not query API");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const tick = async () => {
      try {
        const d = await api.ftSessions();
        const next: Record<string, string> = {};
        for (const s of d.sessions || []) {
          next[s.key] = s.status;
        }
        setConnMap(next);
      } catch {
        /* ignore */
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 2500);
    return () => window.clearInterval(id);
  }, [devices.length]);

  const selectedList = useMemo(() => {
    return [...selected]
      .sort((a, b) => a - b)
      .map((i) => devices[i])
      .filter(Boolean);
  }, [devices, selected]);

  const ftPageSlice = useMemo(() => {
    const start = ftTablePage * ftRowsPerPage;
    return devices.slice(start, start + ftRowsPerPage);
  }, [devices, ftTablePage, ftRowsPerPage]);

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(devices.length / ftRowsPerPage) - 1);
    if (ftTablePage > maxPage) setFtTablePage(maxPage);
  }, [devices.length, ftRowsPerPage, ftTablePage]);

  const singleSelected = selectedList.length === 1 ? selectedList[0] : null;

  const toggleRow = (index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const selectAllValid = () => {
    const next = new Set<number>();
    devices.forEach((d, i) => {
      if (d.sdm_port && !Number.isNaN(d.sdm_port)) next.add(i);
    });
    setSelected(next);
  };

  const selectNone = () => setSelected(new Set());

  const loadFromDeviceManagement = () => {
    const list = (managerDevices || [])
      .map(insightDeviceToFt)
      .filter((x): x is FtDevice => x !== null);
    if (list.length === 0) {
      setMessage("No APs with a valid SDM port in Device Management. Load devices and ensure SDM port is set.");
      return;
    }
    setDevices(list);
    setSelected(new Set(list.map((_, i) => i)));
    setMessage(`Loaded ${list.length} AP(s) from Device Management.`);
    appendLog(`Inventory: ${list.length} AP(s) from Device Management.`);
  };

  const handleCSVUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setMessage(null);
    try {
      const data = await api.parseBatchCsv(file);
      if (data.success && data.devices) {
        const rows: FtDevice[] = (data.devices as FtDevice[]).map((d) => ({
          name: d.name || d.ip_address,
          ip_address: d.ip_address,
          sdm_port: Number(d.sdm_port),
          serial_no: d.serial_no,
          model: d.model,
          sdm_status: (d as { sdm_status?: string }).sdm_status ?? "—",
        }));
        setDevices(rows);
        setSelected(new Set(rows.map((_, i) => i)));
        setMessage(`CSV: ${data.total} device(s).`);
        appendLog(`CSV parsed: ${data.total} device(s).`);
      } else {
        setMessage(data.error || "CSV parse failed.");
      }
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      event.target.value = "";
    }
  };

  const clearInventory = () => {
    setDevices([]);
    setSelected(new Set());
    setFtTablePage(0);
    setMessage("Cleared AP list.");
  };

  const removeSelectedRows = () => {
    setDevices((prev) => prev.filter((_, i) => !selected.has(i)));
    setSelected(new Set());
    setMessage("Removed selected AP(s).");
  };

  const confirmAddPort = () => {
    const port = parseInt(addPort.trim(), 10);
    if (!addIp.trim() || !port || Number.isNaN(port)) {
      setMessage("Add port: enter IP and numeric SDM port.");
      return;
    }
    const row: FtDevice = {
      name: addName.trim() || addIp.trim(),
      ip_address: addIp.trim(),
      sdm_port: port,
      model: "—",
      sdm_status: "—",
    };
    setDevices((d) => [...d, row]);
    setAddOpen(false);
    setAddName("");
    setAddIp("");
    setAddPort("");
    appendLog(`Added manual AP ${row.name} (${row.ip_address}:${row.sdm_port}).`);
  };

  const connectSelected = async () => {
    if (selectedList.length === 0) {
      setMessage("Select at least one AP to connect.");
      return;
    }
    if (!sshKeyPath.trim()) {
      setMessage("Enter SSH private key path on the API host.");
      return;
    }
    setConnecting(true);
    setMessage(null);
    try {
      const data = await api.ftConnect({
        devices: selectedList,
        ...baseRequest,
      });
      if (data.success) {
        const s = data.summary as { succeeded?: number; total?: number; failed?: number };
        setMessage(`Connect: ${s.succeeded}/${s.total} succeeded.`);
        for (const ln of (data.log_lines as string[]) || []) {
          appendLog(ln);
        }
        (data.results as { name?: string; success?: boolean; error?: string }[])?.forEach((r) => {
          appendLog(`${r.name}: ${r.success ? "connected" : "failed"} ${r.error || ""}`.trim());
        });
      } else {
        setMessage((data as { error?: string }).error || "Connect failed.");
      }
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setConnecting(false);
    }
  };

  const disconnectAll = async () => {
    try {
      await api.ftDisconnect();
      appendLog("Disconnect: all sessions closed.");
      setConnMap({});
    } catch (e: unknown) {
      appendLog(`Disconnect error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const stopTransfer = async () => {
    try {
      await api.ftTransferStop();
      appendLog("Stop transfer requested.");
    } catch (e: unknown) {
      appendLog(`Stop error: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const clearForm = () => {
    setUploadRemoteDir("/tmp");
    setUploadLocalPathsText("");
    setUploadBinary(false);
    setDownloadRemotePathsText("");
    setDownloadLocalRoot("");
    setDownloadTimeoutSec("900");
    setBatchCommand("");
    setMessage("Form cleared.");
  };

  const refreshLocalExplorer = async () => {
    if (!exLocalPath.trim()) return;
    setExBusy(true);
    try {
      const r = await api.ftExplorerLocalList(exLocalPath.trim());
      if (r.success && r.entries) setExLocalEntries(r.entries);
      else appendLog(`Local list: ${r.error || "failed"}`);
    } catch (e: unknown) {
      appendLog(`Local list: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExBusy(false);
    }
  };

  const refreshRemoteExplorer = async () => {
    if (!singleSelected || !sshKeyPath.trim()) return;
    setExBusy(true);
    try {
      const r = await api.ftExplorerRemoteList({
        ip_address: singleSelected.ip_address,
        sdm_port: singleSelected.sdm_port,
        path: exRemotePath.trim() || "/",
        ...baseRequest,
      });
      if (r.success && r.entries) setExRemoteEntries(r.entries);
      else appendLog(`Remote list: ${r.error || "failed"}`);
    } catch (e: unknown) {
      appendLog(`Remote list: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExBusy(false);
    }
  };

  const runBatchCommands = async () => {
    if (!batchCommand.trim() || selectedList.length === 0) {
      setMessage("Select APs and enter a command.");
      return;
    }
    setRunning(true);
    setMessage(null);
    try {
      const data = await api.batchExecute({
        devices: selectedList,
        command: batchCommand.trim(),
        jump_host: jumpHost,
        jump_port: parseInt(sshPort, 10) || 443,
        ssh_key_path: sshKeyPath.trim(),
        reliability: reliabilityPayload,
      });
      if (data.success) {
        const s = data.summary;
        setMessage(`Commands: ${s.succeeded}/${s.total} succeeded, ${s.failed} failed.`);
        appendLog(`Batch command finished: ${s.succeeded}/${s.total} ok.`);
        (data.results as { device?: string; success?: boolean; output?: string }[]).forEach((r) => {
          appendLog(`${r.device}: ${r.success ? "ok" : "fail"} ${(r.output || "").slice(0, 200)}`);
        });
      } else {
        setMessage(data.error || "Batch command failed.");
      }
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const runTransfer = async () => {
    if (selectedList.length === 0) {
      setMessage("Select at least one AP.");
      return;
    }
    if (!sshKeyPath.trim()) {
      setMessage("Enter SSH private key path (on the machine running this API).");
      return;
    }
    let dlTo = parseInt(downloadTimeoutSec, 10);
    if (Number.isNaN(dlTo)) dlTo = 900;
    if (dlTo < 30 || dlTo > 86400) {
      setMessage("Download timeout must be between 30 and 86400 seconds.");
      return;
    }

    const body: Record<string, unknown> = {
      devices: selectedList,
      operation: mode,
      jump_host: jumpHost,
      jump_port: parseInt(sshPort, 10) || 443,
      ssh_key_path: sshKeyPath.trim(),
      download_timeout_sec: dlTo,
      reliability: reliabilityPayload,
    };

    if (mode === "upload") {
      const paths = uploadLocalPathsText
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const dest = uploadRemoteDir.trim();
      if (!paths.length || !dest) {
        setMessage("Upload: enter destination directory on APs and at least one local file path (one per line).");
        return;
      }
      body.upload_local_paths = paths;
      body.upload_remote_dir = dest;
      body.chmod_x_after_upload = uploadBinary;
    } else {
      const rpaths = downloadRemotePathsText
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const root = downloadLocalRoot.trim();
      if (!rpaths.length || !root) {
        setMessage("Download: enter remote paths (one per line) and local root folder on the API host.");
        return;
      }
      body.download_remote_paths = rpaths;
      body.download_local_root = root;
    }

    setRunning(true);
    setMessage(null);
    appendLog(`Starting ${mode} (jump shell) for ${selectedList.length} AP(s)…`);
    try {
      const data = await api.batchTransfer(body);
      if (data.success) {
        const s = data.summary as { succeeded?: number; total?: number; failed?: number };
        setMessage(`${mode}: ${s.succeeded}/${s.total} operation(s) succeeded, ${s.failed} failed.`);
        appendLog(`Transfer finished: ${s.succeeded}/${s.total} ok (${(data as { engine?: string }).engine || ""}).`);
        for (const ln of (data as { log_lines?: string[] }).log_lines || []) {
          appendLog(ln);
        }
        (data.results as { device?: string; success?: boolean; bytes?: number; error?: string }[]).forEach((r) => {
          appendLog(
            `${r.device}: ${r.success ? "OK" : "FAIL"}${r.bytes ? ` ${r.bytes} B` : ""}${r.error ? ` — ${r.error}` : ""}`
          );
        });
      } else {
        setMessage((data as { error?: string }).error || "Transfer failed.");
      }
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : String(e));
      appendLog(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRunning(false);
    }
  };

  const canPickFromManager = useMemo(
    () => (managerDevices || []).some((d) => insightDeviceToFt(d)),
    [managerDevices]
  );


  const connCell = (d: FtDevice) => {
    const t = connMap[sessionKey(d)] || "—";
    return t.length > 28 ? `${t.slice(0, 26)}…` : t;
  };

  const tableSx = {
    "& .MuiTableCell-root": { py: 0.35, px: 0.75, fontSize: "0.8125rem" },
    "& .MuiTableCell-head": { py: 0.5, fontWeight: 600, bgcolor: "action.hover" },
  } as const;

  /** Keeps outlined inputs in the connection row visually aligned (with or without end adornment). */
  const compactOutlinedInputSx = {
    "& .MuiOutlinedInput-root": { minHeight: 40, alignItems: "center" },
  } as const;

  return (
    <Box
      sx={{
        width: "100%",
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 0.75,
      }}
    >
      <Stack direction="row" alignItems="center" flexWrap="wrap" gap={0.5} sx={{ flexShrink: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          File transfer
        </Typography>
        <Tooltip
          title={
            "Batch upload or download on selected APs over the jump-host shell. Connect opens a session per AP (SMB Shells, then each SDM port); Run sends files over that shell. Explorer and batch command below use different mechanisms — see their info icons."
          }
        >
          <IconButton size="small" aria-label="About file transfer" sx={{ p: 0.35 }}>
            <InfoOutlinedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      {(message || sshcommandOk === false) && (
        <Stack spacing={0.5} sx={{ flexShrink: 0 }}>
          {message && (
            <Alert
              severity={message.startsWith("CSV:") || message.includes("Loaded") ? "success" : "info"}
              sx={{ py: 0, px: 1, "& .MuiAlert-message": { py: 0.5 }, fontSize: "0.8125rem" }}
            >
              {message}
            </Alert>
          )}
          {sshcommandOk === false && (
            <Alert severity="warning" sx={{ py: 0, px: 1, "& .MuiAlert-message": { py: 0.5 }, fontSize: "0.75rem" }}>
              Jump shell unavailable on this API host ({sshcommandErr || "?"}). File transfer requires pexpect and a supported environment — fix the
              server, then refresh.
            </Alert>
          )}
        </Stack>
      )}

      <Grid container spacing={1} sx={{ flex: 1, minHeight: 0, alignContent: "stretch" }}>
        <Grid item xs={12} lg={7} sx={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0 }}>
          <Paper
            variant="outlined"
            sx={{ p: 1.25, flex: 1, display: "flex", flexDirection: "column", minHeight: 0, borderRadius: 1, overflow: "visible" }}
          >
            <Grid container spacing={1.5} sx={{ mb: 1, flexShrink: 0, alignItems: "flex-end" }}>
              <Grid item xs={12} sm={6} md={5}>
                <TextField
                  size="small"
                  label="SSH URL"
                  value={jumpHost}
                  onChange={(e) => setJumpHost(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={5}>
                <input
                  ref={sshKeyFileInputRef}
                  type="file"
                  hidden
                  accept=".pem,.ppk,.key,.txt,application/x-pem-file,application/octet-stream"
                  onChange={onSshKeyFileInputChange}
                />
                <TextField
                  size="small"
                  label="Private key (API host)"
                  value={sshKeyPath}
                  onChange={(e) => setSshKeyPath(e.target.value)}
                  fullWidth
                  placeholder="Path to key"
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="Choose key file on API host">
                          <IconButton
                            type="button"
                            size="small"
                            edge="end"
                            onClick={(e) => void onBrowseSshKeyIconClick(e)}
                            aria-label="Browse for SSH private key"
                          >
                            <InsertDriveFileIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={6} sm={4} md={2}>
                <TextField
                  size="small"
                  label="Jump port"
                  value={sshPort}
                  onChange={(e) => setSshPort(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                />
              </Grid>
              <Grid item xs={6} sm={2} md={2}>
                <TextField
                  size="small"
                  label="Retry"
                  value={extraConnectRetries}
                  onChange={(e) => setExtraConnectRetries(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                />
              </Grid>
              <Grid item xs={6} sm={2} md={2}>
                <TextField
                  size="small"
                  label="Backoff"
                  value={backoffBaseSec}
                  onChange={(e) => setBackoffBaseSec(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                />
              </Grid>
              <Grid item xs={6} sm={3} md={2}>
                <TextField
                  size="small"
                  label="Pause conn"
                  value={pauseAfterConnectSec}
                  onChange={(e) => setPauseAfterConnectSec(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                />
              </Grid>
              <Grid item xs={6} sm={3} md={2}>
                <TextField
                  size="small"
                  label="Pause AP"
                  value={pauseBetweenBatchApsSec}
                  onChange={(e) => setPauseBetweenBatchApsSec(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                  title="Seconds to wait between APs during jump-shell file transfer and batch SSH commands (legacy Tk behaviour; 0–5)."
                />
              </Grid>
              <Grid
                item
                xs={12}
                sm={12}
                md={4}
                sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", pb: 0.25 }}
              >
                <FormControlLabel
                  control={<Switch size="small" checked={pingShellAfterConnect} onChange={(e) => setPingShellAfterConnect(e.target.checked)} />}
                  label="Ping"
                  sx={{
                    m: 0,
                    gap: 0.75,
                    alignItems: "center",
                    "& .MuiFormControlLabel-label": { fontSize: "0.75rem", pl: 0.25 },
                  }}
                />
                <FormControlLabel
                  control={<Switch size="small" checked={reconnectIfSessionDead} onChange={(e) => setReconnectIfSessionDead(e.target.checked)} />}
                  label="Reconnect"
                  sx={{
                    m: 0,
                    gap: 0.75,
                    alignItems: "center",
                    "& .MuiFormControlLabel-label": { fontSize: "0.75rem", pl: 0.25 },
                  }}
                />
              </Grid>
            </Grid>

            <Stack direction="row" flexWrap="wrap" useFlexGap columnGap={0.5} rowGap={0.5} sx={{ mb: 0.75, flexShrink: 0, alignItems: "center" }}>
              <Button size="small" variant="outlined" component="label" disabled={loading} sx={{ minWidth: 0, px: 1 }}>
                CSV
                <input type="file" accept=".csv" hidden onChange={handleCSVUpload} />
              </Button>
              <Button size="small" variant="outlined" onClick={loadFromDeviceManagement} disabled={!canPickFromManager} startIcon={<FolderOpenIcon sx={{ fontSize: 16 }} />} sx={{ minWidth: 0 }}>
                Devices
              </Button>
              <Button size="small" variant="outlined" onClick={clearInventory} sx={{ minWidth: 0 }}>
                Clear
              </Button>
              <Button size="small" variant="outlined" onClick={selectAllValid} disabled={!devices.length} sx={{ minWidth: 0 }}>
                All
              </Button>
              <Button size="small" variant="outlined" onClick={selectNone} disabled={!devices.length} sx={{ minWidth: 0 }}>
                None
              </Button>
              <Button size="small" variant="outlined" onClick={() => setAddOpen(true)} sx={{ minWidth: 0 }}>
                +Port
              </Button>
              <Button size="small" variant="outlined" onClick={removeSelectedRows} disabled={!selected.size} sx={{ minWidth: 0 }}>
                Del
              </Button>
              <Button
                size="small"
                color="secondary"
                variant="contained"
                disabled={connecting || !devices.length || sshcommandOk === false}
                onClick={() => void connectSelected()}
                startIcon={connecting ? <CircularProgress size={14} color="inherit" /> : <LinkIcon sx={{ fontSize: 16 }} />}
                sx={{ minWidth: 0 }}
              >
                Connect
              </Button>
              <Button size="small" variant="outlined" disabled={sshcommandOk === false} onClick={() => void disconnectAll()} sx={{ minWidth: 0 }} startIcon={<LinkOffIcon sx={{ fontSize: 16 }} />}>
                Disc.
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
                {selected.size}/{devices.length}
              </Typography>
            </Stack>

            <TableContainer sx={{ flex: 1, minHeight: 160, border: 1, borderColor: "divider", borderRadius: 0.5 }}>
              {devices.length === 0 ? (
                <Box sx={{ p: 1.5, color: "text.secondary", fontSize: "0.8125rem" }}>Load CSV or Device Management APs.</Box>
              ) : (
                <Table size="small" stickyHeader sx={tableSx}>
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox" />
                      <TableCell>Name</TableCell>
                      <TableCell>IP</TableCell>
                      <TableCell>Model</TableCell>
                      <TableCell>SDM</TableCell>
                      <TableCell>Port</TableCell>
                      <TableCell title="Jump shell session state after Connect (from API).">Link</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ftPageSlice.map((d, j) => {
                      const i = ftTablePage * ftRowsPerPage + j;
                      return (
                      <TableRow key={`${d.ip_address}-${d.sdm_port}-${i}`} hover>
                        <TableCell padding="checkbox">
                          <Checkbox size="small" checked={selected.has(i)} onChange={() => toggleRow(i)} />
                        </TableCell>
                        <TableCell>{d.name}</TableCell>
                        <TableCell>{d.ip_address}</TableCell>
                        <TableCell>{d.model || "—"}</TableCell>
                        <TableCell>{d.sdm_status ?? "—"}</TableCell>
                        <TableCell>{d.sdm_port}</TableCell>
                        <TableCell sx={{ fontFamily: "monospace", fontSize: "0.7rem", maxWidth: 120 }} title={connCell(d)}>
                          {connCell(d)}
                        </TableCell>
                      </TableRow>
                    );})}
                  </TableBody>
                </Table>
              )}
            </TableContainer>
            {devices.length > 0 && (
              <TablePagination
                component="div"
                rowsPerPageOptions={[25, 50, 100, 250, 500]}
                count={devices.length}
                rowsPerPage={ftRowsPerPage}
                page={ftTablePage}
                onPageChange={(_, newPage) => setFtTablePage(newPage)}
                onRowsPerPageChange={(e) => {
                  setFtRowsPerPage(parseInt(e.target.value, 10));
                  setFtTablePage(0);
                }}
                sx={{ borderTop: 1, borderColor: "divider", flexShrink: 0 }}
              />
            )}
          </Paper>
        </Grid>

        <Grid item xs={12} lg={5} sx={{ display: "flex", flexDirection: "column", minHeight: 0, minWidth: 0, gap: 0.75 }}>
          <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1, flexShrink: 0, overflow: "visible" }}>
            <Stack direction="row" alignItems="flex-end" justifyContent="space-between" flexWrap="wrap" columnGap={1.5} rowGap={1} sx={{ mb: 1, width: 1 }}>
              <ToggleButtonGroup exclusive size="small" value={mode} onChange={(_e, v) => v && setMode(v)}>
                <ToggleButton value="upload">Upload</ToggleButton>
                <ToggleButton value="download">Download</ToggleButton>
              </ToggleButtonGroup>
              <TextField
                size="small"
                label="Timeout (s)"
                value={downloadTimeoutSec}
                onChange={(e) => setDownloadTimeoutSec(e.target.value)}
                sx={{ ...compactOutlinedInputSx, width: 118, flexShrink: 0 }}
                InputLabelProps={{ shrink: true }}
                margin="dense"
              />
            </Stack>
            {mode === "upload" ? (
              <Stack spacing={1.25}>
                <TextField
                  size="small"
                  label="Remote dir (on each AP)"
                  value={uploadRemoteDir}
                  onChange={(e) => setUploadRemoteDir(e.target.value)}
                  fullWidth
                  placeholder="/tmp"
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="POSIX path on each AP (e.g. /tmp). Type it here — there is no folder picker for remote paths.">
                          <IconButton
                            size="small"
                            edge="end"
                            aria-label="About remote directory"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={(e) => e.preventDefault()}
                          >
                            <InfoOutlinedIcon fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                />
                <input
                  ref={uploadLocalFilesInputRef}
                  type="file"
                  multiple
                  hidden
                  onChange={onUploadLocalFilesInputChange}
                />
                <Stack direction="row" spacing={0.75} alignItems="flex-start">
                  <TextField
                    size="small"
                    label="Local paths (API host, one per line)"
                    value={uploadLocalPathsText}
                    onChange={(e) => setUploadLocalPathsText(e.target.value)}
                    fullWidth
                    multiline
                    minRows={2}
                    maxRows={6}
                    InputLabelProps={{ shrink: true }}
                    margin="dense"
                    sx={{ flex: 1, minWidth: 0 }}
                  />
                  <Stack spacing={0.25} sx={{ flexShrink: 0, pt: 0.5 }}>
                    <Tooltip title="Absolute paths on the machine running the API, one per line. Use the file icon to append paths from a picker when available.">
                      <IconButton
                        size="small"
                        aria-label="About local paths"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={(e) => e.preventDefault()}
                        sx={{ display: "block" }}
                      >
                        <InfoOutlinedIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Add files on API host (appends paths)">
                      <IconButton
                        type="button"
                        size="small"
                        onClick={(e) => void onBrowseUploadLocalFilesClick(e)}
                        aria-label="Add local files for upload"
                      >
                        <InsertDriveFileIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Stack>
                <FormControlLabel
                  control={<Switch size="small" checked={uploadBinary} onChange={(e) => setUploadBinary(e.target.checked)} />}
                  label="chmod +x"
                  sx={{ m: 0, gap: 0.75, alignItems: "center", "& .MuiFormControlLabel-label": { fontSize: "0.8125rem", pl: 0.25 } }}
                />
              </Stack>
            ) : (
              <Stack spacing={1.25}>
                <TextField
                  size="small"
                  label="Remote paths (one/line)"
                  value={downloadRemotePathsText}
                  onChange={(e) => setDownloadRemotePathsText(e.target.value)}
                  fullWidth
                  multiline
                  minRows={2}
                  maxRows={6}
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                />
                <TextField
                  size="small"
                  label="Local root (API host)"
                  value={downloadLocalRoot}
                  onChange={(e) => setDownloadLocalRoot(e.target.value)}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                  sx={compactOutlinedInputSx}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <Stack direction="row" alignItems="center" component="span">
                          <Tooltip title="Choose folder on API host">
                            <IconButton
                              type="button"
                              size="small"
                              edge="end"
                              onClick={(e) => void onBrowseDownloadLocalRootClick(e)}
                              aria-label="Browse download folder on API host"
                            >
                              <FolderOpenIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Folder on the API host where each AP gets a subfolder for downloaded files. Browse or type the path.">
                            <IconButton
                              size="small"
                              aria-label="About local download root"
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={(e) => e.preventDefault()}
                            >
                              <InfoOutlinedIcon fontSize="inherit" />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </InputAdornment>
                    ),
                  }}
                />
              </Stack>
            )}
          </Paper>

          <Paper variant="outlined" sx={{ p: 1.25, flex: 1, minHeight: 120, display: "flex", flexDirection: "column", borderRadius: 1, overflow: "hidden" }}>
            <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mb: 0.5, flexShrink: 0, display: "block" }}>
              Log
            </Typography>
            <Box
              component="pre"
              sx={{
                flex: 1,
                m: 0,
                p: 0.75,
                overflow: "auto",
                minHeight: 80,
                fontFamily: "ui-monospace, Consolas, monospace",
                fontSize: "0.68rem",
                lineHeight: 1.35,
                bgcolor: (theme) => (theme.palette.mode === "dark" ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)"),
                borderRadius: 0.5,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {logLines.join("\n") || "—"}
            </Box>
            <Stack
              direction="row"
              flexWrap="wrap"
              alignItems="center"
              justifyContent="space-between"
              columnGap={1}
              rowGap={0.75}
              sx={{ mt: 0.75, flexShrink: 0 }}
            >
              <Stack direction="row" flexWrap="wrap" alignItems="center" gap={0.75}>
                <Button
                  size="small"
                  variant="contained"
                  disabled={running || !devices.length || sshcommandOk === false}
                  onClick={() => void runTransfer()}
                  startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon sx={{ fontSize: 18 }} />}
                >
                  Run
                </Button>
                <Button size="small" variant="outlined" onClick={() => void stopTransfer()} startIcon={<StopIcon sx={{ fontSize: 16 }} />}>
                  Stop
                </Button>
                <Button size="small" variant="outlined" onClick={clearForm}>
                  Reset
                </Button>
              </Stack>
              <Button size="small" variant="text" sx={{ minHeight: 0, py: 0.5 }} onClick={() => setLogLines([])}>
                Clear log
              </Button>
            </Stack>
          </Paper>

          <Accordion disableGutters defaultExpanded={false} sx={{ border: 1, borderColor: "divider", borderRadius: 1, "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.25 } }}>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ flex: 1, minWidth: 0, pr: 0.5 }}>
                <Typography variant="body2" fontWeight={600} sx={{ minWidth: 0 }}>
                  Explorer — folder lists only
                </Typography>
                <Tooltip
                  title={
                    "Select exactly one AP in the table. Left: list folders on the API host machine. Right: list folders on that AP over an existing jump-shell session. For moving files in bulk, use Upload/Download and Run above — Explorer does not run batch transfer."
                  }
                >
                  <IconButton
                    size="small"
                    aria-label="About Explorer"
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    sx={{ p: 0.25, flexShrink: 0 }}
                  >
                    <InfoOutlinedIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </AccordionSummary>
            <AccordionDetails sx={{ pt: 0, pb: 1 }}>
              <Grid container spacing={1.5}>
                <Grid item xs={12} sm={6}>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    Local
                  </Typography>
                  <Stack direction="row" spacing={0.75} alignItems="flex-start" sx={{ mb: 0.5 }}>
                    <TextField
                      size="small"
                      label="Path"
                      fullWidth
                      value={exLocalPath}
                      onChange={(e) => setExLocalPath(e.target.value)}
                      placeholder="C:\\temp"
                      InputLabelProps={{ shrink: true }}
                      margin="dense"
                    />
                    <Button size="small" variant="outlined" disabled={exBusy} onClick={() => void refreshLocalExplorer()}>
                      ↻
                    </Button>
                  </Stack>
                  <List dense sx={{ maxHeight: 140, overflow: "auto", border: 1, borderColor: "divider", borderRadius: 0.5, py: 0 }}>
                    {exLocalEntries.map((e) => (
                      <ListItemButton
                        key={e}
                        dense
                        sx={{ py: 0 }}
                        onClick={() => {
                          if (e === "..") {
                            const p = exLocalPath.replace(/[/\\]+$/, "");
                            const up = p.replace(/[/\\][^/\\]*$/, "");
                            setExLocalPath(up || p);
                            return;
                          }
                          if (!e.endsWith("/") && !e.endsWith("\\")) return;
                          const sep = exLocalPath.includes("\\") ? "\\" : "/";
                          const base = exLocalPath.replace(/[/\\]+$/, "");
                          setExLocalPath(`${base}${sep}${e.replace(/[/\\]$/, "")}`);
                        }}
                      >
                        <ListItemText primary={e} primaryTypographyProps={{ variant: "caption", sx: { fontFamily: "monospace" } }} />
                      </ListItemButton>
                    ))}
                  </List>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    Remote
                  </Typography>
                  <Stack direction="row" spacing={0.75} alignItems="flex-start" sx={{ mb: 0.5 }}>
                    <TextField
                      size="small"
                      label="Path"
                      fullWidth
                      value={exRemotePath}
                      onChange={(e) => setExRemotePath(e.target.value)}
                      placeholder="/tmp"
                      InputLabelProps={{ shrink: true }}
                      margin="dense"
                    />
                    <Button size="small" variant="outlined" disabled={exBusy || !singleSelected || !sshKeyPath.trim()} onClick={() => void refreshRemoteExplorer()}>
                      ↻
                    </Button>
                  </Stack>
                  <List dense sx={{ maxHeight: 140, overflow: "auto", border: 1, borderColor: "divider", borderRadius: 0.5, py: 0 }}>
                    {exRemoteEntries.map((e) => (
                      <ListItemButton
                        key={e}
                        dense
                        sx={{ py: 0 }}
                        onClick={() => {
                          if (e === "..") {
                            const base = exRemotePath.replace(/\/+$/, "") || "/";
                            const parent = base === "/" ? "/" : base.replace(/\/[^/]+$/, "") || "/";
                            setExRemotePath(parent);
                            return;
                          }
                          const base = (exRemotePath.trim() || "/").replace(/\/+$/, "");
                          setExRemotePath(`${base}/${e.replace(/\/$/, "")}`);
                        }}
                      >
                        <ListItemText primary={e} primaryTypographyProps={{ variant: "caption", sx: { fontFamily: "monospace" } }} />
                      </ListItemButton>
                    ))}
                  </List>
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>

          <Accordion disableGutters defaultExpanded={false} sx={{ border: 1, borderColor: "divider", borderRadius: 1, "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.25 } }}>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ flex: 1, minWidth: 0, pr: 0.5 }}>
                <Typography variant="body2" fontWeight={600} sx={{ minWidth: 0 }}>
                  Batch command — not file transfer
                </Typography>
                <Tooltip
                  title={
                    "Runs the same shell line on every selected AP using direct SSH (subprocess), one AP at a time. For quick checks (e.g. uptime). This is not jump-shell file transfer — use Run above for uploads and downloads."
                  }
                >
                  <IconButton
                    size="small"
                    aria-label="About batch command"
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    sx={{ p: 0.25, flexShrink: 0 }}
                  >
                    <InfoOutlinedIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </AccordionSummary>
            <AccordionDetails sx={{ pt: 0, pb: 1 }}>
              <Stack spacing={1.25}>
                <TextField
                  size="small"
                  label="Command"
                  value={batchCommand}
                  onChange={(e) => setBatchCommand(e.target.value)}
                  fullWidth
                  multiline
                  minRows={2}
                  placeholder="uptime"
                  InputLabelProps={{ shrink: true }}
                  margin="dense"
                />
                <Button size="small" variant="outlined" disabled={running} onClick={() => void runBatchCommands()}>
                  Execute
                </Button>
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Grid>
      </Grid>

      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Add AP</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <TextField label="Name" size="small" value={addName} onChange={(e) => setAddName(e.target.value)} fullWidth />
            <TextField label="IP" size="small" value={addIp} onChange={(e) => setAddIp(e.target.value)} fullWidth required />
            <TextField label="SDM port" size="small" value={addPort} onChange={(e) => setAddPort(e.target.value)} fullWidth required />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={confirmAddPort}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );

}
