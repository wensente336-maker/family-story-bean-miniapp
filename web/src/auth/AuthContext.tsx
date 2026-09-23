import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getSession, type AuthData, type Family, type SessionData } from "../services/authApi";
import { clearAccessToken, getAccessToken, saveAccessToken } from "../services/authStore";

type AuthState = {
  loading: boolean;
  session: SessionData | null;
  completeLogin: (auth: AuthData) => void;
  updateFamily: (family: Family) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<SessionData | null>(null);

  useEffect(() => {
    let active = true;
    if (!getAccessToken()) {
      setLoading(false);
      return () => { active = false; };
    }
    getSession()
      .then((restored) => { if (active) setSession(restored); })
      .catch(() => {
        if (active) {
          clearAccessToken();
          setSession(null);
        }
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const value = useMemo<AuthState>(() => ({
    loading,
    session,
    completeLogin(auth) {
      saveAccessToken(auth.access_token);
      setSession({ user_id: auth.user_id, family: auth.family });
    },
    updateFamily(family) {
      setSession((current) => current ? { ...current, family } : current);
    },
    logout() {
      clearAccessToken();
      setSession(null);
    }
  }), [loading, session]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
