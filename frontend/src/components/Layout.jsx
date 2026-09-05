import { Link, useLocation, Outlet } from "react-router-dom";
import { Users, Users2, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import ProviderBalance from "@/components/ProviderBalance";
import CharacterSwitcher from "@/components/CharacterSwitcher";

// THE SIDEBAR HOLDS ONLY WHAT IS GLOBAL.
//
// "Studio" used to sit here as a peer of Characters and Settings, which is a
// category error: the studio is not a place you go, it is what you get once you
// have opened a character. Clicking it with nobody active silently adopted
// whichever character the server last considered active.
//
// It also made the word "Studio" mean three different things at once — the app
// ("Identity Studio"), the per-character route, and the multi-character route
// ("Collaborator Studio"), two of which were listed side by side. `/collaborate`
// is now **Scenes**, which is what it actually does: compose one photograph with
// a cast. The /studio route still exists; it is just reached by opening someone.
const NAV = [
  // `match` is separate from `to` because being inside a character — /studio, or
  // /characters/new — is still "the Characters area". Without it those routes
  // light nothing at all, which is how the previous two versions of this
  // function broke.
  { to: "/", label: "Characters", icon: Users,
    match: ["/", "/characters", "/studio"] },
  { to: "/collaborate", label: "Scenes", icon: Users2, match: ["/collaborate"] },
  { to: "/settings", label: "Settings", icon: Settings, match: ["/settings"] },
];

// Prefix match per entry, with "/" kept exact — a bare startsWith("/") would
// light every item at once.
//
// The version before this was strict equality: correct for four flat routes, and
// dark the moment a nested one appears. (The version before THAT resolved every
// non-root link to `onStudio`, so /collaborate lit up "Studio". A nav that lies
// about where you are wastes real time.)
const isActive = (pathname, item) =>
  item.match.some((m) => (m === "/" ? pathname === "/" : pathname.startsWith(m)));

export default function Layout() {
  const { pathname } = useLocation();

  const navLinks = (cls) =>
    NAV.map((item) => {
      const Icon = item.icon;
      return (
        <Link key={item.to} to={item.to} className={cls(isActive(pathname, item))}>
          <Icon className="h-4 w-4" strokeWidth={1.5} />
          {item.label}
        </Link>
      );
    });

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-zinc-100 flex">
      {/* Sidebar */}
      <aside className="hidden md:flex w-60 flex-col border-r border-white/5 bg-[#0d0d0f] fixed inset-y-0">
        <div className="px-6 py-7">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-rose-400 to-amber-300 flex items-center justify-center">
              <span className="text-[10px] font-bold text-black">TL</span>
            </div>
            <div className="text-[15px] font-semibold tracking-tight">Throughline</div>
          </Link>
        </div>

        <nav className="px-3 flex-1 space-y-0.5">
          {navLinks((active) => cn(
            "flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] transition-colors",
            active ? "bg-white/[0.07] text-white"
                   : "text-zinc-400 hover:text-zinc-100 hover:bg-surface",
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-white/5 space-y-1">
          {/* The number that decides what the next shot costs, and WHO the next
              shot is of. The second slot used to hold a hardcoded "Director /
              studio mode" chip — not a real user, and not the question anyone
              was asking. */}
          <ProviderBalance />
          <CharacterSwitcher variant="sidebar" />
        </div>
      </aside>

      {/* Mobile top bar — labels included. Icons alone made three destinations
          a guessing game. */}
      <div className="md:hidden fixed top-0 inset-x-0 z-30 bg-[#0d0d0f] border-b border-white/5 px-3 py-2 flex items-center gap-2 overflow-x-auto no-scrollbar">
        <Link to="/" className="shrink-0 h-7 w-7 rounded-lg bg-gradient-to-br from-rose-400 to-amber-300 flex items-center justify-center">
          <span className="text-[10px] font-bold text-black">TL</span>
        </Link>
        {navLinks((active) => cn(
          "shrink-0 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] transition-colors",
          active ? "bg-white/[0.07] text-white" : "text-zinc-400",
        ))}
      </div>

      {/* Main */}
      {/* min-w-0: without it this flex child keeps its content's intrinsic
          width and the page scrolls sideways on narrow viewports. */}
      <main className="min-w-0 flex-1 md:ml-60 pt-12 md:pt-0">
        <Outlet />
      </main>
    </div>
  );
}
