import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Target,
  Gauge,
  Briefcase,
  Rocket,
  Sparkles,
  Award,
  GraduationCap,
  Users,
  Globe2,
  FileCheck2,
  Wallet,
  Map,
  ListChecks,
  Archive,
  Bot,
  Settings,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

export const navItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "MBA Targets", href: "/mba-targets", icon: Target },
  { label: "MBA Readiness", href: "/mba-readiness", icon: Gauge },
  { label: "Career", href: "/career", icon: Briefcase },
  { label: "Projects & Impact", href: "/projects", icon: Rocket },
  { label: "Skills", href: "/skills", icon: Sparkles },
  { label: "Certifications", href: "/certifications", icon: Award },
  { label: "Education", href: "/education", icon: GraduationCap },
  { label: "Leadership", href: "/leadership", icon: Users },
  { label: "International Exposure", href: "/international", icon: Globe2 },
  { label: "MBA Application", href: "/mba-application", icon: FileCheck2 },
  { label: "Financial Plan", href: "/financial-plan", icon: Wallet },
  { label: "Roadmap", href: "/roadmap", icon: Map },
  { label: "Tasks", href: "/tasks", icon: ListChecks },
  { label: "Evidence Bank", href: "/evidence", icon: Archive },
  { label: "AI Career Advisor", href: "/ai-advisor", icon: Bot },
  { label: "Settings", href: "/settings", icon: Settings },
];
