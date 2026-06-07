import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import theme from "./styles/theme";
import { useAuthStore } from "./store/authStore";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";

function App() {
  const { isAuthenticated } = useAuthStore();
  const logout = useAuthStore((state) => state.logout);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        component="div"
        sx={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {isAuthenticated ? (
          <DashboardPage
            onLogout={() => {
              logout();
            }}
          />
        ) : (
          <AuthPage
            onAuthSuccess={() => {
              // Just switch UI, no reload needed (auth state is in localStorage now)
            }}
          />
        )}
      </Box>
    </ThemeProvider>
  );
}

export default App;
