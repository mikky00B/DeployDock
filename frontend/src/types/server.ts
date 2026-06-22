export type ServerStatus = "unknown" | "connected" | "unreachable";

export type Server = {
  id: string;
  owner_id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: "ssh_key";
  public_ssh_key: string | null;
  private_key_fingerprint: string | null;
  status: ServerStatus;
  last_connection_check_at: string | null;
  last_connection_error: string | null;
  created_at: string;
  updated_at: string;
};

export type ServerPayload = {
  name: string;
  host: string;
  port: number;
  username: string;
  private_key?: string;
};

export type ServerConnectionTest = {
  success: boolean;
  status: ServerStatus;
  message: string;
};
