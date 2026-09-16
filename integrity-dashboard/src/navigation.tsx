import { Activity, FileCheck2, FileKey2, Fingerprint, KeyRound, LayoutDashboard, ScrollText, ShieldCheck, WalletCards } from 'lucide-react';
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
  { section: 'Protocol', items: [
    { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
    { to: '/identity', label: 'Agent Identity', icon: Fingerprint },
    { to: '/records', label: 'Integrity Records', icon: ScrollText },
    { to: '/proofs', label: 'Proofs & Verification', icon: FileCheck2 },
    { to: '/wallets', label: 'Wallet', icon: WalletCards },
    { to: '/transactions', label: 'Transactions', icon: Activity },
    { to: '/contracts', label: 'Contracts', icon: FileKey2 },
    { to: '/security', label: 'Security & Keys', icon: KeyRound },
    { to: '/activity', label: 'Activity Log', icon: ShieldCheck },
  ] },
];

export const NAVIGATION_ITEMS = NAVIGATION_GROUPS.flatMap((group) => group.items);
