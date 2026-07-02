import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { clearSession, getStoredToken, getStoredUser, login as apiLogin } from "./api";

interface AuthContextValue {
  token: string | null;
  username: string | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setToken(getStoredToken());
    setUsername(getStoredUser());
    setReady(true);
  }, []);

  const login = useCallback(async (user: string, password: string) => {
    const t = await apiLogin(user, password);
    setToken(t);
    setUsername(user);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setToken(null);
    setUsername(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, username, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
