import {
  BookOpen,
  BrainCircuit,
  Code,
  Landmark,
  LayoutDashboard,
  LockKeyhole,
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
      { to: '/treasury', label: 'Funds & Access', icon: Landmark },
      { to: '/security', label: 'Security & Policy', icon: ShieldCheck },
      { to: '/knowledge', label: 'Knowledge & Evidence', icon: BrainCircuit },
    ],
  },
  {
    section: 'Build',
    items: [
      { to: '/developer', label: 'Developer', icon: Code },
      { to: '/licence', label: 'Licensing', icon: LockKeyhole },
      { to: '/wiki', label: 'Wiki', icon: BookOpen },
    ],
  },
];

export const NAVIGATION_ITEMS = NAVIGATION_GROUPS.flatMap((group) => group.items);
