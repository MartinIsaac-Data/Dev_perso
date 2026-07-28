import { useEffect, useState } from "react";

import { api } from "./api/client";
import { ErrorNote } from "./components/primitives";
import { useApi } from "./hooks/useApi";
import { CasesView } from "./views/CasesView";
import { Dashboard } from "./views/Dashboard";
import { DeliverablesView } from "./views/DeliverablesView";
import { EvidenceView } from "./views/EvidenceView";
import { QuotasView } from "./views/QuotasView";
import { SkillsView } from "./views/SkillsView";

const TABS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "skills", label: "Skill graph" },
  { key: "deliverables", label: "Deliverables" },
  { key: "cases", label: "Business cases" },
  { key: "quotas", label: "Quotas" },
  { key: "evidence", label: "Evidence" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function isTab(value: string): value is TabKey {
  return TABS.some((tab) => tab.key === value);
}

/**
 * Navigation is the URL hash, not a router library.
 *
 * Six views with no nested routes and no route parameters beyond a skill
 * code. React Router would be a dependency, a provider and a concept to carry
 * for something the platform already does — and the hash keeps deep links
 * working, which is the only feature actually needed here.
 */
export default function App() {
  const [tab, setTab] = useState<TabKey>(() => {
    const initial = window.location.hash.replace("#", "");
    return isTab(initial) ? initial : "dashboard";
  });
  const [profile, setProfile] = useState("demo");
  const [asOf, setAsOf] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);

  const profiles = useApi(() => api.profiles(), []);

  useEffect(() => {
    window.location.hash = tab;
  }, [tab]);

  useEffect(() => {
    const onHashChange = () => {
      const next = window.location.hash.replace("#", "");
      if (isTab(next)) setTab(next);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const scope = { profile, ...(asOf ? { asOf } : {}) };

  const openSkill = (code: string) => {
    setSelectedSkill(code);
    setTab("skills");
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <div>
            <h1 className="text-base font-semibold tracking-tight text-slate-900">
              Transformation OS
            </h1>
            <p className="text-[11px] text-slate-500">
              Skill graph · deliverables · business cases
            </p>
          </div>

          <nav className="flex flex-wrap gap-1">
            {TABS.map((entry) => (
              <button
                key={entry.key}
                onClick={() => setTab(entry.key)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                  tab === entry.key
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <select
              value={profile}
              onChange={(event) => setProfile(event.target.value)}
              className="rounded border border-slate-200 px-2 py-1 text-xs"
              title="Which profile to show"
            >
              {(profiles.data ?? [{ code: "demo", display_name: "demo", is_demo: true }]).map(
                (entry) => (
                  <option key={entry.code} value={entry.code}>
                    {entry.display_name}
                    {entry.is_demo ? " (demo)" : ""}
                  </option>
                ),
              )}
            </select>
            <label
              className="flex items-center gap-1 text-[11px] text-slate-500"
              title="Ask the system what it would have said on a past date"
            >
              as of
              <input
                type="date"
                value={asOf}
                onChange={(event) => setAsOf(event.target.value)}
                className="rounded border border-slate-200 px-1.5 py-1 text-xs"
              />
            </label>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-5">
        {profiles.error ? (
          <ErrorNote message={profiles.error} onRetry={profiles.reload} />
        ) : (
          <>
            {tab === "dashboard" && <Dashboard scope={scope} onOpenSkill={openSkill} />}
            {tab === "skills" && (
              <SkillsView
                scope={scope}
                selectedCode={selectedSkill}
                onSelect={setSelectedSkill}
              />
            )}
            {tab === "deliverables" && <DeliverablesView scope={scope} />}
            {tab === "cases" && <CasesView scope={scope} />}
            {tab === "quotas" && <QuotasView scope={scope} />}
            {tab === "evidence" && <EvidenceView scope={scope} />}
          </>
        )}
      </main>
    </div>
  );
}
