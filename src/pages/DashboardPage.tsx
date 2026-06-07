import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Box,
  Paper,
  Typography,
  Button,
  CircularProgress,
  Dialog,
  Stack,
  TextField,
  Chip,
  Divider,
  Avatar,
  Menu,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Tooltip,
  Skeleton,
} from "@mui/material";
import { DeviceDataTable } from "../components/DeviceDataTable";
import { useAuthStore } from "../store/authStore";
import { Device, Organization, Location } from "../utils/constants";
import api from "../services/api";
import CloudDownloadIcon from "@mui/icons-material/CloudDownload";
import ShareIcon from "@mui/icons-material/Share";
import LogoutIcon from "@mui/icons-material/Logout";
import StorageIcon from "@mui/icons-material/Storage";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import MenuIcon from "@mui/icons-material/Menu";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import RefreshIcon from "@mui/icons-material/Refresh";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import BusinessIcon from "@mui/icons-material/Business";
import LocationOnIcon from "@mui/icons-material/LocationOn";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import FileTransferBatch from "../components/FileTransferBatch";

type DeviceFetchMode =
  | { kind: "network"; networkId: string }
  | { kind: "org"; orgId: string }
  | { kind: "all" };

function normalizeDeviceRows(items: unknown[]): Device[] {
  return (items || []).map((rowUnknown) => {
    const row = rowUnknown as Record<string, unknown>;
    return {
    ...row,
    organization:
      row.organization !== undefined && row.organization !== null
        ? String(row.organization)
        : undefined,
    org_id:
      row.org_id !== undefined && row.org_id !== null ? String(row.org_id) : undefined,
    sdm_status:
      row.sdm_status !== undefined && row.sdm_status !== null
        ? String(row.sdm_status)
        : "0",
    sdm_port:
      row.sdm_port === undefined ||
      row.sdm_port === null ||
      row.sdm_port === ""
        ? null
        : String(row.sdm_port),
  } as Device;
  });
}

/** In-memory cache for locations + device lists (Insight + SDM). Cleared on account/env change. */
type InventoryCache = {
  locations: Record<string, Location[]>;
  byNetwork: Record<string, Device[]>;
  byOrg: Record<string, Device[]>;
  allOrgs: Device[] | null;
};

const emptyInventoryCache = (): InventoryCache => ({
  locations: {},
  byNetwork: {},
  byOrg: {},
  allOrgs: null,
});

export const DashboardPage: React.FC<{
  onLogout: () => void;
}> = ({ onLogout }) => {
  const auth = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"devices" | "transfer">("devices");
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  /** Locations keyed by org_id — each org is loaded when expanded (or on first-org init). */
  const [locationsByOrg, setLocationsByOrg] = useState<Record<string, Location[]>>({});
  const [devices, setDevices] = useState<Device[]>([]);
  const [deviceFetchMode, setDeviceFetchMode] = useState<DeviceFetchMode | null>(null);
  const deviceFetchModeRef = useRef<DeviceFetchMode | null>(null);
  const setFetchMode = (m: DeviceFetchMode | null) => {
    deviceFetchModeRef.current = m;
    setDeviceFetchMode(m);
  };
  const [selectedOrg, setSelectedOrg] = useState<string>("");
  const [selectedLocation, setSelectedLocation] = useState<string>("");
  const [selectedDevices, setSelectedDevices] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [loadingOrgs, setLoadingOrgs] = useState(false);
  /** Which org_id is currently fetching locations (tree spinner). */
  const [loadingOrgId, setLoadingOrgId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDialogOpen, setErrorDialogOpen] = useState(false);
  const [diagnosticsDialogOpen, setDiagnosticsDialogOpen] = useState(false);
  const [diagnosticsEmails, setDiagnosticsEmails] = useState("");
  const [operationInProgress, setOperationInProgress] = useState(false);
  const [profileAnchor, setProfileAnchor] = useState<null | HTMLElement>(null);
  const [expandedOrgs, setExpandedOrgs] = useState<Set<string>>(new Set());
  const [hierarchyOpen, setHierarchyOpen] = useState(true);

  const inventoryCacheRef = useRef<InventoryCache>(emptyInventoryCache());
  const lastInventorySessionRef = useRef<string>("");

  useEffect(() => {
    if (!auth.isAuthenticated || !auth.user_id || !auth.token || !auth.account_id) {
      lastInventorySessionRef.current = "";
      return;
    }
    const session = `${auth.user_id}|${auth.account_id}|${auth.environment}`;
    if (lastInventorySessionRef.current !== session) {
      lastInventorySessionRef.current = session;
      inventoryCacheRef.current = emptyInventoryCache();
    }
    void fetchOrganizations();
  }, [auth.isAuthenticated, auth.user_id, auth.account_id, auth.environment]);

  const fetchOrganizations = async () => {
    setLoadingOrgs(true);
    setError(null);
    try {
      const result = await api.getOrganizations(
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      const items = result.items || [];
      setOrganizations(items);
      setLocationsByOrg({});
      inventoryCacheRef.current.locations = {};
      inventoryCacheRef.current.byNetwork = {};
      inventoryCacheRef.current.byOrg = {};
      inventoryCacheRef.current.allOrgs = null;
      setExpandedOrgs(new Set());
      if (items.length > 0) {
        const firstId = items[0].org_id;
        setSelectedOrg(firstId);
        setExpandedOrgs(new Set([firstId]));
        await fetchLocationsForOrg(firstId, { selectFirstLocation: true });
      } else {
        setSelectedOrg("");
        setSelectedLocation("");
        setDevices([]);
        setFetchMode(null);
      }
    } catch (err: any) {
      const errorMsg = err.message || "Failed to fetch organizations";
      setError(errorMsg);
      setErrorDialogOpen(true);
    } finally {
      setLoadingOrgs(false);
    }
  };

  const fetchLocationsForOrg = async (
    org_id: string,
    options: { selectFirstLocation?: boolean; force?: boolean } = {}
  ) => {
    const { selectFirstLocation = false, force = false } = options;
    if (!force) {
      const cached = inventoryCacheRef.current.locations[org_id];
      if (cached) {
        setLocationsByOrg((prev) => ({ ...prev, [org_id]: cached }));
        if (selectFirstLocation) {
          if (cached.length > 0) {
            setSelectedLocation(cached[0].network_id);
            await fetchDevices(cached[0].network_id, { force: false });
          } else {
            setSelectedLocation("");
            setDevices([]);
            setFetchMode(null);
          }
        }
        return;
      }
    }
    setLoadingOrgId(org_id);
    setError(null);
    try {
      const result = await api.getLocations(
        org_id,
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      const items = result.items || [];
      inventoryCacheRef.current.locations[org_id] = items;
      setLocationsByOrg((prev) => ({ ...prev, [org_id]: items }));
      if (selectFirstLocation) {
        if (items.length > 0) {
          setSelectedLocation(items[0].network_id);
          await fetchDevices(items[0].network_id, { force: false });
        } else {
          setSelectedLocation("");
          setDevices([]);
          setFetchMode(null);
        }
      }
    } catch (err: any) {
      const errorMsg = err.message || "Failed to fetch locations";
      setError(errorMsg);
      setErrorDialogOpen(true);
      setLocationsByOrg((prev) => ({ ...prev, [org_id]: [] }));
    } finally {
      setLoadingOrgId(null);
    }
  };

  const fetchDevices = async (network_id: string, options: { force?: boolean } = {}) => {
    const { force = false } = options;
    if (!network_id || String(network_id).trim() === "") {
      setDevices([]);
      setFetchMode(null);
      setLoading(false);
      return;
    }
    setFetchMode({ kind: "network", networkId: network_id });
    setSelectedLocation(network_id);
    if (!force) {
      const cached = inventoryCacheRef.current.byNetwork[network_id];
      if (cached) {
        setDevices(cached.map((d) => ({ ...d })));
        setSelectedDevices(new Set());
        setLoading(false);
        return;
      }
    }
    setLoading(true);
    setError(null);
    setSelectedDevices(new Set());
    try {
      const result = await api.getDevices(
        network_id,
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      const rows = normalizeDeviceRows(result.items || []);
      inventoryCacheRef.current.byNetwork[network_id] = rows;
      setDevices(rows);
    } catch (err: any) {
      const errorMsg = err.message || "Failed to fetch devices";
      setError(errorMsg);
      setErrorDialogOpen(true);
    } finally {
      setLoading(false);
    }
  };

  const fetchApDevicesForOrg = async (orgId: string, options: { force?: boolean } = {}) => {
    const { force = false } = options;
    setFetchMode({ kind: "org", orgId });
    setSelectedLocation("");
    if (!force) {
      const cached = inventoryCacheRef.current.byOrg[orgId];
      if (cached) {
        setDevices(cached.map((d) => ({ ...d })));
        setSelectedDevices(new Set());
        setLoading(false);
        return;
      }
    }
    setLoading(true);
    setError(null);
    setSelectedDevices(new Set());
    try {
      const result = await api.getApDevicesForOrg(
        orgId,
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      const rows = normalizeDeviceRows(result.items || []);
      inventoryCacheRef.current.byOrg[orgId] = rows;
      setDevices(rows);
    } catch (err: any) {
      const errorMsg = err.message || "Failed to fetch AP devices for organization";
      setError(errorMsg);
      setErrorDialogOpen(true);
    } finally {
      setLoading(false);
    }
  };

  const fetchApDevicesAllOrgs = async (options: { force?: boolean } = {}) => {
    const { force = false } = options;
    setFetchMode({ kind: "all" });
    setSelectedLocation("");
    if (!force) {
      const cached = inventoryCacheRef.current.allOrgs;
      if (cached) {
        setDevices(cached.map((d) => ({ ...d })));
        setSelectedDevices(new Set());
        setLoading(false);
        return;
      }
    }
    setLoading(true);
    setError(null);
    setSelectedDevices(new Set());
    try {
      const result = await api.getApDevicesAllOrgs(
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      const rows = normalizeDeviceRows(result.items || []);
      inventoryCacheRef.current.allOrgs = rows;
      setDevices(rows);
    } catch (err: any) {
      const errorMsg = err.message || "Failed to fetch AP devices across organizations";
      setError(errorMsg);
      setErrorDialogOpen(true);
    } finally {
      setLoading(false);
    }
  };

  const refreshDeviceList = async () => {
    const m = deviceFetchModeRef.current;
    if (!m) return;
    if (m.kind === "network") await fetchDevices(m.networkId, { force: true });
    else if (m.kind === "org") await fetchApDevicesForOrg(m.orgId, { force: true });
    else await fetchApDevicesAllOrgs({ force: true });
  };

  const toggleDeviceSelection = useCallback((deviceId: string) => {
    setSelectedDevices((prev) => {
      const newSelected = new Set(prev);
      if (newSelected.has(deviceId)) {
        newSelected.delete(deviceId);
      } else {
        newSelected.add(deviceId);
      }
      return newSelected;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedDevices.size === devices.length) {
      setSelectedDevices(new Set());
    } else {
      setSelectedDevices(new Set(devices.map((d) => d.device_id)));
    }
  }, [devices, selectedDevices]);

  const isDeviceOnline = (d: Device) => d.device_status === 1;

  const bulkEnableSDM = async () => {
    const selected = devices.filter((d) => selectedDevices.has(d.device_id));
    if (selected.length === 0) {
      setError("Please select at least one device");
      setErrorDialogOpen(true);
      return;
    }

    const online = selected.filter(isDeviceOnline);
    const offline = selected.filter((d) => !isDeviceOnline(d));

    if (online.length === 0) {
      setError(
        "SDM cannot be enabled on offline devices. Only online devices support enabling SDM.\n\n" +
          `You selected ${offline.length} offline device(s):\n${offline.map((d) => `• ${d.name || d.serial_no}`).join("\n")}`
      );
      setErrorDialogOpen(true);
      return;
    }

    setOperationInProgress(true);
    let successCount = 0;
    const failedDevices: string[] = [];

    for (const device of online) {
      try {
        await api.enableSDM(
          device.device_id,
          device.network_id,
          auth.user_id!,
          auth.account_id!,
          auth.token!,
          auth.environment
        );
        successCount++;
      } catch (err: any) {
        failedDevices.push(`${device.name}: ${err.message}`);
      }
    }

    await refreshDeviceList();
    setSelectedDevices(new Set());
    setOperationInProgress(false);

    const offlineNote =
      offline.length > 0
        ? `\n\nSDM was enabled only on online devices. Skipped ${offline.length} offline device(s):\n${offline.map((d) => `• ${d.name || d.serial_no}`).join("\n")}`
        : "";

    if (failedDevices.length > 0) {
      setError(
        `Enabled SDM on ${successCount} of ${online.length} online device(s). Failed on ${failedDevices.length}:\n\n${failedDevices.join("\n")}${offlineNote}`
      );
      setErrorDialogOpen(true);
    } else if (offline.length > 0) {
      setError(
        `✓ Successfully enabled SDM on ${successCount} online device(s).${offlineNote}`
      );
      setErrorDialogOpen(true);
    } else {
      setError(`✓ Successfully enabled SDM on ${successCount} device(s)`);
      setErrorDialogOpen(true);
    }
  };

  const bulkDisableSDM = async () => {
    const selected = devices.filter((d) => selectedDevices.has(d.device_id));
    if (selected.length === 0) {
      setError("Please select at least one device");
      setErrorDialogOpen(true);
      return;
    }

    setOperationInProgress(true);
    let successCount = 0;
    let failedDevices: string[] = [];

    for (const device of selected) {
      try {
        await api.disableSDM(
          device.device_id,
          device.network_id,
          auth.user_id!,
          auth.account_id!,
          auth.token!,
          auth.environment
        );
        successCount++;
      } catch (err: any) {
        failedDevices.push(`${device.name}: ${err.message}`);
      }
    }

    await refreshDeviceList();
    setSelectedDevices(new Set());
    setOperationInProgress(false);

    if (failedDevices.length > 0) {
      setError(`Disabled SDM on ${successCount} device(s). Failed on ${failedDevices.length}:\n\n${failedDevices.join("\n")}`);
      setErrorDialogOpen(true);
    } else {
      setError(`✓ Successfully disabled SDM on ${successCount} device(s)`);
      setErrorDialogOpen(true);
    }
  };

  const shareDiagnostics = async () => {
    const selected = devices.filter((d) => selectedDevices.has(d.device_id));
    if (selected.length === 0) {
      setError("Please select at least one device");
      setErrorDialogOpen(true);
      return;
    }

    const emails = diagnosticsEmails.split(",").map((e) => e.trim()).filter((e) => e);
    if (emails.length === 0) {
      setError("Please enter at least one email address");
      setErrorDialogOpen(true);
      return;
    }

    setOperationInProgress(true);
    try {
      const result = await api.shareDiagnosticsBulk(
        selected,
        emails,
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );
      setDiagnosticsDialogOpen(false);
      setDiagnosticsEmails("");
      setError(`✓ Shared diagnostics for ${result.summary.succeeded}/${result.summary.total} device(s)`);
      setErrorDialogOpen(true);
    } catch (err: any) {
      setError(`Failed to share diagnostics: ${err.message}`);
      setErrorDialogOpen(true);
    } finally {
      setOperationInProgress(false);
    }
  };

  const exportDevices = async () => {
    const toExport = selectedDevices.size > 0 
      ? devices.filter((d) => selectedDevices.has(d.device_id))
      : devices;

    if (toExport.length === 0) {
      setError("No devices to export");
      setErrorDialogOpen(true);
      return;
    }

    try {
      const result = await api.exportDevices(
        toExport,
        auth.user_id!,
        auth.account_id!,
        auth.token!,
        auth.environment
      );

      const blob = new Blob([result.csv_data], { type: "text/csv" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "devices_export.csv";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(`Failed to export devices: ${err.message}`);
      setErrorDialogOpen(true);
    }
  };

  const getInitials = useCallback((email: string) => {
    const parts = email.split("@")[0].split(".");
    return parts.map((p) => p[0].toUpperCase()).join("").slice(0, 2);
  }, []);

  return (
    <Box
      sx={{
        display: "flex",
        height: "100vh",
        maxHeight: "100vh",
        minWidth: 0,
        overflow: "hidden",
        backgroundColor: "#e8eaed",
      }}
    >
      {/* Collapsible Left Sidebar */}
      <Drawer
        variant="permanent"
        sx={{
          width: sidebarOpen ? 220 : 0,
          flexShrink: 0,
          transition: "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          "& .MuiDrawer-paper": {
            width: sidebarOpen ? 220 : 0,
            boxSizing: "border-box",
            backgroundColor: "#ffffff",
            borderRight: "1px solid #e8eef2",
            transition: "width 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
            overflow: "hidden",
            boxShadow: sidebarOpen ? "2px 0 8px rgba(0,0,0,0.08)" : "none",
          },
        }}
      >
        <Box sx={{ p: 1.5, pt: 2 }}>
          <Typography
            variant="h6"
            sx={{
              fontWeight: "700",
              mb: 2,
              color: "#1976d2",
              fontSize: "1rem",
              letterSpacing: "0.5px",
            }}
          >
            SDM Manager
          </Typography>
          <List sx={{ padding: 0 }}>
            <ListItem disablePadding>
              <ListItemButton
                selected={activeTab === "devices"}
                onClick={() => setActiveTab("devices")}
                sx={{
                  borderRadius: "8px",
                  mb: 1,
                  transition: "all 0.2s ease",
                  "&.Mui-selected": {
                    backgroundColor: "#e3f2fd",
                    borderLeft: "3px solid #1976d2",
                    paddingLeft: "13px",
                  },
                  "&:hover": {
                    backgroundColor: "#f5f5f5",
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: "inherit" }}>
                  <StorageIcon />
                </ListItemIcon>
                <ListItemText primary="Device Management" />
              </ListItemButton>
            </ListItem>
            <ListItem disablePadding>
              <ListItemButton
                selected={activeTab === "transfer"}
                onClick={() => setActiveTab("transfer")}
                sx={{
                  borderRadius: "8px",
                  transition: "all 0.2s ease",
                  "&.Mui-selected": {
                    backgroundColor: "#e3f2fd",
                    borderLeft: "3px solid #1976d2",
                    paddingLeft: "13px",
                  },
                  "&:hover": {
                    backgroundColor: "#f5f5f5",
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: "inherit" }}>
                  <UploadFileIcon />
                </ListItemIcon>
                <ListItemText primary="File Transfer" />
              </ListItemButton>
            </ListItem>
          </List>
        </Box>
      </Drawer>

      {/* Main Content */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <Paper
          sx={{
            background: "linear-gradient(135deg, #1976d2 0%, #1565c0 100%)",
            px: 1.5,
            py: 1.25,
            flexShrink: 0,
            boxShadow: "0 1px 0 rgba(0, 0, 0, 0.06)",
            backgroundColor: "white",
          }}
        >
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <IconButton
                onClick={() => setSidebarOpen(!sidebarOpen)}
                sx={{
                  color: "white",
                  transition: "all 0.2s ease",
                  "&:hover": { backgroundColor: "rgba(255, 255, 255, 0.1)" },
                }}
              >
                {sidebarOpen ? <ChevronLeftIcon /> : <MenuIcon />}
              </IconButton>
              <Typography
                variant="h6"
                component="div"
                sx={{
                  fontWeight: "700",
                  color: "white",
                  letterSpacing: "0.02em",
                  fontSize: "1.1rem",
                }}
              >
                {activeTab === "devices" ? "Device Management" : "File Transfer"}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <Avatar
                sx={{
                  bgcolor: "#fff",
                  color: "#1976d2",
                  cursor: "pointer",
                  width: 40,
                  height: 40,
                  fontWeight: "700",
                  transition: "all 0.3s ease",
                  boxShadow: "0 2px 8px rgba(0, 0, 0, 0.15)",
                  "&:hover": {
                    transform: "scale(1.05)",
                    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.2)",
                  },
                }}
                onClick={(e) => setProfileAnchor(e.currentTarget)}
              >
                {getInitials(auth.email ?? "")}
              </Avatar>
              <Menu
                anchorEl={profileAnchor}
                open={Boolean(profileAnchor)}
                onClose={() => setProfileAnchor(null)}
                PaperProps={{
                  sx: {
                    borderRadius: "12px",
                    boxShadow: "0 8px 32px rgba(0, 0, 0, 0.12)",
                    mt: 1,
                  },
                }}
              >
                <Box sx={{ p: 2, minWidth: 250 }}>
                  <Typography
                    variant="subtitle2"
                    sx={{ fontWeight: "700", color: "#212121" }}
                  >
                    {auth.email}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ color: "#999", mb: 2, fontSize: "0.85rem" }}
                  >
                    {auth.environment}
                  </Typography>
                  <Divider sx={{ mb: 1 }} />
                  <Button
                    fullWidth
                    startIcon={<LogoutIcon />}
                    onClick={() => {
                      setProfileAnchor(null);
                      onLogout();
                    }}
                    sx={{
                      mt: 1,
                      justifyContent: "flex-start",
                      color: "#d32f2f",
                      transition: "all 0.2s ease",
                      "&:hover": { backgroundColor: "#ffebee" },
                    }}
                  >
                    Logout
                  </Button>
                </Box>
              </Menu>
            </Stack>
          </Box>
        </Paper>

        {/* Content Area — fills viewport; scroll only inside hierarchy/table */}
        <Box
          sx={{
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
            p: { xs: 0.5, sm: 1 },
          }}
        >
          {activeTab === "devices" ? (
            <Paper
              sx={{
                display: "flex",
                flexDirection: "row",
                alignItems: "stretch",
                flex: 1,
                minHeight: 0,
                minWidth: 0,
                borderRadius: { xs: 0, sm: "10px" },
                boxShadow: { xs: "none", sm: "0 1px 4px rgba(0, 0, 0, 0.08)" },
                overflow: "hidden",
                p: 0,
                bgcolor: "background.paper",
              }}
            >
              {hierarchyOpen && (
              <Box
                sx={{
                  width: 228,
                  flexShrink: 0,
                  borderRight: "1px solid",
                  borderColor: "divider",
                  bgcolor: "grey.50",
                  p: 1.25,
                  overflow: "auto",
                  display: "flex",
                  flexDirection: "column",
                  minHeight: 0,
                }}
              >
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    mb: 1.25,
                  }}
                >
                  <Typography
                    variant="subtitle2"
                    sx={{
                      fontWeight: "700",
                      color: "#212121",
                      fontSize: "0.9rem",
                    }}
                  >
                    Hierarchy Tree
                  </Typography>
                  <Tooltip title="Hide hierarchy panel" arrow>
                    <IconButton
                      size="small"
                      onClick={() => setHierarchyOpen(false)}
                      sx={{ color: "#1976d2" }}
                      aria-label="Hide hierarchy panel"
                    >
                      <ChevronLeftIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>

                {loadingOrgs ? (
                  <Box>
                    <Skeleton sx={{ mb: 1 }} />
                    <Skeleton sx={{ mb: 1 }} />
                    <Skeleton />
                  </Box>
                ) : (
                  <Box>
                    {/* All Organizations Item */}
                    <Box
                      sx={{
                        p: 1,
                        borderRadius: "6px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 1,
                        backgroundColor: !selectedOrg ? "#e3f2fd" : "#f5f5f5",
                        border: !selectedOrg ? "1px solid #90caf9" : "1px solid transparent",
                        transition: "all 0.2s ease",
                        "&:hover": {
                          backgroundColor: "#e3f2fd",
                        },
                      }}
                      onClick={() => {
                        setSelectedOrg("");
                        setSelectedLocation("");
                        void fetchApDevicesAllOrgs();
                      }}
                    >
                      <BusinessIcon sx={{ fontSize: "1.2rem", color: "#1976d2" }} />
                      <Typography variant="body2" sx={{ fontWeight: "500", flex: 1 }}>
                        All Organizations
                      </Typography>
                    </Box>

                    <Divider sx={{ my: 1 }} />

                    {/* Organizations with Locations */}
                    {organizations.map((org) => (
                      <Box key={org.org_id}>
                        <Box
                          sx={{
                            p: 1,
                            borderRadius: "6px",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 0.5,
                            mb: 0.5,
                            backgroundColor: selectedOrg === org.org_id ? "#e3f2fd" : "transparent",
                            border: selectedOrg === org.org_id ? "1px solid #90caf9" : "1px solid transparent",
                            transition: "all 0.2s ease",
                            "&:hover": {
                              backgroundColor: "#f5f5f5",
                            },
                          }}
                          onClick={() => {
                            setSelectedOrg(org.org_id);
                            void fetchApDevicesForOrg(org.org_id);
                            if (expandedOrgs.has(org.org_id)) {
                              setExpandedOrgs((prev) => {
                                const newSet = new Set(prev);
                                newSet.delete(org.org_id);
                                return newSet;
                              });
                            } else {
                              setExpandedOrgs((prev) => new Set(prev).add(org.org_id));
                              if (locationsByOrg[org.org_id] === undefined) {
                                void fetchLocationsForOrg(org.org_id, {
                                  selectFirstLocation: false,
                                });
                              }
                            }
                          }}
                        >
                          {expandedOrgs.has(org.org_id) ? (
                            <KeyboardArrowDownIcon sx={{ fontSize: "1.2rem", color: "#666" }} />
                          ) : (
                            <KeyboardArrowRightIcon sx={{ fontSize: "1.2rem", color: "#666" }} />
                          )}
                          <BusinessIcon sx={{ fontSize: "1rem", color: "#1976d2" }} />
                          <Typography variant="body2" sx={{ fontWeight: "500", flex: 1, fontSize: "0.9rem" }}>
                            {org.org_name}
                          </Typography>
                          <Chip label={org.location_count} size="small" sx={{ fontSize: "0.7rem", height: 20 }} />
                        </Box>

                        {/* Locations under Organization (per-org cache; load on expand) */}
                        {expandedOrgs.has(org.org_id) && (
                          <Box sx={{ pl: 1 }}>
                            {loadingOrgId === org.org_id ? (
                              <Box sx={{ display: "flex", justifyContent: "center", py: 1.5, pl: 3 }}>
                                <CircularProgress size={22} />
                              </Box>
                            ) : (locationsByOrg[org.org_id] ?? []).length === 0 ? (
                              <Typography
                                variant="caption"
                                sx={{ display: "block", pl: 4, py: 1, color: "text.secondary" }}
                              >
                                No locations for this organization (Insight returned no networks for this account/org).
                              </Typography>
                            ) : (
                              (locationsByOrg[org.org_id] ?? []).map((loc) => (
                              <Box
                                key={loc.network_id}
                                sx={{
                                  pl: 3,
                                  p: 1,
                                  borderRadius: "6px",
                                  cursor: "pointer",
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 1,
                                  mb: 0.5,
                                  backgroundColor: selectedLocation === loc.network_id ? "#e8f5e9" : "transparent",
                                  border: selectedLocation === loc.network_id ? "1px solid #81c784" : "1px solid transparent",
                                  transition: "all 0.2s ease",
                                  "&:hover": {
                                    backgroundColor: "#f5f5f5",
                                  },
                                }}
                                onClick={() => {
                                  if (selectedOrg !== org.org_id) {
                                    setSelectedOrg(org.org_id);
                                  }
                                  setSelectedLocation(loc.network_id);
                                  fetchDevices(loc.network_id);
                                }}
                              >
                                <LocationOnIcon sx={{ fontSize: "1rem", color: "#4caf50" }} />
                                <Typography variant="body2" sx={{ flex: 1, fontSize: "0.85rem" }}>
                                  {loc.network_name}
                                </Typography>
                                <Chip label={loc.device_count} size="small" sx={{ fontSize: "0.65rem", height: 18 }} />
                              </Box>
                            )))
                          }
                          </Box>
                        )}
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
              )}

              {/* Table area: toolbar + grid (same card as hierarchy) */}
              <Box
                sx={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  minWidth: 0,
                  minHeight: 0,
                  p: { xs: 1, sm: 1.25 },
                  pt: 1.25,
                }}
              >
                {/* Devices: title + hierarchy + actions on one aligned row */}
                <Box
                  sx={{
                    mb: 1.25,
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 1.25,
                    rowGap: 1,
                    pb: 1.25,
                    borderBottom: "1px solid #e8eef2",
                    justifyContent: "space-between",
                  }}
                >
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      minWidth: 0,
                    }}
                  >
                    <Tooltip
                      title={hierarchyOpen ? "Hide hierarchy panel" : "Show hierarchy panel"}
                      arrow
                    >
                      <IconButton
                        size="small"
                        onClick={() => setHierarchyOpen(!hierarchyOpen)}
                        aria-label={hierarchyOpen ? "Hide hierarchy panel" : "Show hierarchy panel"}
                        sx={{
                          color: "#1976d2",
                          border: "1px solid #e0e0e0",
                          bgcolor: "background.paper",
                          flexShrink: 0,
                          "&:hover": { backgroundColor: "#e3f2fd" },
                        }}
                      >
                        <AccountTreeIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Typography
                      variant="h6"
                      component="h2"
                      sx={{
                        fontWeight: 600,
                        color: "#212121",
                        fontSize: "1.1rem",
                        lineHeight: 1.2,
                      }}
                    >
                      Devices
                    </Typography>
                  </Box>

                  <Box
                    sx={{
                      display: "flex",
                      gap: 1,
                      alignItems: "center",
                      flexWrap: "wrap",
                      justifyContent: "flex-end",
                      flex: { xs: "1 1 100%", sm: "0 1 auto" },
                      ml: { sm: "auto" },
                    }}
                  >
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={toggleSelectAll}
                      sx={{
                        borderRadius: "8px",
                        textTransform: "none",
                        transition: "all 0.2s ease",
                        "&:hover": {
                          backgroundColor: "#f5f5f5",
                        },
                      }}
                    >
                      {selectedDevices.size === devices.length
                        ? "Deselect All"
                        : "Select All"}
                    </Button>

                    <Tooltip title="Refresh device list from API (bypass cache)" arrow>
                      <IconButton
                        size="small"
                        onClick={() => void refreshDeviceList()}
                        disabled={loading || !deviceFetchMode}
                        sx={{
                          color: "#1976d2",
                          border: "1px solid #e0e0e0",
                          bgcolor: "background.paper",
                          transition: "all 0.2s ease",
                          "&:hover": {
                            backgroundColor: "#e3f2fd",
                            transform: "rotate(20deg)",
                          },
                          "&:disabled": {
                            color: "#ccc",
                            borderColor: "#eee",
                          },
                        }}
                        aria-label="Refresh device list"
                      >
                        <RefreshIcon />
                      </IconButton>
                    </Tooltip>

                    {selectedDevices.size > 0 && (
                      <>
                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<CheckCircleIcon />}
                          onClick={bulkEnableSDM}
                          disabled={operationInProgress}
                          sx={{
                            backgroundColor: "#4caf50",
                            borderRadius: "8px",
                            textTransform: "none",
                            fontWeight: "600",
                            transition: "all 0.2s ease",
                            "&:hover": {
                              backgroundColor: "#45a049",
                              transform: "translateY(-2px)",
                              boxShadow: "0 4px 12px rgba(76, 175, 80, 0.3)",
                            },
                            "&:disabled": {
                              backgroundColor: "#ccc",
                            },
                          }}
                        >
                          Enable
                        </Button>

                        <Button
                          size="small"
                          variant="contained"
                          startIcon={<CancelIcon />}
                          onClick={bulkDisableSDM}
                          disabled={operationInProgress}
                          sx={{
                            backgroundColor: "#f44336",
                            borderRadius: "8px",
                            textTransform: "none",
                            fontWeight: "600",
                            transition: "all 0.2s ease",
                            "&:hover": {
                              backgroundColor: "#da190b",
                              transform: "translateY(-2px)",
                              boxShadow: "0 4px 12px rgba(244, 67, 54, 0.3)",
                            },
                            "&:disabled": {
                              backgroundColor: "#ccc",
                            },
                          }}
                        >
                          Disable
                        </Button>
                      </>
                    )}

                    {selectedDevices.size > 0 && (
                      <>
                        <Tooltip
                          title="Share diagnostics with selected devices"
                          arrow
                        >
                          <IconButton
                            size="small"
                            onClick={() => setDiagnosticsDialogOpen(true)}
                            disabled={operationInProgress}
                            sx={{
                              color: "#1976d2",
                              transition: "all 0.2s ease",
                              "&:hover": {
                                backgroundColor: "#e3f2fd",
                                transform: "scale(1.1)",
                              },
                              "&:disabled": {
                                color: "#ccc",
                              },
                            }}
                          >
                            <ShareIcon />
                          </IconButton>
                        </Tooltip>

                        <Tooltip
                          title="Download selected devices as CSV"
                          arrow
                        >
                          <IconButton
                            size="small"
                            onClick={exportDevices}
                            disabled={operationInProgress}
                            sx={{
                              color: "#1976d2",
                              transition: "all 0.2s ease",
                              "&:hover": {
                                backgroundColor: "#e3f2fd",
                                transform: "scale(1.1)",
                              },
                              "&:disabled": {
                                color: "#ccc",
                              },
                            }}
                          >
                            <CloudDownloadIcon />
                          </IconButton>
                        </Tooltip>
                      </>
                    )}
                  </Box>
                </Box>

                {/* Data Grid */}
                {loading ? (
                  <Box
                    sx={{
                      flex: 1,
                      minHeight: 0,
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      py: 4,
                    }}
                  >
                    <CircularProgress />
                  </Box>
                ) : (
                  <Box
                    sx={{
                      minWidth: 0,
                      width: "100%",
                      flex: 1,
                      minHeight: 0,
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <DeviceDataTable
                      devices={devices}
                      selectedDevices={selectedDevices}
                      onToggleDevice={toggleDeviceSelection}
                    />
                  </Box>
                )}
              </Box>
            </Paper>
          ) : (
            <Box sx={{ flex: 1, minHeight: 0, minWidth: 0, overflow: "auto", p: { xs: 0.5, sm: 0.75 } }}>
              <FileTransferBatch managerDevices={devices} />
            </Box>
          )}
        </Box>
      </Box>

      {/* Error Dialog */}
      <Dialog
        open={errorDialogOpen}
        onClose={() => setErrorDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: "12px",
            boxShadow: "0 20px 60px rgba(0, 0, 0, 0.15)",
          },
        }}
      >
        <Box sx={{ p: 3 }}>
          <Typography
            variant="h6"
            sx={{
              mb: 2,
              fontWeight: "700",
              color: error?.includes("✓") ? "#4caf50" : "#d32f2f",
            }}
          >
            {error?.includes("✓")
              ? "Success"
              : error?.includes("Failed") || error?.includes("Error")
              ? "Error"
              : "Information"}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              mb: 3,
              whiteSpace: "pre-wrap",
              color: "#424242",
              lineHeight: "1.6",
            }}
          >
            {error}
          </Typography>
          <Button
            variant="contained"
            onClick={() => setErrorDialogOpen(false)}
            fullWidth
            sx={{
              borderRadius: "8px",
              textTransform: "none",
              fontWeight: "600",
              transition: "all 0.2s ease",
              "&:hover": {
                transform: "translateY(-2px)",
              },
            }}
          >
            Close
          </Button>
        </Box>
      </Dialog>

      {/* Share Diagnostics Dialog */}
      <Dialog
        open={diagnosticsDialogOpen}
        onClose={() => setDiagnosticsDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: "12px",
            boxShadow: "0 20px 60px rgba(0, 0, 0, 0.15)",
          },
        }}
      >
        <Box sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: "700" }}>
            Share Diagnostics
          </Typography>
          <Typography
            variant="body2"
            sx={{ mb: 2, color: "#666", fontSize: "0.95rem" }}
          >
            Enter email addresses (comma-separated):
          </Typography>
          <TextField
            fullWidth
            multiline
            rows={4}
            placeholder="user1@example.com, user2@example.com"
            value={diagnosticsEmails}
            onChange={(e) => setDiagnosticsEmails(e.target.value)}
            disabled={operationInProgress}
            sx={{
              mb: 2,
              "& .MuiOutlinedInput-root": {
                borderRadius: "8px",
                transition: "all 0.2s ease",
              },
            }}
          />
          <Stack direction="row" spacing={2}>
            <Button
              variant="contained"
              onClick={shareDiagnostics}
              disabled={operationInProgress}
              fullWidth
              sx={{
                borderRadius: "8px",
                textTransform: "none",
                fontWeight: "600",
                transition: "all 0.2s ease",
                "&:hover": {
                  transform: "translateY(-2px)",
                },
              }}
            >
              {operationInProgress ? "Sending..." : "Send"}
            </Button>
            <Button
              variant="outlined"
              onClick={() => setDiagnosticsDialogOpen(false)}
              disabled={operationInProgress}
              sx={{
                borderRadius: "8px",
                textTransform: "none",
                fontWeight: "600",
              }}
            >
              Cancel
            </Button>
          </Stack>
        </Box>
      </Dialog>
    </Box>
  );
};