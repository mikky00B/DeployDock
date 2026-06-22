import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getCurrentUser, login, logout, register, type LoginPayload, type RegisterPayload } from "../api/auth";
import type { User } from "../types/auth";

const TOKEN_STORAGE_KEY = "deploydock.access_token";

type AuthContextValue = {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  authError: string | null;
  signIn: (payload: LoginPayload) => Promise<void>;
  signUp: (payload: RegisterPayload) => Promise<void>;
  signOut: () => Promise<void>;
  clearAuthError: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(token));
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadUser(savedToken: string) {
      setIsLoading(true);
      try {
        const currentUser = await getCurrentUser(savedToken);
        if (isActive) {
          setUser(currentUser);
          setAuthError(null);
        }
      } catch {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        if (isActive) {
          setToken(null);
          setUser(null);
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    if (token) {
      void loadUser(token);
    } else {
      setIsLoading(false);
    }

    return () => {
      isActive = false;
    };
  }, [token]);

  const storeSession = useCallback((nextToken: string, nextUser: User) => {
    localStorage.setItem(TOKEN_STORAGE_KEY, nextToken);
    setToken(nextToken);
    setUser(nextUser);
    setAuthError(null);
  }, []);

  const signIn = useCallback(
    async (payload: LoginPayload) => {
      try {
        const response = await login(payload);
        storeSession(response.token.access_token, response.user);
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : "Could not sign in");
        throw error;
      }
    },
    [storeSession],
  );

  const signUp = useCallback(
    async (payload: RegisterPayload) => {
      try {
        const response = await register(payload);
        storeSession(response.token.access_token, response.user);
      } catch (error) {
        setAuthError(error instanceof Error ? error.message : "Could not create account");
        throw error;
      }
    },
    [storeSession],
  );

  const signOut = useCallback(async () => {
    await logout(token).catch(() => undefined);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setAuthError(null);
  }, [token]);

  const value = useMemo(
    () => ({
      user,
      token,
      isLoading,
      authError,
      signIn,
      signUp,
      signOut,
      clearAuthError: () => setAuthError(null),
    }),
    [authError, isLoading, signIn, signOut, signUp, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
