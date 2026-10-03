export type User = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  email_verified: boolean;
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
  // True when the account must confirm the emailed 6-digit code before it is
  // usable; `token` is then empty and the client collects the code.
  email_verification_required?: boolean;
};
