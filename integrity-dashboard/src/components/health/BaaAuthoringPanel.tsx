import { useState } from 'react';
import { ethers } from 'ethers';
import { FileText, Stethoscope, ShieldCheck, ArrowRight, Loader2 } from 'lucide-react';
import { Panel } from '../shared/Panel';
import { oracle } from '../../services/oracle';
import { SMART_BAA_FACTORY_ADDRESS, COVERED_ENTITY_REGISTRY_ADDRESS } from '../../constants';
import { SMART_BAA_FACTORY_ABI, COVERED_ENTITY_REGISTRY_ABI, ENTITY_TYPE_COVERED_ENTITY } from '../../chain/shield';

interface BaaAuthoringPanelProps {
  walletAddress: string | null;
  selectedAgent: { alias?: string; eth_address: string } | null;
  addToast: (kind: 'success' | 'error' | 'info', msg: string) => void;
  onDeployed: () => void;
}

function StepLabel({ n, label }: { n: number; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: 'var(--space-2)' }}>
      <div style={{
        width: '20px', height: '20px', borderRadius: '50%', background: 'var(--theme-accent-muted)',
        color: 'var(--theme-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.7rem', fontWeight: 800, flexShrink: 0,
      }}>
        {n}
      </div>
      <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>{label}</span>
    </div>
  );
}

// A real, guided authoring flow for a HIPAA Business Associate Agreement, backed entirely by
// SmartBAAFactory.createBAA (contracts/src/health/SmartBAAFactory.sol) -- this doesn't invent
// a new contract or a draft/preview-only step; every field here is a real constructor argument,
// and clicking Deploy fires the same on-chain call HealthPage's old modal did. The only new
// thing is presenting it as an ordered clinical-intake-style form instead of a popup, per the
// "programmatically write BAA agreements as smart contracts to be deployed" reimagining --
// so a covered entity can see the whole agreement taking shape (parties, document commitment,
// collateral terms) before the one transaction that deploys it.
export function BaaAuthoringPanel({ walletAddress, selectedAgent, addToast, onDeployed }: BaaAuthoringPanelProps) {
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [agreementHash, setAgreementHash] = useState<string | null>(null);
  const [hashing, setHashing] = useState(false);
  const [stake, setStake] = useState('5000');
  const [busy, setBusy] = useState(false);

  const handleFile = async (file: File | null) => {
    setPdfFile(file);
    setAgreementHash(null);
    if (!file) return;
    setHashing(true);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      setAgreementHash(ethers.keccak256(bytes));
    } finally {
      setHashing(false);
    }
  };

  const getSigner = async () => new ethers.BrowserProvider((window as any).ethereum).getSigner();

  const handleDeploy = async () => {
    if (!selectedAgent) { addToast('error', 'Select an agent first.'); return; }
    if (!walletAddress) { addToast('error', 'Connect the covered-entity wallet first.'); return; }
    if (!pdfFile || !agreementHash) { addToast('error', 'Attach the BAA document.'); return; }

    setBusy(true);
    try {
      const businessAssociate = await oracle.resolveSovereignAgent(selectedAgent.eth_address);
      const signer = await getSigner();

      const registry = new ethers.Contract(COVERED_ENTITY_REGISTRY_ADDRESS, COVERED_ENTITY_REGISTRY_ABI, signer);
      const isActive: boolean = await registry.isActiveCoveredEntity(walletAddress);
      if (!isActive) {
        const registrarRole: string = await registry.REGISTRAR_ROLE();
        const canRegister: boolean = await registry.hasRole(registrarRole, walletAddress);
        if (!canRegister) {
          throw new Error('Your wallet is not a registered Covered Entity. Registration requires the protocol registrar (REGISTRAR_ROLE).');
        }
        addToast('info', 'Registering your wallet as a Covered Entity…');
        await (await registry.registerEntity(walletAddress, ENTITY_TYPE_COVERED_ENTITY, 'ipfs://covered-entity')).wait();
      }

      const requiredCollateral = ethers.parseEther(stake || '0');
      const factory = new ethers.Contract(SMART_BAA_FACTORY_ADDRESS, SMART_BAA_FACTORY_ABI, signer);
      addToast('info', 'Deploying the SmartBAA on-chain…');
      await (await factory.createBAA(businessAssociate, agreementHash, requiredCollateral)).wait();

      addToast('success', 'Smart BAA deployed. The agent must sign to activate it.');
      setPdfFile(null);
      setAgreementHash(null);
      onDeployed();
    } catch (err: any) {
      addToast('error', `Failed to deploy BAA: ${err.shortMessage || err.reason || err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const canDeploy = !!walletAddress && !!pdfFile && !!agreementHash && !busy;

  return (
    <Panel title="Draft a Business Associate Agreement" icon={<Stethoscope size={18} color="var(--theme-accent)" />}>
      <p className="text-muted" style={{ fontSize: '0.85rem', marginBottom: 'var(--space-6)' }}>
        Every field below is a real constructor argument to <code>SmartBAAFactory.createBAA</code> -- this writes and
        deploys an actual on-chain agreement (Base Sepolia), not a draft or preview.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 'var(--space-6)' }}>
        <div>
          <StepLabel n={1} label="Parties" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.8rem' }}>
            <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: '2px' }}>COVERED ENTITY (your connected wallet)</div>
              {walletAddress ? <code style={{ fontSize: '0.75rem' }}>{walletAddress}</code> : <span style={{ color: 'var(--danger)' }}>Connect a wallet first.</span>}
            </div>
            <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)' }}>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginBottom: '2px' }}>BUSINESS ASSOCIATE</div>
              <span>{selectedAgent?.alias || selectedAgent?.eth_address || 'No agent selected'}</span>
            </div>
          </div>
        </div>

        <div>
          <StepLabel n={2} label="Agreement document" />
          <div style={{ position: 'relative', marginBottom: '8px' }}>
            <input
              type="file"
              accept=".pdf"
              style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }}
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
            <div className="input flex items-center gap-2" style={{ background: 'var(--bg-secondary)', borderStyle: 'dashed', fontSize: '0.8rem' }}>
              <FileText size={16} /> {pdfFile ? pdfFile.name : 'Upload BAA document (PDF)...'}
            </div>
          </div>
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', minHeight: '32px' }}>
            {hashing ? 'Hashing locally…' : agreementHash ? (
              <>Content commitment (keccak256, computed locally -- the file itself is never uploaded): <code style={{ wordBreak: 'break-all' }}>{agreementHash}</code></>
            ) : 'The document is hashed in your browser; only the hash is written on-chain.'}
          </div>
        </div>

        <div>
          <StepLabel n={3} label="Collateral terms" />
          <label className="form-label" style={{ fontSize: '0.75rem' }}>Staked ITK collateral required from the agent</label>
          <input
            type="number" className="input" value={stake}
            onChange={(e) => setStake(e.target.value)}
            style={{ fontSize: '0.85rem' }}
          />
          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Slashed only by the protocol arbitrator, on a raised dispute.
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-6)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--glass-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.7rem', color: canDeploy ? '#10b981' : 'var(--text-muted)' }}>
          <ShieldCheck size={14} /> {canDeploy ? 'Ready to deploy' : 'Complete the fields above'}
        </div>
        <button className="btn btn-primary" disabled={!canDeploy} onClick={handleDeploy} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {busy ? 'Deploying…' : 'Write & Deploy SmartBAA'}
        </button>
      </div>
    </Panel>
  );
}
