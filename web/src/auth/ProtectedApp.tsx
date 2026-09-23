import { LoaderCircle } from "lucide-react";
import { Navigate, useLocation } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { useAuth } from "./AuthContext";
import type { ReactNode } from "react";

export function ProtectedApp({ children }: { children: ReactNode }) {
  const { loading, session } = useAuth();
  const location = useLocation();

  if (loading) return <div className="auth-loading"><LoaderCircle className="spin" size={30} /><span>正在打开家庭故事…</span></div>;
  if (!session) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!session.family && location.pathname !== "/family") return <Navigate to="/family" replace />;
  return <AppShell>{children}</AppShell>;
}
