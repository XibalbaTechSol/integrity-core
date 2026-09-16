import {
  Activity,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  Code,
  Database,
  FileCheck2,
  FileKey2,
  Fingerprint,
  KeyRound,
  Landmark,
  LayoutDashboard,
  Network,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  WalletCards,
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
  { section: 'Finance', items: [
    { to: '/treasury', label: 'Treasury', icon: Landmark },
    { to: '/financials', label: 'Financials', icon: WalletCards },
  ] },
  { section: 'Intelligence', items: [
    { to: '/intelligence', label: 'Intelligence', icon: BrainCircuit },
    { to: '/correlation', label: 'Correlation', icon: Network },
    { to: '/prediction-markets', label: 'Prediction Markets', icon: BadgeCheck },
  ] },
  { section: 'Operations', items: [
    { to: '/health', label: 'Health', icon: ShieldCheck },
    { to: '/shield', label: 'Shield', icon: Shield },
    { to: '/quant', label: 'Quant', icon: Activity },
  ] },
  { section: 'System', items: [
    { to: '/knowledge', label: 'Knowledge', icon: Database },
    { to: '/licence', label: 'Licence', icon: FileKey2 },
    { to: '/kernel', label: 'Kernel', icon: ShieldCheck },
    { to: '/kernel-intent', label: 'Kernel Intent', icon: KeyRound },
    { to: '/developer', label: 'Developer', icon: Code },
    { to: '/wiki', label: 'Wiki', icon: BookOpen },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
];

export const NAVIGATION_ITEMS = NAVIGATION_GROUPS.flatMap((group) => group.items);
