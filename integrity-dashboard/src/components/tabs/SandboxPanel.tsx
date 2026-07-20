import React, { useState, useEffect } from 'react';
import { Server, Cpu, HardDrive, Play, Square, RefreshCw, ShieldCheck, Globe } from 'lucide-react';
import { Panel } from '../shared/Panel';

interface SandboxStatus {
  id: string;
  provider: string;
  status: 'running' | 'stopped' | 'error';
  cpu: number;
  ram: number;
  uptime: string;
}

export function SandboxPanel() {
  const [sandboxes, setSandboxes] = useState<SandboxStatus[]>([
    { id: 'sb-v7-alpha', provider: 'E2B', status: 'running', cpu: 12, ram: 450, uptime: '1h 22m' },
    { id: 'sb-v7-beta', provider: 'Modal', status: 'stopped', cpu: 0, ram: 0, uptime: '0m' },
  ]);

  const [selectedProvider, setSelectedProvider] = useState('E2B');

  const spawnSandbox = () => {
    const id = 'sb-' + Math.random().toString(36).substring(2, 7);
    setSandboxes(prev => [...prev, { 
      id, provider: selectedProvider, status: 'running', cpu: 5, ram: 128, uptime: '0m' 
    }]);
  };

  const killSandbox = (id: string) => {
    setSandboxes(prev => prev.map(s => s.id === id ? { ...s, status: 'stopped', cpu: 0, ram: 0 } : s));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <Panel title="Containerized Execution Environment" icon={<Server size={18} />}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <select 
              value={selectedProvider} 
              onChange={e => setSelectedProvider(e.target.value)}
              style={{ 
                background: 'var(--bg-secondary)', 
                color: 'white', 
                border: '1px solid var(--glass-border)', 
                padding: '4px 8px', 
                borderRadius: '4px',
                fontSize: '0.75rem'
              }}
            >
              <option value="E2B">E2B Sandbox</option>
              <option value="Modal">Modal Labs</option>
              <option value="Daytona">Daytona</option>
              <option value="Local">Local Docker</option>
            </select>
            <button 
              className="btn btn-primary" 
              onClick={spawnSandbox}
              style={{ padding: '4px 12px', fontSize: '0.7rem', height: '28px', display: 'flex', alignItems: 'center', gap: '4px' }}
            >
              <Play size={12} /> Spawn Sandbox
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.7rem', color: 'var(--success)' }}>
            <ShieldCheck size={14} /> TEE Verified
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {sandboxes.map(sb => (
            <div 
              key={sb.id} 
              style={{ 
                padding: '12px', 
                background: 'rgba(255,255,255,0.03)', 
                border: `1px solid ${sb.status === 'running' ? 'var(--primary)' : 'var(--glass-border)'}`, 
                borderRadius: 'var(--radius-md)',
                position: 'relative'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span className="mono" style={{ fontSize: '0.75rem', fontWeight: 700 }}>{sb.id}</span>
                <span style={{ 
                  fontSize: '0.6rem', 
                  padding: '2px 6px', 
                  borderRadius: '4px', 
                  background: sb.status === 'running' ? 'var(--success-dim)' : 'var(--bg-secondary)',
                  color: sb.status === 'running' ? 'var(--success)' : 'var(--text-muted)',
                  textTransform: 'uppercase'
                }}>
                  {sb.status}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Cpu size={12} /> CPU</div>
                  <span style={{ color: 'white' }}>{sb.cpu}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><HardDrive size={12} /> RAM</div>
                  <span style={{ color: 'white' }}>{sb.ram} MB</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Globe size={12} /> Provider</div>
                  <span style={{ color: 'white' }}>{sb.provider}</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button 
                  className="btn btn-ghost" 
                  onClick={() => killSandbox(sb.id)}
                  style={{ flex: 1, fontSize: '0.65rem', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}
                >
                  <Square size={10} /> Stop
                </button>
                <button 
                  className="btn btn-ghost" 
                  style={{ flex: 1, fontSize: '0.65rem', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}
                >
                  <RefreshCw size={10} /> Reset
                </button>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
