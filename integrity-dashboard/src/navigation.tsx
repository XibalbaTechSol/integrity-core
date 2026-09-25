import {
  FileCheck2,
  Gauge,
  Settings2,
  UsersRound,
  WalletCards,
} from 'lucide-react';

export const NAVIGATION_ITEMS = [
  { to: '/dashboard', label: 'Command center', icon: Gauge, aliases: [] },
  { to: '/agents', label: 'Agent registry', icon: UsersRound, aliases: ['/identity', '/fleet', '/intelligence', '/knowledge', '/memory'] },
  { to: '/evidence', label: 'Evidence ledger', icon: FileCheck2, aliases: ['/records', '/proofs', '/contracts', '/activity', '/correlation'] },
  { to: '/treasury', label: 'Treasury', icon: WalletCards, aliases: ['/wallets', '/transactions', '/financials', '/prediction-markets', '/quant'] },
  { to: '/system', label: 'Operations', icon: Settings2, aliases: ['/health', '/kernel', '/kernel-intent', '/licence', '/developer', '/wiki', '/docs'] },
];
