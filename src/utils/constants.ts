/**
 * Application constants and types
 */

export interface AuthState {
  isAuthenticated: boolean;
  user_id: string | null;
  token: string | null;
  account_id: string | null;
  email: string | null;
  environment: string;
}

export interface Organization {
  org_id: string;
  org_name: string;
  location_count: number;
  device_count: number;
}

export interface Location {
  network_id: string;
  network_name: string;
  device_count: number;
  ap_count: number;
}

export interface Device {
  device_id: string;
  serial_no: string;
  name: string;
  model: string;
  ip_address: string;
  mac_address: string;
  network_id: string;
  network_name: string;
  device_status: number;
  last_seen: number;
  sdm_status: string;
  sdm_port: string | null;
  /** Set when AP list is aggregated by org or all orgs */
  organization?: string;
  org_id?: string;
}

/**
 * Insight environment keys — shown and sent verbatim (matches backend auth_service keys).
 */
export const ENVIRONMENTS = [
  "pri-qa",
  "demo-aux",
  "maint-qa",
  "production",
  "beta",
  "demo",
  "maint-beta",
  "maint-dev",
  "pri-dev",
] as const;

export type EnvironmentId = (typeof ENVIRONMENTS)[number];

export const API_BASE_URL = "http://127.0.0.1:8000";
