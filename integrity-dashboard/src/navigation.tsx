import {
  Activity,
  BookOpen,
  BrainCircuit,
  HeartPulse,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  WalletCards,
} from 'lucide-react';

export const NAVIGATION_ITEMS = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard, aliases: [] },
  { to: '/agents', label: 'Identity & agents', icon: BrainCircuit, aliases: ['/identity', '/fleet', '/intelligence', '/knowledge', '/memory'] },
  { to: '/evidence', label: 'Evidence & activity', icon: ShieldCheck, aliases: ['/records', '/proofs', '/contracts', '/activity', '/correlation'] },
  { to: '/treasury', label: 'Wallet & finance', icon: WalletCards, aliases: ['/wallets', '/transactions', '/financials', '/prediction-markets', '/quant'] },
  { to: '/security', label: 'Protection', icon: ShieldCheck, aliases: ['/shield'] },
  { to: '/health', label: 'Health', icon: HeartPulse, aliases: [] },
  { to: '/system', label: 'System', icon: Activity, aliases: ['/kernel', '/kernel-intent', '/licence', '/developer'] },
  { to: '/wiki', label: 'Docs & wiki', icon: BookOpen, aliases: ['/docs'] },
  { to: '/settings', label: 'Settings', icon: Settings, aliases: [] },
];
