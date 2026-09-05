import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Zap, AlertTriangle } from "lucide-react";
import { api } from "@/api/throughline";
import { cn } from "@/lib/utils";

// WHAT THE NEXT SHOT COSTS, and whether it can be paid for.
//
// The balance is the number that silently decides which provider actually runs:
// kie is $0.12 against fal's $0.30, but an empty kie account falls through to
// fal at full price without complaining. That is safe and it is not what anyone
// chose, so the number belongs where it is seen rather than on a settings page
// nobody opens.
//
// 24 credits per 4K edit, so "shots left" is the honest unit — a credit count on
// its own means nothing at a glance.
const SHOT_COST = 24;
const POLL_MS = 60000;      // server caches for 60s; this just keeps it fresh

export default function ProviderBalance() {
  const [d, setD] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.get("/api/providers")
      .then((x) => { if (alive) setD(x); })
      .catch(() => {});
    load();
    const t = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!d) return null;
  const active = (d.providers || []).find((p) => p.name === d.chain?.[0]);
  const credits = d.kie_credits;
  const usesKie = d.chain?.[0] === "kie";
  const shots = typeof credits === "number" ? Math.floor(credits / SHOT_COST) : null;
  // Only warn when the balance actually matters — if kie is not first in the
  // chain, its balance is not what the next shot is spending.
  const low = usesKie && typeof credits === "number" && credits < SHOT_COST;

  return (
    <Link to="/settings"
      title="Provider order and balance"
      className={cn("block rounded-lg px-3 py-2 transition-colors hover:bg-surface",
        low && "bg-amber-500/[0.07]")}>
      <div className="flex items-center gap-2">
        {low ? <AlertTriangle className="h-3.5 w-3.5 text-amber-400" strokeWidth={1.5} />
             : <Zap className="h-3.5 w-3.5 text-emerald-400" strokeWidth={1.5} />}
        <span className="text-[12px] text-zinc-300">{active?.label || "—"}</span>
        {active && (
          <span className="text-[11px] text-zinc-500 ml-auto tabular-nums">
            ${active.usd.toFixed(2)}/shot
          </span>
        )}
      </div>
      {typeof credits === "number" && (
        <div className={cn("mt-1 text-[10px] tabular-nums",
          low ? "text-amber-400" : "text-zinc-500")}>
          {low
            ? `${credits} credits — not enough, next shot falls through`
            : `${credits} credits · ~${shots} shot${shots === 1 ? "" : "s"} left`}
        </div>
      )}
    </Link>
  );
}
