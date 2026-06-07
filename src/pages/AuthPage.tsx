import React, { useState } from "react";
import {
  Container,
  Paper,
  TextField,
  Button,
  Box,
  Typography,
  MenuItem,
  Alert,
  CircularProgress,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import { useAuthStore } from "../store/authStore";
import { ENVIRONMENTS } from "../utils/constants";
import api from "../services/api";

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`login-tabpanel-${index}`}
      aria-labelledby={`login-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

export const AuthPage: React.FC<{
  onAuthSuccess: () => void;
}> = ({ onAuthSuccess }) => {
  const [tabValue, setTabValue] = useState(0);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [manualUserId, setManualUserId] = useState("");
  const [manualAccountId, setManualAccountId] = useState("");
  const [manualToken, setManualToken] = useState("");
  const [environment, setEnvironment] = useState<string>("pri-qa");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const setAuth = useAuthStore((state) => state.setAuth);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    if (!email || !password) {
      setError("Enter your email and password.");
      setLoading(false);
      return;
    }

    try {
      const result = await api.login(email, password, environment);

      if (result.success) {
        setSuccess("Signed in. Loading your workspace…");
        setAuth({
          isAuthenticated: true,
          user_id: result.user_id,
          token: result.token,
          account_id: result.account_id,
          email: result.email,
          environment: result.environment,
        });
        setTimeout(() => {
          onAuthSuccess();
        }, 800);
      } else {
        if (result.error && result.error.includes("not exist")) {
          setError("No account found for that email.");
        } else if (result.error && result.error.includes("password")) {
          setError("Incorrect password.");
        } else if (result.error && result.error.includes("not match")) {
          setError("Email and password not match.");
        } else {
          setError(result.error || "Sign-in failed. Try again.");
        }
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : String(err);

      if (errorMsg.includes("401")) {
        setError("Email or password is incorrect.");
      } else if (errorMsg.includes("403")) {
        setError("Access denied. Your account may be locked or disabled.");
      } else if (errorMsg.includes("404")) {
        setError("Service not found for this environment.");
      } else if (errorMsg.includes("Network")) {
        setError("Network error. Check your connection.");
      } else if (errorMsg.includes("timeout")) {
        setError("Request timed out. Please try again.");
      } else {
        setError(errorMsg || "Something went wrong.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleManualLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    const uid = manualUserId.trim();
    const aid = manualAccountId.trim();
    const tok = manualToken.trim();

    if (!uid || !aid || !tok) {
      setError("User ID, Account ID, and Access Token are required.");
      setLoading(false);
      return;
    }

    try {
      const result = await api.loginManual(uid, aid, tok, environment);

      if (result.success) {
        setSuccess("Session verified. Loading your workspace…");
        setAuth({
          isAuthenticated: true,
          user_id: result.user_id,
          token: result.token,
          account_id: result.account_id,
          email: result.email,
          environment: result.environment ?? environment,
        });
        setTimeout(() => {
          onAuthSuccess();
        }, 600);
      } else {
        setError(result.error || "Could not verify this session.");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg || "Session verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const envField = (
    <TextField
      select
      fullWidth
      size="small"
      label="Environment"
      value={environment}
      onChange={(e) => setEnvironment(e.target.value)}
      disabled={loading}
      sx={{
        "& .MuiSelect-select": { fontFamily: "ui-monospace, monospace", fontSize: "0.9rem" },
      }}
    >
      {ENVIRONMENTS.map((id) => (
        <MenuItem key={id} value={id} dense sx={{ fontFamily: "ui-monospace, monospace", fontSize: "0.875rem" }}>
          {id}
        </MenuItem>
      ))}
    </TextField>
  );

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        py: 3,
        px: 2,
        bgcolor: "#eceff1",
      }}
    >
      <Container maxWidth="xs" disableGutters sx={{ maxWidth: 380 }}>
        <Paper
          elevation={0}
          sx={{
            borderRadius: "14px",
            border: "1px solid #cfd8dc",
            boxShadow: "0 1px 3px rgba(0,0,0,.08)",
            overflow: "hidden",
            bgcolor: "#fff",
          }}
        >
          <Box sx={{ px: 3, pt: 3, pb: 2 }}>
            <Typography
              component="h1"
              sx={{
                fontWeight: 700,
                fontSize: "1.25rem",
                letterSpacing: "-0.03em",
                color: "#263238",
              }}
            >
              SDM Manager
            </Typography>
            <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "#78909c", lineHeight: 1.4 }}>
              Netgear Insight · Secure Diagnostic Mode
            </Typography>
          </Box>

          <Box
            sx={{
              px: 1.5,
              pb: 0.5,
              borderTop: "1px solid #eceff1",
              borderBottom: "1px solid #eceff1",
              bgcolor: "#fafafa",
            }}
          >
            <ToggleButtonGroup
              exclusive
              fullWidth
              value={tabValue}
              onChange={(_e, v) => v !== null && setTabValue(v)}
              aria-label="Sign-in method"
              sx={{
                gap: 0.5,
                py: 1,
                "& .MuiToggleButtonGroup-grouped": {
                  border: "none",
                  borderRadius: "8px !important",
                  mx: 0,
                  py: 0.75,
                  textTransform: "none",
                  fontWeight: 600,
                  fontSize: "0.8125rem",
                  color: "#546e7a",
                  "&.Mui-selected": {
                    bgcolor: "#fff",
                    color: "#1565c0",
                    boxShadow: "0 1px 2px rgba(0,0,0,.06)",
                    "&:hover": { bgcolor: "#fff" },
                  },
                },
              }}
            >
              <ToggleButton value={0} id="login-tab-0" aria-controls="login-tabpanel-0">
                Email
              </ToggleButton>
              <ToggleButton value={1} id="login-tab-1" aria-controls="login-tabpanel-1">
                Session
              </ToggleButton>
            </ToggleButtonGroup>
          </Box>

          <Box sx={{ px: 3, pb: 3, pt: 2 }}>
            {error && (
              <Alert severity="error" sx={{ mb: 2, py: 0.5, fontSize: "0.8125rem" }} onClose={() => setError(null)}>
                {error}
              </Alert>
            )}

            {success && (
              <Alert severity="success" sx={{ mb: 2, py: 0.5, fontSize: "0.8125rem" }}>
                {success}
              </Alert>
            )}

            <TabPanel value={tabValue} index={0}>
              <Box component="form" onSubmit={handleLogin}>
                <Stack spacing={2}>
                  {envField}

                  <TextField
                    fullWidth
                    label="Email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={loading}
                    autoComplete="email"
                    size="small"
                  />

                  <TextField
                    fullWidth
                    label="Password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    disabled={loading}
                    autoComplete="current-password"
                    size="small"
                  />

                  <Button
                    fullWidth
                    variant="contained"
                    disableElevation
                    type="submit"
                    disabled={loading}
                    sx={{
                      mt: 0.5,
                      py: 1.1,
                      borderRadius: "10px",
                      textTransform: "none",
                      fontWeight: 600,
                      bgcolor: "#1565c0",
                      "&:hover": { bgcolor: "#0d47a1" },
                    }}
                  >
                    {loading ? <CircularProgress size={22} color="inherit" /> : "Sign in"}
                  </Button>
                </Stack>
              </Box>
            </TabPanel>

            <TabPanel value={tabValue} index={1}>
              <Box component="form" onSubmit={handleManualLogin}>
                <Stack spacing={2}>
                  <Typography variant="caption" sx={{ color: "#78909c", lineHeight: 1.5, display: "block" }}>
                    Signed into{" "}
                    <Box component="span" sx={{ fontFamily: "ui-monospace, monospace", color: "#37474f" }}>
                      {environment}
                    </Box>{" "}
                    in the browser? Paste cookies <strong>_Id</strong>, <strong>accountId</strong>,{" "}
                    <strong>accessToken</strong> (DevTools → Application).
                  </Typography>

                  {envField}

                  <TextField
                    fullWidth
                    label="User ID"
                    value={manualUserId}
                    onChange={(e) => setManualUserId(e.target.value)}
                    required
                    disabled={loading}
                    autoComplete="username"
                    size="small"
                  />

                  <TextField
                    fullWidth
                    label="Account ID"
                    value={manualAccountId}
                    onChange={(e) => setManualAccountId(e.target.value)}
                    required
                    disabled={loading}
                    size="small"
                  />

                  <TextField
                    fullWidth
                    label="Access token"
                    type="password"
                    value={manualToken}
                    onChange={(e) => setManualToken(e.target.value)}
                    required
                    disabled={loading}
                    autoComplete="new-password"
                    size="small"
                  />

                  <Button
                    fullWidth
                    variant="contained"
                    disableElevation
                    type="submit"
                    disabled={loading}
                    sx={{
                      mt: 0.5,
                      py: 1.1,
                      borderRadius: "10px",
                      textTransform: "none",
                      fontWeight: 600,
                      bgcolor: "#1565c0",
                      "&:hover": { bgcolor: "#0d47a1" },
                    }}
                  >
                    {loading ? <CircularProgress size={22} color="inherit" /> : "Continue"}
                  </Button>
                </Stack>
              </Box>
            </TabPanel>
          </Box>
        </Paper>
      </Container>
    </Box>
  );
};
