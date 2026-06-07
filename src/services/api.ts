import axios, { AxiosInstance } from "axios";
import { API_BASE_URL } from "../utils/constants";

class APIService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
    });
  }

  private getAuthHeaders(
    user_id?: string,
    account_id?: string,
    token?: string,
    environment?: string
  ) {
    const headers: Record<string, string> = {};
    if (user_id) headers["user-id"] = user_id;
    if (account_id) headers["account-id"] = account_id;
    if (token) headers["token"] = token;
    if (environment) headers["environment"] = environment;
    return headers;
  }

  // Authentication
  async login(email: string, password: string, environment: string = "pri-qa") {
    try {
      const response = await this.api.post("/api/v1/auth/login", {
        email,
        password,
        environment,
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Organizations - REAL API
  async getOrganizations(
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.get("/api/v1/orgs/", {
        headers: this.getAuthHeaders(user_id, account_id, token, environment),
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Locations - REAL API
  async getLocations(
    org_id: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.get(`/api/v1/devices/locations/${org_id}`, {
        headers: this.getAuthHeaders(user_id, account_id, token, environment),
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // Devices - REAL API
  async getDevices(
    network_id: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.get(`/api/v1/devices/${network_id}`, {
        headers: this.getAuthHeaders(user_id, account_id, token, environment),
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getApDevicesForOrg(
    org_id: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const enc = encodeURIComponent(org_id);
      const response = await this.api.get(`/api/v1/orgs/${enc}/ap-devices`, {
        headers: this.getAuthHeaders(user_id, account_id, token, environment),
        timeout: 120000,
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async getApDevicesAllOrgs(
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.get("/api/v1/ap-devices/all-orgs", {
        headers: this.getAuthHeaders(user_id, account_id, token, environment),
        timeout: 180000,
      });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async loginManual(
    user_id: string,
    account_id: string,
    token: string,
    environment: string,
    email?: string
  ) {
    try {
      const body: Record<string, string> = {
        user_id,
        account_id,
        token,
        environment,
      };
      if (email?.trim()) {
        body.email = email.trim();
      }
      const response = await this.api.post("/api/v1/auth/manual", body, { timeout: 45000 });
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // SDM Operations
  async getSDMStatus(
    deviceId: string,
    networkId: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.get(
        `/api/v1/sdm/status/${deviceId}/${networkId}`,
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async enableSDM(
    deviceId: string,
    networkId: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/sdm/enable",
        { device_id: deviceId, network_id: networkId },
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async disableSDM(
    deviceId: string,
    networkId: string,
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/sdm/disable",
        { device_id: deviceId, network_id: networkId },
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async shareDiagnostics(
    deviceId: string,
    networkId: string,
    emailList: string[],
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/sdm/diagnostics",
        { device_id: deviceId, network_id: networkId, email_list: emailList },
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  // SSH Operations
  async executeSSHCommand(
    deviceSerial: string,
    ipAddress: string,
    sdmPort: number,
    command: string,
    timeout?: number
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/ssh/execute",
        {
          device_serial: deviceSerial,
          ip_address: ipAddress,
          sdm_port: sdmPort,
          command,
          timeout: timeout || 30,
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async uploadFile(
    deviceSerial: string,
    ipAddress: string,
    sdmPort: number,
    localPath: string,
    remotePath: string,
    timeout?: number
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/ssh/upload",
        {
          device_serial: deviceSerial,
          ip_address: ipAddress,
          sdm_port: sdmPort,
          local_path: localPath,
          remote_path: remotePath,
          timeout: timeout || 60,
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async downloadFile(
    deviceSerial: string,
    ipAddress: string,
    sdmPort: number,
    remotePath: string,
    localPath: string,
    timeout?: number
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/ssh/download",
        {
          device_serial: deviceSerial,
          ip_address: ipAddress,
          sdm_port: sdmPort,
          remote_path: remotePath,
          local_path: localPath,
          timeout: timeout || 60,
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async executeBatchCommands(
    deviceSerial: string,
    ipAddress: string,
    sdmPort: number,
    commands: string[],
    timeout?: number
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/ssh/batch",
        {
          device_serial: deviceSerial,
          ip_address: ipAddress,
          sdm_port: sdmPort,
          commands,
          timeout: timeout || 60,
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async parseBatchCsv(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    const response = await this.api.post("/api/v1/batch/parse-csv", formData, {
      timeout: 120000,
    });
    return response.data;
  }

  async batchExecute(body: Record<string, unknown>) {
    const response = await this.api.post("/api/v1/batch/execute", body, {
      timeout: 600000,
    });
    return response.data;
  }

  async batchTransfer(body: Record<string, unknown>) {
    const response = await this.api.post("/api/v1/batch/transfer", body, {
      timeout: 600000,
    });
    return response.data;
  }

  async ftCapabilities() {
    const response = await this.api.get("/api/v1/ft/capabilities");
    return response.data as {
      sshcommand_available: boolean;
      sshcommand_error: string | null;
    };
  }

  async ftConnect(body: Record<string, unknown>) {
    const response = await this.api.post("/api/v1/ft/connect", body, { timeout: 600000 });
    return response.data;
  }

  async ftDisconnect() {
    const response = await this.api.post("/api/v1/ft/disconnect");
    return response.data;
  }

  async ftTransferStop() {
    const response = await this.api.post("/api/v1/ft/transfer/stop");
    return response.data;
  }

  async ftSessions() {
    const response = await this.api.get("/api/v1/ft/sessions");
    return response.data as {
      sshcommand_available: boolean;
      sshcommand_error: string | null;
      sessions: { key: string; status: string }[];
    };
  }

  async ftExplorerLocalList(path: string) {
    const response = await this.api.post("/api/v1/ft/explorer/local-list", { path });
    return response.data as { success: boolean; error?: string | null; entries?: string[] };
  }

  async ftExplorerRemoteList(body: Record<string, unknown>) {
    const response = await this.api.post("/api/v1/ft/explorer/remote-list", body, { timeout: 120000 });
    return response.data as { success: boolean; error?: string | null; entries?: string[] };
  }

  // Export & Diagnostics
  async exportDevices(
    devices: any[],
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/devices/export",
        { devices },
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  async shareDiagnosticsBulk(
    devices: any[],
    emailList: string[],
    user_id: string,
    account_id: string,
    token: string,
    environment: string
  ) {
    try {
      const response = await this.api.post(
        "/api/v1/sdm/diagnostics/bulk",
        { devices, email_list: emailList },
        {
          headers: this.getAuthHeaders(user_id, account_id, token, environment),
        }
      );
      return response.data;
    } catch (error) {
      throw this.handleError(error);
    }
  }

  private handleError(error: any) {
    if (axios.isAxiosError(error)) {
      const data = error.response?.data as Record<string, unknown> | undefined;
      const message =
        (data && typeof data.error === "string" && data.error) ||
        (data && typeof data.detail === "string" && data.detail) ||
        error.message;
      return new Error(String(message));
    }
    return error;
  }
}

export default new APIService();
