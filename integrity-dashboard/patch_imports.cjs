const fs = require('fs');
let content = fs.readFileSync('src/pages/ShieldPage.tsx', 'utf8');

// Replace next/link
content = content.replace(/import Link from 'next\/link';/g, "import { Link } from 'react-router-dom';");

// Remove 'use client'
content = content.replace(/'use client';/g, '');

// Mock PasskeyConnectButton
content = content.replace(/import \{ PasskeyConnectButton \} from '@\/components\/PasskeyConnectButton';/g, "const PasskeyConnectButton = () => <button className=\"px-4 py-2 bg-slate-800 text-white rounded\">Connect Wallet</button>;");

// Mock io
content = content.replace(/import \{ io, Socket \} from 'socket\.io-client';/g, "const io = () => ({ on: () => {}, off: () => {}, disconnect: () => {} }); type Socket = any;");

// Mock EHRGateABI
content = content.replace(/import EHRGateABI from '\.\.\/\.\.\/lib\/web3\/EHRGateABI\.json';/g, "const EHRGateABI = [];");

// Mock IntegrityClient
content = content.replace(/import \{ IntegrityClient \} from '\.\.\/\.\.\/lib\/integrity-sdk';/g, "class IntegrityClient { constructor() {} async init() {} async getMetrics() { return []; } }");

// Mock wagmi
content = content.replace(/import \{ useWalletClient \} from 'wagmi';/g, "const useWalletClient = () => ({ data: null });");

// Mock ethers
content = content.replace(/import \{ ethers \} from 'ethers';/g, "const ethers = { BrowserProvider: class { constructor() {} async getSigner() { return { getAddress: () => '0xMockAddress' }; } }, Contract: class { constructor() {} } };");

// Any other missing components?
// The default export in NextJS is Dashboard(). We should rename it to ShieldPage.
content = content.replace(/export default function Dashboard\(\) \{/g, "export default function ShieldPage() {");

fs.writeFileSync('src/pages/ShieldPage.tsx', content);
