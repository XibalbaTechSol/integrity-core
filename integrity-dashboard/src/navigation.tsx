import {
  BookOpen,
  BrainCircuit,
  Code,
  FileCheck2,
  LayoutDashboard,
  ShieldCheck,
  Users,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type NavigationItem = {
  to: string;
  label: string;
  icon: LucideIcon;
};

export type NavigationGroup = {
  section: string;
  items: NavigationItem[];
};

/** Canonical authenticated-app navigation. Sidebar and header must render this model. */
export const NAVIGATION_GROUPS: NavigationGroup[] = [
  { section: 'Command', items: [{ to: '/dashboard', label: 'Overview', icon: LayoutDashboard }] },
  {
    section: 'Manage',
    items: [
      { to: '/agents', label: 'Agents & Identity', icon: Users },
      { to: '/security', label: 'Policy', icon: ShieldCheck },
      { to: '/knowledge', label: 'Evidence', icon: FileCheck2 },
      { to: '/fleet', label: 'Fleet', icon: ShieldCheck },
      { to: '/memory', label: 'Memory', icon: BrainCircuit },
    ],
  },
  {
    section: 'Build',
    items: [
      { to: '/developer', label: 'Developer', icon: Code },
      { to: '/wiki', label: 'Wiki', icon: BookOpen },
    ],
  },
];

export const NAVIGATION_ITEMS = NAVIGATION_GROUPS.flatMap((group) => group.items);
