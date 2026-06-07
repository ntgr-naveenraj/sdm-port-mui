import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Checkbox,
  FormControl,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  type SelectChangeEvent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import { Device } from "../utils/constants";

const DOT_ONLINE = "#4caf50";
const DOT_OFFLINE_OR_DISABLED = "#f44336";

type ColKey =
  | "checkbox"
  | "name"
  | "organization"
  | "serial_no"
  | "model"
  | "ip_address"
  | "device_status"
  | "sdm_status"
  | "sdm_port"
  | "mac_address";

type SortableColKey = Exclude<ColKey, "checkbox">;

const ORDER: ColKey[] = [
  "checkbox",
  "name",
  "organization",
  "serial_no",
  "model",
  "ip_address",
  "device_status",
  "sdm_status",
  "sdm_port",
  "mac_address",
];

const MIN: Record<ColKey, number> = {
  checkbox: 36,
  name: 100,
  organization: 72,
  serial_no: 88,
  model: 64,
  ip_address: 80,
  device_status: 72,
  sdm_status: 72,
  sdm_port: 56,
  mac_address: 120,
};

/** Initial widths — tuned for typical laptop width; drag headers to widen. */
const DEFAULT: Record<ColKey, number> = {
  checkbox: 36,
  name: 140,
  organization: 108,
  serial_no: 118,
  model: 88,
  ip_address: 100,
  device_status: 78,
  sdm_status: 86,
  sdm_port: 68,
  mac_address: 138,
};

const RESIZABLE: Record<ColKey, boolean> = {
  checkbox: false,
  name: true,
  organization: true,
  serial_no: true,
  model: true,
  ip_address: true,
  device_status: true,
  sdm_status: true,
  sdm_port: true,
  mac_address: true,
};

const LABELS: Record<ColKey, string> = {
  checkbox: "",
  name: "Name",
  organization: "Organization",
  serial_no: "Serial",
  model: "Model",
  ip_address: "IP",
  device_status: "Status",
  sdm_status: "SDM Status",
  sdm_port: "SDM Port",
  mac_address: "MAC Address",
};

type ConnectivityFilter = "all" | "online" | "offline";
type SdmFilter = "all" | "enabled" | "disabled";

function deviceMatchesSearch(row: Device, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    row.name,
    row.serial_no,
    row.model,
    row.ip_address,
    row.mac_address,
    row.network_name,
    row.organization,
    row.device_id,
  ]
    .filter((s) => s != null && String(s).length > 0)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

function deviceMatchesConnectivity(row: Device, f: ConnectivityFilter): boolean {
  if (f === "all") return true;
  if (f === "online") return row.device_status === 1;
  return row.device_status !== 1;
}

function deviceMatchesSdm(row: Device, f: SdmFilter): boolean {
  if (f === "all") return true;
  const enabled = String(row.sdm_status) === "1";
  if (f === "enabled") return enabled;
  return !enabled;
}

function sdmPortDisplay(row: Device): string {
  const online = row.device_status === 1;
  const raw = row.sdm_port;
  const hasPort = raw !== null && raw !== undefined && String(raw).trim() !== "";
  return !online || !hasPort ? "N/A" : String(raw);
}

function sortKeyFor(row: Device, field: SortableColKey): string {
  switch (field) {
    case "name":
      return (row.name || "").toLowerCase();
    case "organization":
      return (row.organization || "").toLowerCase();
    case "serial_no":
      return (row.serial_no || "").toLowerCase();
    case "model":
      return (row.model || "").toLowerCase();
    case "ip_address":
      return (row.ip_address || "").toLowerCase();
    case "mac_address":
      return (row.mac_address || "").toLowerCase();
    case "device_status":
      return row.device_status === 1 ? "online" : "offline";
    case "sdm_status":
      return String(row.sdm_status) === "1" ? "enabled" : "disabled";
    case "sdm_port":
      return sdmPortDisplay(row).toLowerCase();
    default:
      return "";
  }
}

function compareDevices(
  a: Device,
  b: Device,
  field: SortableColKey,
  dir: "asc" | "desc"
): number {
  const av = sortKeyFor(a, field);
  const bv = sortKeyFor(b, field);
  const primary = av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
  if (primary !== 0) return dir === "asc" ? primary : -primary;
  const sec = a.network_id.localeCompare(b.network_id);
  if (sec !== 0) return dir === "asc" ? sec : -sec;
  return a.device_id.localeCompare(b.device_id);
}

export interface DeviceDataTableProps {
  devices: Device[];
  selectedDevices: Set<string>;
  onToggleDevice: (deviceId: string) => void;
}

export function DeviceDataTable({
  devices,
  selectedDevices,
  onToggleDevice,
}: DeviceDataTableProps) {
  const [widths, setWidths] = useState<Record<ColKey, number>>(() => ({ ...DEFAULT }));
  const widthsRef = useRef(widths);
  widthsRef.current = widths;

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const [search, setSearch] = useState("");
  const [connectivity, setConnectivity] = useState<ConnectivityFilter>("all");
  const [sdmFilter, setSdmFilter] = useState<SdmFilter>("all");
  const [sortField, setSortField] = useState<SortableColKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const drag = useRef<{ key: ColKey; startX: number; startW: number } | null>(null);

  const onResizeMove = useCallback((e: MouseEvent) => {
    const s = drag.current;
    if (!s) return;
    const delta = e.clientX - s.startX;
    const min = MIN[s.key];
    setWidths((w) => ({
      ...w,
      [s.key]: Math.max(min, s.startW + delta),
    }));
  }, []);

  const onResizeEnd = useCallback(() => {
    drag.current = null;
    document.removeEventListener("mousemove", onResizeMove);
    document.removeEventListener("mouseup", onResizeEnd);
  }, [onResizeMove]);

  const startResize = useCallback(
    (key: ColKey) => (e: React.MouseEvent) => {
      if (!RESIZABLE[key]) return;
      e.preventDefault();
      e.stopPropagation();
      drag.current = {
        key,
        startX: e.clientX,
        startW: widthsRef.current[key],
      };
      document.addEventListener("mousemove", onResizeMove);
      document.addEventListener("mouseup", onResizeEnd);
    },
    [onResizeMove, onResizeEnd]
  );

  useEffect(() => {
    return () => {
      document.removeEventListener("mousemove", onResizeMove);
      document.removeEventListener("mouseup", onResizeEnd);
    };
  }, [onResizeMove, onResizeEnd]);

  const filteredDevices = useMemo(() => {
    return devices.filter(
      (d) =>
        deviceMatchesConnectivity(d, connectivity) &&
        deviceMatchesSdm(d, sdmFilter) &&
        deviceMatchesSearch(d, search)
    );
  }, [devices, connectivity, sdmFilter, search]);

  const processedDevices = useMemo(() => {
    const list = [...filteredDevices];
    if (sortField) {
      list.sort((a, b) => compareDevices(a, b, sortField, sortDir));
    }
    return list;
  }, [filteredDevices, sortField, sortDir]);

  useEffect(() => {
    const maxPage = Math.max(0, Math.ceil(processedDevices.length / rowsPerPage) - 1);
    if (page > maxPage) setPage(maxPage);
  }, [processedDevices.length, rowsPerPage, page]);

  useEffect(() => {
    setPage(0);
  }, [search, connectivity, sdmFilter]);

  const tableMinWidth = useMemo(
    () => ORDER.reduce((sum, k) => sum + widths[k], 0),
    [widths]
  );

  const pagedDevices = useMemo(() => {
    const start = page * rowsPerPage;
    return processedDevices.slice(start, start + rowsPerPage);
  }, [processedDevices, page, rowsPerPage]);

  const handleSort = (key: SortableColKey) => {
    if (sortField !== key) {
      setSortField(key);
      setSortDir("asc");
    } else {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    }
  };

  const renderCell = (key: ColKey, row: Device) => {
    switch (key) {
      case "checkbox":
        return (
          <Checkbox
            size="small"
            checked={selectedDevices.has(row.device_id)}
            onChange={() => onToggleDevice(row.device_id)}
            sx={{
              p: 0.25,
              transition: "background-color 0.15s ease",
              "&:hover": { bgcolor: "action.hover" },
            }}
          />
        );
      case "name":
        return (
          <Tooltip title={row.name || ""} arrow>
            <Typography variant="body2" noWrap>
              {row.name}
            </Typography>
          </Tooltip>
        );
      case "organization":
        return (
          <Tooltip title={row.organization || ""} arrow>
            <Typography variant="body2" noWrap sx={{ color: row.organization ? "text.primary" : "text.disabled" }}>
              {row.organization || "—"}
            </Typography>
          </Tooltip>
        );
      case "serial_no":
        return (
          <Typography variant="body2" noWrap>
            {row.serial_no}
          </Typography>
        );
      case "model":
        return (
          <Typography variant="body2" noWrap>
            {row.model}
          </Typography>
        );
      case "ip_address":
        return (
          <Typography variant="body2" noWrap>
            {row.ip_address}
          </Typography>
        );
      case "device_status":
        return (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                flexShrink: 0,
                backgroundColor: row.device_status === 1 ? DOT_ONLINE : DOT_OFFLINE_OR_DISABLED,
                animation: row.device_status === 1 ? "pulse 2s infinite" : "none",
                "@keyframes pulse": {
                  "0%, 100%": { opacity: 1 },
                  "50%": { opacity: 0.6 },
                },
              }}
            />
            <Typography variant="body2" noWrap>
              {row.device_status === 1 ? "Online" : "Offline"}
            </Typography>
          </Box>
        );
      case "sdm_status": {
        const enabled = String(row.sdm_status) === "1";
        return (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                flexShrink: 0,
                backgroundColor: enabled ? DOT_ONLINE : DOT_OFFLINE_OR_DISABLED,
              }}
            />
            <Typography variant="body2" noWrap>
              {enabled ? "Enabled" : "Disabled"}
            </Typography>
          </Box>
        );
      }
      case "sdm_port": {
        const label = sdmPortDisplay(row);
        return (
          <Typography
            variant="body2"
            noWrap
            sx={{ color: label === "N/A" ? "text.secondary" : "text.primary" }}
          >
            {label}
          </Typography>
        );
      }
      case "mac_address":
        return (
          <Tooltip title={row.mac_address || ""} arrow>
            <Typography
              variant="body2"
              sx={{
                fontFamily: "monospace",
                fontSize: "0.85rem",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {row.mac_address}
            </Typography>
          </Tooltip>
        );
      default:
        return null;
    }
  };

  const headerCellSx = (key: ColKey) => ({
    width: widths[key],
    minWidth: MIN[key],
    maxWidth: key === "checkbox" ? widths[key] : undefined,
    position: "relative" as const,
    fontWeight: 600,
    color: "#424242",
    backgroundColor: "#f8fafb",
    borderBottom: "2px solid #e8eef2",
    borderRight: "1px solid #e8eef2",
    py: key === "checkbox" ? 0.75 : 1.1,
    px: key === "checkbox" ? 0.5 : 1.5,
    userSelect: "none" as const,
    overflow: "hidden",
  });

  const bodyCellSx = (key: ColKey) => ({
    width: widths[key],
    minWidth: MIN[key],
    maxWidth: key === "checkbox" ? widths[key] : undefined,
    borderRight: "1px solid #e8eef2",
    borderBottom: "1px solid #e8eef2",
    verticalAlign: "middle" as const,
    overflow: "hidden",
    py: key === "checkbox" ? 0.25 : 1,
    px: key === "checkbox" ? 0.5 : 1.5,
  });

  const emptyMessage =
    devices.length === 0
      ? "No devices in this location."
      : "No devices match your search or filters.";

  return (
    <Paper
      elevation={0}
      sx={{
        borderRadius: "8px",
        width: "100%",
        maxWidth: "100%",
        flex: 1,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        overflow: "hidden",
        bgcolor: "transparent",
        boxShadow: "none",
      }}
    >
      {/* Filters + table share one border so widths line up */}
      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          width: "100%",
          display: "flex",
          flexDirection: "column",
          border: "1px solid #e8eef2",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            gap: 1.5,
            rowGap: 1.25,
            p: 1.5,
            pr: 2,
            borderBottom: "1px solid #e8eef2",
            bgcolor: "#fafbfc",
            flexShrink: 0,
            width: "100%",
            boxSizing: "border-box",
          }}
        >
          <TextField
            size="small"
            placeholder="Search name, org, serial, model, IP, MAC, network…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: "text.secondary", fontSize: "1.15rem" }} />
                </InputAdornment>
              ),
            }}
            sx={{
              flex: "1 1 200px",
              minWidth: 0,
              maxWidth: "100%",
            }}
          />
          <Box
            sx={{
              display: "flex",
              flexWrap: "wrap",
              gap: 1.5,
              alignItems: "center",
              flexShrink: 0,
            }}
          >
            <FormControl size="small" sx={{ minWidth: 132, width: { xs: "100%", sm: 132 } }}>
              <InputLabel id="device-filter-conn">Connection</InputLabel>
              <Select<ConnectivityFilter>
                labelId="device-filter-conn"
                label="Connection"
                value={connectivity}
                onChange={(e: SelectChangeEvent<ConnectivityFilter>) =>
                  setConnectivity(e.target.value as ConnectivityFilter)
                }
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="online">Online</MenuItem>
                <MenuItem value="offline">Offline</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 132, width: { xs: "100%", sm: 132 } }}>
              <InputLabel id="device-filter-sdm">SDM</InputLabel>
              <Select<SdmFilter>
                labelId="device-filter-sdm"
                label="SDM"
                value={sdmFilter}
                onChange={(e: SelectChangeEvent<SdmFilter>) =>
                  setSdmFilter(e.target.value as SdmFilter)
                }
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="enabled">Enabled</MenuItem>
                <MenuItem value="disabled">Disabled</MenuItem>
              </Select>
            </FormControl>
          </Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              flex: { xs: "1 1 100%", lg: "0 0 auto" },
              ml: { lg: "auto" },
              textAlign: "right",
              whiteSpace: "nowrap",
            }}
          >
            Showing {filteredDevices.length} of {devices.length}
          </Typography>
        </Box>

        <TableContainer
          sx={{
            flex: "1 1 0%",
            minHeight: 160,
            minWidth: 0,
            width: "100%",
            overflow: "auto",
            bgcolor: "#fff",
          }}
        >
        <Table
          stickyHeader
          size="small"
          sx={{
            tableLayout: "fixed",
            minWidth: tableMinWidth,
            width: "100%",
            "& .MuiTableCell-root": { boxSizing: "border-box" },
          }}
        >
          <TableHead>
            <TableRow>
              {ORDER.map((key) => (
                <TableCell
                  key={key}
                  sx={headerCellSx(key)}
                  aria-label={key === "checkbox" ? "Select rows" : undefined}
                >
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: key === "checkbox" ? "center" : "flex-start",
                      pr: RESIZABLE[key] ? 1 : 0,
                    }}
                  >
                    {key === "checkbox" ? null : (
                      <TableSortLabel
                        active={sortField === key}
                        direction={sortField === key ? sortDir : "asc"}
                        onClick={() => handleSort(key)}
                      >
                        <Typography variant="body2" fontWeight={600} noWrap component="span">
                          {LABELS[key]}
                        </Typography>
                      </TableSortLabel>
                    )}
                  </Box>
                  {RESIZABLE[key] && (
                    <Box
                      onMouseDown={startResize(key)}
                      role="separator"
                      aria-orientation="vertical"
                      sx={{
                        position: "absolute",
                        right: 0,
                        top: 0,
                        bottom: 0,
                        width: 6,
                        cursor: "col-resize",
                        zIndex: 2,
                        "&:hover": { backgroundColor: "rgba(25, 118, 210, 0.12)" },
                      }}
                    />
                  )}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedDevices.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={ORDER.length}
                  align="center"
                  sx={{ py: 5, color: "text.secondary", border: "none" }}
                >
                  <Typography variant="body2">{emptyMessage}</Typography>
                </TableCell>
              </TableRow>
            ) : (
              pagedDevices.map((row) => {
                const selected = selectedDevices.has(row.device_id);
                return (
                  <TableRow
                    key={row.device_id}
                    hover
                    selected={selected}
                    sx={{
                      backgroundColor: "#fff",
                      transition: "background-color 0.2s ease",
                      "&:hover": {
                        backgroundColor: "#f8fafb !important",
                      },
                      "&.Mui-selected": {
                        backgroundColor: "#e3f2fd !important",
                        "&:hover": { backgroundColor: "#e3f2fd !important" },
                      },
                    }}
                  >
                    {ORDER.map((col) => (
                      <TableCell key={col} sx={bodyCellSx(col)}>
                        {renderCell(col, row)}
                      </TableCell>
                    ))}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
        </TableContainer>

        <TablePagination
          component="div"
          rowsPerPageOptions={[10, 25, 50]}
          count={processedDevices.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={(_, newPage) => setPage(newPage)}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          sx={{
            borderTop: "1px solid #e8eef2",
            flexShrink: 0,
            width: "100%",
            maxWidth: "100%",
            overflow: "hidden",
            bgcolor: "#fafbfc",
          }}
        />
      </Box>
    </Paper>
  );
}
