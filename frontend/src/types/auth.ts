export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Token = {
  access_token: string;
  token_type: "bearer";
};

export type AuthResponse = {
  user: User;
  token: Token;
};
