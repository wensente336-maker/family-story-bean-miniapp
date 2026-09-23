import { BookHeart, Disc3, House, Mail, Settings, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "首页", icon: House },
  { to: "/podcasts", label: "家庭留声机", icon: Disc3 },
  { to: "/postcards", label: "声音明信片", icon: Mail },
  { to: "/family", label: "家人", icon: UsersRound }
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="side-rail" aria-label="主要导航">
        <NavLink className="brand-lockup" to="/" aria-label="家庭故事豆首页">
          <span className="brand-bean" aria-hidden="true"><span /></span>
          <span>家庭故事豆</span>
        </NavLink>
        <nav className="desktop-nav">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
              <Icon size={20} strokeWidth={2.2} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="rail-spacer" />
        <NavLink className="nav-item" to="/settings/privacy"><Settings size={20} /><span>隐私设置</span></NavLink>
        <div className="privacy-note"><BookHeart size={18} /><span>家庭内容默认私密</span></div>
      </aside>

      <main className="main-surface">{children}</main>

      <nav className="mobile-nav" aria-label="主要导航">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => isActive ? "mobile-nav-item active" : "mobile-nav-item"}>
            <Icon size={22} strokeWidth={2.1} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
