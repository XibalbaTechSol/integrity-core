import { useState } from 'react';
import { motion } from 'framer-motion';
import { useDashboard } from '../../context/useDashboard';
import { Shield, Key, Database, Anchor, Activity, FileText, User, HelpCircle, ArrowRight } from 'lucide-react';

interface Node {
  id: string;
  label: string;
  icon: React.ReactNode;
  description: string;
  x: number; // percentage width
  y: number; // percentage height
  color: string;
}

const NODES: Node[] = [
  { id: 'sovereign_agent', label: 'SovereignAgent', icon: <Key size={18} />, description: 'On-chain identity smart account / controller.', x: 15, y: 50, color: 'var(--primary)' },
  { id: 'state_anchor', label: 'StateAnchor', icon: <Anchor size={18} />, description: 'Cryptographic commit anchoring ledger.', x: 45, y: 20, color: '#3b82f6' },
  { id: 'reputation_registry', label: 'ReputationRegistry', icon: <Activity size={18} />, description: 'Composite reputation (AIS) & tiers repository.', x: 75, y: 50, color: 'var(--gold)' },
  { id: 'slasher', label: 'Slasher', icon: <Shield size={18} />, description: 'Enforces collateral slashing on policy deviations.', x: 45, y: 80, color: 'var(--danger)' },
  { id: 'verifier_registry', label: 'VerifierRegistry', icon: <Database size={18} />, description: 'UltraPlonk ZK verifying logic gate.', x: 75, y: 20, color: 'var(--success)' },
  { id: 'compliance_gate', label: 'ComplianceGate', icon: <Shield size={18} />, description: 'Pre-execution intent validation module.', x: 15, y: 20, color: '#a855f7' },
  { id: 'agent_profile', label: 'AgentProfile', icon: <User size={18} />, description: 'Stores agent metadata & W3C DID document.', x: 45, y: 50, color: '#06b6d4' }
];

const CONNECTIONS = [
  { from: 'sovereign_agent', to: 'state_anchor', label: 'updates root' },
  { from: 'sovereign_agent', to: 'agent_profile', label: 'manages metadata' },
  { from: 'sovereign_agent', to: 'reputation_registry', label: 'registers DID' },
  { from: 'compliance_gate', to: 'sovereign_agent', label: 'gates execution' },
  { from: 'compliance_gate', to: 'reputation_registry', label: 'queries tier/AIS' },
  { from: 'verifier_registry', to: 'reputation_registry', label: 'reports zk-proof status' },
  { from: 'slasher', to: 'reputation_registry', label: 'updates stake deficit' },
  { from: 'sovereign_agent', to: 'slasher', label: 'deposits collateral' }
];

export function VisualTopologyMap() {
  const { selectedAgent, setActiveTab } = useDashboard() as any;
  const [selectedNode, setSelectedNode] = useState<Node | null>(NODES[0]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Maps node id to actual primitives address from current context if available
  const getAddress = (id: string) => {
    if (!selectedAgent?.primitives) return '0x0000000000000000000000000000000000000000';
    const mapping: Record<string, string> = {
      sovereign_agent: selectedAgent.primitives.sovereign_agent,
      state_anchor: selectedAgent.primitives.state_anchor,
      reputation_registry: selectedAgent.primitives.reputation_registry,
      slasher: selectedAgent.primitives.slasher,
      verifier_registry: selectedAgent.primitives.verifier_registry,
      compliance_gate: selectedAgent.primitives.compliance_gate,
      agent_profile: selectedAgent.primitives.agent_profile
    };
    return mapping[id] || '0x0000000000000000000000000000000000000000';
  };

  const getContractAction = (node: Node) => {
    switch (node.id) {
      case 'state_anchor':
        return { label: 'Anchor Memory State', action: () => setActiveTab('ledger') };
      case 'reputation_registry':
        return { label: 'Inspect Reputation Details', action: () => setActiveTab('oracle') };
      case 'verifier_registry':
        return { label: 'Submit ZK Attestation', action: () => setActiveTab('zk') };
      case 'compliance_gate':
        return { label: 'Inspect Compliance Log', action: () => setActiveTab('health') };
      default:
        return null;
    }
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--space-6)', height: '560px' }}>
      
      {/* ── Topological Interactive Canvas ── */}
      <div style={{
        position: 'relative',
        background: 'rgba(11, 13, 25, 0.4)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        boxShadow: 'inset 0 0 40px rgba(0, 0, 0, 0.6)'
      }}>
        
        {/* Background Grid Pattern */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundImage: 'radial-gradient(var(--glass-border) 1px, transparent 0)',
          backgroundSize: '24px 24px',
          opacity: 0.4,
          pointerEvents: 'none'
        }} />

        {/* Connections Layer (SVG) */}
        <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          <defs>
            <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.4" />
              <stop offset="100%" stopColor="var(--gold)" stopOpacity="0.4" />
            </linearGradient>
            <linearGradient id="lineGradActive" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity="1" />
              <stop offset="100%" stopColor="var(--gold)" stopOpacity="1" />
            </linearGradient>
          </defs>
          
          {CONNECTIONS.map((conn, idx) => {
            const fromNode = NODES.find(n => n.id === conn.from);
            const toNode = NODES.find(n => n.id === conn.to);
            if (!fromNode || !toNode) return null;

            const isRelated = hoveredNode === conn.from || hoveredNode === conn.to ||
                              (selectedNode && (selectedNode.id === conn.from || selectedNode.id === conn.to));

            // Custom curved path (cubic bezier)
            const x1 = `${fromNode.x}%`;
            const y1 = `${fromNode.y}%`;
            const x2 = `${toNode.x}%`;
            const y2 = `${toNode.y}%`;

            // For path calculation we just use simple lines since CSS coordinates are percentages
            // (SVPs handle percentages fine if mapped nicely, or we can use linear coordinates)
            return (
              <g key={idx}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={isRelated ? 'url(#lineGradActive)' : 'url(#lineGrad)'}
                  strokeWidth={isRelated ? 2 : 1}
                  strokeDasharray={isRelated ? '4 2' : undefined}
                  style={{ transition: 'all 0.3s ease' }}
                />
              </g>
            );
          })}
        </svg>

        {/* Nodes Layer */}
        {NODES.map(node => {
          const isSelected = selectedNode?.id === node.id;
          const isHovered = hoveredNode === node.id;
          
          return (
            <motion.div
              key={node.id}
              onClick={() => setSelectedNode(node)}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{
                position: 'absolute',
                left: `${node.x}%`,
                top: `${node.y}%`,
                transform: 'translate(-50%, -50%)',
                cursor: 'pointer',
                zIndex: 10
              }}
            >
              <motion.div
                animate={{
                  scale: isSelected ? 1.08 : isHovered ? 1.04 : 1,
                  boxShadow: isSelected 
                    ? `0 0 20px ${node.color}40` 
                    : isHovered 
                      ? `0 0 12px ${node.color}25` 
                      : '0 4px 12px rgba(0,0,0,0.4)'
                }}
                style={{
                  background: isSelected ? 'var(--bg-secondary)' : 'var(--bg-card)',
                  border: `1px solid ${isSelected ? node.color : 'var(--glass-border)'}`,
                  borderRadius: 'var(--radius-md)',
                  padding: '10px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  color: 'var(--text-primary)',
                  transition: 'background 0.2s, border-color 0.2s',
                  userSelect: 'none'
                }}
              >
                <div style={{
                  color: node.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}>
                  {node.icon}
                </div>
                <div>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{node.label}</div>
                  <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                    {getAddress(node.id).substring(0, 10)}...
                  </div>
                </div>
              </motion.div>
            </motion.div>
          );
        })}
      </div>

      {/* ── Side Node Inspector Panel ── */}
      <div style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-5)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)'
      }}>
        {selectedNode ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--primary-dim)',
                border: `1px solid ${selectedNode.color}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: selectedNode.color
              }}>
                {selectedNode.icon}
              </div>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>{selectedNode.label}</h3>
                <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Contract Primitive
                </span>
              </div>
            </div>

            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5, margin: 0 }}>
              {selectedNode.description}
            </div>

            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: 'var(--space-4)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '6px' }}>Deployed Contract Address</div>
              <div style={{
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                background: 'var(--bg-secondary)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--glass-border)',
                wordBreak: 'break-all',
                color: 'var(--text-primary)'
              }}>
                {getAddress(selectedNode.id)}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: 'auto' }}>
              {getContractAction(selectedNode) && (
                <button
                  onClick={getContractAction(selectedNode)?.action}
                  style={{
                    width: '100%',
                    padding: '10px',
                    background: 'var(--primary)',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px'
                  }}
                >
                  {getContractAction(selectedNode)?.label} <ArrowRight size={12} />
                </button>
              )}
            </div>
          </>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', textAlign: 'center', gap: '10px' }}>
            <HelpCircle size={32} />
            <span style={{ fontSize: '0.8rem' }}>Click any node on the graph to inspect its details and execute primitives transactions.</span>
          </div>
        )}
      </div>
    </div>
  );
}
