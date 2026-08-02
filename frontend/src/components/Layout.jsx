import { Link, useLocation, Outlet } from "react-router-dom";
import { Users, Clapperboard, ChevronLeft, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Characters", icon: Users },
  { to: "/studio", label: "Studio", icon: Clapperboard },
];

export default function Layout() {
  const { pathname } = useLocation();
  const onStudio = pathname.startsWith("/studio");

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-zinc-100 flex">
      {/* Sidebar */}
      <aside className="hidden md:flex w-60 flex-col border-r border-white/5 bg-[#0d0d0f] fixed inset-y-0">
        <div className="px-6 py-7">
          <div className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-rose-400 to-amber-300 flex items-center justify-center">
              <span className="text-[10px] font-bold text-black">TL</span>
            </div>
            <div className="leading-tight">
              <div className="text-[15px] font-semibold tracking-tight">Throughline</div>
              <div className="text-[10px] text-zinc-500 uppercase tracking-[0.18em]">Identity Studio</div>
            </div>
          </div>
        </div>
        <nav className="px-3 flex-1 space-y-0.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? pathname === "/" : onStudio;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors",
                  active ? "bg-white/[0.07] text-white" : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.03]"
                )}
              >
                <Icon className="h-4 w-4" strokeWidth={1.5} />
                {item.label}
              </Link>
            );
          })}

          {/* Studio section hint */}
          {onStudio && (
            <div className="px-3 pt-6 pb-2">
              <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-600">Studio workflow</div>
              <p className="mt-2 text-[11px] leading-relaxed text-zinc-600">
                Shoot, Bio, Calibrate &amp; Review live in the tab bar above the character.
              </p>
            </div>
          )}
        </nav>
        <div className="px-3 py-4 border-t border-white/5 space-y-0.5">
          <button className="w-full flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.03] transition-colors">
            <Settings className="h-4 w-4" strokeWidth={1.5} />
            Settings
          </button>
          <div className="flex items-center gap-2.5 px-3 pt-3">
            <div className="h-8 w-8 rounded-full bg-zinc-700 overflow-hidden flex items-center justify-center text-[11px] font-medium">
              D
            </div>
            <div className="leading-tight">
              <div className="text-[12px] font-medium">Director</div>
              <div className="text-[10px] text-zinc-500">studio mode</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-30 bg-[#0d0d0f] border-b border-white/5 px-4 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <ChevronLeft className="h-4 w-4 text-zinc-400" />
          <span className="text-[13px] font-semibold">Throughline</span>
        </Link>
        <div className="flex gap-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = item.to === "/" ? pathname === "/" : onStudio;
            return (
              <Link key={item.to} to={item.to} className={active ? "text-white" : "text-zinc-400"}>
                <Icon className="h-4 w-4" strokeWidth={1.5} />
              </Link>
            );
          })}
        </div>
      </div>

      {/* Main */}
      <main className="flex-1 md:ml-60 pt-14 md:pt-0">
        <Outlet />
      </main>
    </div>
  );
}