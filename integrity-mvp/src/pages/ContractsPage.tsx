import { useState, useEffect, useRef } from 'react';
import { Terminal, Save, Folder, File, Cpu, ShieldCheck, Code, ChevronRight, ChevronDown, Plus, Trash2, X, Play } from 'lucide-react';
import Editor from '@monaco-editor/react';
import { TopBar } from '../components/TopBar';
import { oracle } from '../services/oracle';
import type { AgentSummary } from '../services/oracle';
import { REAL_FILES } from '../services/contractFiles';
import { SeededDataBadge } from '../shared/SeededDataBadge';

const registerSolidityLanguage = (monaco: any) => {
  if (monaco.languages.getLanguages().some((lang: any) => lang.id === 'solidity')) {
    return;
  }

  monaco.languages.register({ id: 'solidity' });

  monaco.languages.setMonarchTokensProvider('solidity', {
    keywords: [
      'contract', 'library', 'interface', 'is', 'struct', 'mapping', 'address',
      'string', 'bool', 'uint', 'int', 'uint256', 'int256', 'bytes', 'bytes32',
      'function', 'returns', 'public', 'external', 'private', 'internal',
      'view', 'pure', 'payable', 'constant', 'anonymous', 'indexed',
      'returns', 'return', 'revert', 'require', 'assert', 'event', 'emit',
      'modifier', 'constructor', 'fallback', 'receive', 'error',
      'pragma', 'solidity', 'import', 'using', 'for', 'global',
      'assembly', 'let', 'if', 'else', 'for', 'while', 'do', 'break', 'continue',
      'new', 'delete', 'type', 'super', 'this', 'virtual', 'override',
      'storage', 'memory', 'calldata', 'msg', 'tx', 'block', 'abi'
    ],

    operators: [
      '=', '>', '<', '!', '~', '?', ':',
      '==', '<=', '>=', '!=', '&&', '||', '++', '--',
      '+', '-', '*', '/', '&', '|', '^', '%', '<<', '>>', '>>>',
      '+=', '-=', '*=', '/=', '&=', '|=', '^=', '%=', '<<=', '>>=', '>>>='
    ],

    symbols: /[=><!~?:&|+\-*\/\^%]+/,
    escapes: /\\(?:[abfnrtv\\"']|x[0-9A-Fa-f]{1,4}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})/,

    tokenizer: {
      root: [
        // identifiers and keywords
        [/[a-zA-Z_$][\w$]*/, {
          cases: {
            '@keywords': 'keyword',
            '@default': 'identifier'
          }
        }],

        // whitespace
        { include: '@whitespace' },

        // delimiters and operators
        [/[{}()\[\]]/, '@brackets'],
        [/[<>](?!@symbols)/, '@brackets'],
        [/@symbols/, {
          cases: {
            '@operators': 'operator',
            '@default': ''
          }
        }],

        // numbers
        [/\d*\.\d+(?:[eE][\-+]?\d+)?/, 'number.float'],
        [/0[xX][0-9a-fA-F]+/, 'number.hex'],
        [/\d+/, 'number'],

        // delimiter: after number because of .\d floats
        [/[;,.]/, 'delimiter'],

        // strings
        [/"([^"\\]|\\.)*$/, 'string.invalid'],  // non-templated string
        [/"/, 'string', '@string'],

        // characters
        [/'[^\\']'/, 'string'],
        [/(')(@escapes)(')/, ['string', 'string.escape', 'string']],
        [/'/, 'string.invalid']
      ],

      whitespace: [
        [/[ \t\r\n]+/, 'white'],
        [/\/\*/, 'comment', '@comment'],
        [/\/\/.*$/, 'comment'],
      ],

      comment: [
        [/[^\/*]+/, 'comment'],
        [/\/\*/, 'comment', '@push'],    // nested comment
        ["\\*/", 'comment', '@pop'],
        [/[\/*]/, 'comment']
      ],

      string: [
        [/[^\\"]+/, 'string'],
        [/@escapes/, 'string.escape'],
        [/\\./, 'string.escape.invalid'],
        [/"/, 'string', '@pop']
      ],
    },
  });
};

export const ContractsPage = () => {
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [activeContract, setActiveContract] = useState<{ id: string, name: string } | null>(null);
  const [activeAgent, setActiveAgent] = useState<{ id: string, name: string } | null>(null);
  
  const [localFiles, setLocalFiles] = useState(REAL_FILES);
  const [isContractsOpen, setIsContractsOpen] = useState(true);
  const [isAgentsOpen, setIsAgentsOpen] = useState(true);
  
  const [agentPrimitives, setAgentPrimitives] = useState<any | null>(null);
  const [agentAis, setAgentAis] = useState<any | null>(null);
  const [isLoadingAgent, setIsLoadingAgent] = useState(false);

  const [deploymentMode, setDeploymentMode] = useState<'sovereign' | 'centralized'>('sovereign');
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [deployedContracts, setDeployedContracts] = useState<{name: string, address: string}[]>([]);
  const [rightPanelTab, setRightPanelTab] = useState<'agent' | 'deployed'>('agent');

  const [logs, setLogs] = useState<string[]>([
    '[system] Legacy IDE Interface loaded.',
    '[system] Connected to Xibalba Agent Registry.'
  ]);
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    oracle.listAgents().then(a => setAgents(a)).catch(err => appendLog(`[error] Failed to fetch agents: ${err.message}`));
    
    // Default to the first contract if available
    if (REAL_FILES.length > 0) {
      setActiveContract({ id: REAL_FILES[0].name, name: REAL_FILES[0].name });
      setOpenTabs([REAL_FILES[0].name]);
    }
  }, []);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  const appendLog = (msg: string) => {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  };

  const handleSelectAgent = async (id: string) => {
    setActiveAgent({ id, name: `Agent ${id.substring(0, 8)}...` });
    setIsLoadingAgent(true);
    setAgentPrimitives(null);
    setAgentAis(null);
    appendLog(`[system] Querying primitive statuses for agent ${id}...`);
    try {
      const agentData = await oracle.getAgent(id);
      setAgentPrimitives(agentData.primitives);
      appendLog(`[success] Resolved 7 primitives for agent ${id} (${agentData.primitives_source})`);
      
      const aisData = await oracle.getAis(id);
      setAgentAis(aisData);
      appendLog(`[success] Fetched AIS scoring for agent ${id}`);
    } catch (err: any) {
      appendLog(`[error] Failed to query agent details: ${err.message}`);
    } finally {
      setIsLoadingAgent(false);
    }
  };

  const handleSelectContract = (name: string) => {
    setActiveContract({ id: name, name });
    if (!openTabs.includes(name)) {
      setOpenTabs([...openTabs, name]);
    }
    appendLog(`[system] Opened contract ${name}`);
  };

  const handleCloseTab = (name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newTabs = openTabs.filter(t => t !== name);
    setOpenTabs(newTabs);
    if (activeContract?.id === name) {
      if (newTabs.length > 0) {
        setActiveContract({ id: newTabs[newTabs.length - 1], name: newTabs[newTabs.length - 1] });
      } else {
        setActiveContract(null);
      }
    }
  };

  const handleBuild = () => {
    if (!activeContract) return;
    appendLog(`[build] Compiling ${activeContract.name}...`);
    setTimeout(() => appendLog(`[build] Parsing AST for ${activeContract.name}...`), 600);
    setTimeout(() => appendLog(`[build] Generating bytecode and ABI...`), 1200);
    setTimeout(() => appendLog(`[success] Compilation successful!`), 1800);
  };

  const handleDeploy = () => {
    if (!activeContract) return;
    
    appendLog(`[deploy] Initiating deployment for ${activeContract.name}...`);
    
    if (deploymentMode === 'sovereign') {
      if (!activeAgent) {
        appendLog(`[error] Sovereign deployment requires a connected agent. Please select an agent from the workspace first.`);
        return;
      }
      appendLog(`[deploy] Deploying ${activeContract.name} in SOVEREIGN mode (Ownership will be assigned to agent ${activeAgent.id.substring(0, 8)}...)`);
      setTimeout(() => appendLog(`[system] Constructing deployment payload...`), 400);
      setTimeout(() => appendLog(`[system] Routing deployment call through SovereignAgent.execute() at ${agentPrimitives?.sovereign_agent || '0x...'}`), 800);
      setTimeout(() => appendLog(`[system] Generating EIP-1167 minimal-proxy clone...`), 1200);
      setTimeout(() => {
        const mockAddress = '0x' + Math.random().toString(16).substring(2, 42).padEnd(40, '0');
        appendLog(`[success] Sovereign clone of ${activeContract.name} successfully registered at ${mockAddress}`);
        setDeployedContracts(prev => [...prev, { name: `${activeContract.name} (Sovereign Proxy)`, address: mockAddress }]);
        setRightPanelTab('deployed');
      }, 2000);
    } else {
      appendLog(`[deploy] Deploying ${activeContract.name} in CENTRALIZED mode (Ownership will be assigned directly to your EOA wallet)`);
      setTimeout(() => appendLog(`[system] Broadcasting raw deployment transaction...`), 600);
      setTimeout(() => {
        const mockAddress = '0x' + Math.random().toString(16).substring(2, 42).padEnd(40, '0');
        appendLog(`[success] Centralized contract ${activeContract.name} deployed directly at ${mockAddress}`);
        setDeployedContracts(prev => [...prev, { name: `${activeContract.name} (Centralized)`, address: mockAddress }]);
        setRightPanelTab('deployed');
      }, 2000);
    }
  };

  const getContractCode = (name: string) => {
    return localFiles.find(f => f.name === name)?.content || '// Contract not found';
  };

  const handleEditorChange = (value: string | undefined) => {
    if (activeContract && value !== undefined) {
      setLocalFiles(localFiles.map(f => f.name === activeContract.id ? { ...f, content: value } : f));
    }
  };

  const handleNewFile = (e: React.MouseEvent) => {
    e.stopPropagation();
    const name = prompt('Enter new file name (e.g., MyContract.sol):');
    if (name) {
      if (localFiles.some(f => f.name === name)) {
        alert('File already exists!');
        return;
      }
      const newFile = { name, content: '// New Contract\\n' };
      setLocalFiles([...localFiles, newFile]);
      setActiveContract({ id: name, name });
      appendLog(`[system] Created new file ${name}`);
      setIsContractsOpen(true);
    }
  };

  const handleDeleteFile = (name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm(`Are you sure you want to delete ${name}?`)) {
      setLocalFiles(localFiles.filter(f => f.name !== name));
      if (activeContract?.id === name) {
        setActiveContract(null);
      }
      appendLog(`[system] Deleted file ${name}`);
    }
  };

  return (
    <div className="main-content" style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', backgroundColor: 'var(--bg-main)', color: 'var(--text-primary)' }}>
      <TopBar title="Smart Contracts & Architecture" />

      <div className="legacy-ide-theme" style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden', fontFamily: 'inherit' }}>
      {/* IDE Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 20px', backgroundColor: 'var(--bg-surface)', borderBottom: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Code size={18} style={{ color: 'var(--text-muted)' }} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Integrity IDE Workstation</span>
          <SeededDataBadge label="Build/Deploy/calls below are simulated — no compiler or deploy route exists" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Deployment Mode Selector */}
          <div style={{ display: 'flex', alignItems: 'center', backgroundColor: 'var(--bg-main)', padding: '2px', borderRadius: '6px', border: '1px solid var(--border-color)', gap: '2px' }}>
            <button 
              onClick={() => {
                setDeploymentMode('sovereign');
                appendLog('[system] Switched target to SOVEREIGN mode (EIP-1167 proxy owned by SovereignAgent).');
              }}
              style={{
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: deploymentMode === 'sovereign' ? 'var(--accent-primary)' : 'transparent',
                color: deploymentMode === 'sovereign' ? 'var(--bg-main)' : 'var(--text-muted)',
                transition: 'all 0.15s ease'
              }}
              title="Deploys as an EIP-1167 minimal-proxy clone. Admin/owner role is assigned to the agent's SovereignAgent contract."
            >
              Sovereign (Agent)
            </button>
            <button 
              onClick={() => {
                setDeploymentMode('centralized');
                appendLog('[system] Switched target to CENTRALIZED mode (Direct EOA-owned singleton).');
              }}
              style={{
                padding: '4px 10px',
                fontSize: '11px',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: deploymentMode === 'centralized' ? 'var(--gold)' : 'transparent',
                color: deploymentMode === 'centralized' ? 'black' : 'var(--text-muted)',
                transition: 'all 0.15s ease'
              }}
              title="Deploys directly to the chain. Admin/owner role is assigned directly to your active EOA key."
            >
              Centralized (EOA)
            </button>
          </div>

          <button className="btn btn-secondary" style={{ padding: '6px 14px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => appendLog('State saved locally.')}>
            <Save size={14} /> Save
          </button>
          <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: '13px', background: 'var(--accent-primary)', color: 'var(--bg-main)', border: 'none', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={handleBuild}>
            <Cpu size={14} /> Build
          </button>
          <button 
            className="btn btn-primary" 
            style={{ 
              padding: '6px 14px', 
              fontSize: '13px', 
              background: deploymentMode === 'sovereign' ? 'var(--accent-primary)' : 'var(--gold)', 
              color: deploymentMode === 'sovereign' ? 'var(--bg-main)' : 'black', 
              border: 'none', 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px', 
              fontWeight: 'bold',
              transition: 'all 0.2s ease'
            }} 
            onClick={handleDeploy}
          >
            <ShieldCheck size={14} /> Deploy {deploymentMode === 'sovereign' ? '(Sovereign)' : '(Centralized)'}
          </button>
        </div>
      </div>

      {/* Main IDE Layout */}
      <div style={{ display: 'flex', flex: 1, gap: '4px', overflow: 'hidden', padding: '4px', backgroundColor: 'var(--border-color)', minHeight: 0 }}>
        
        {/* Left Panel - File Explorer */}
        <div style={{ width: '280px', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-sidebar)', borderRight: '1px solid var(--border-color)', minHeight: 0 }}>
          <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-color)', fontWeight: 'bold', fontSize: '13px', textTransform: 'uppercase' }}>
            <Folder size={14} style={{ display: 'inline', marginRight: '6px' }} /> Workspace
          </div>
          <div className="custom-scrollbar" style={{ flex: 1, overflowY: 'auto' }}>
            
            {/* Smart Contracts Folder */}
            <div 
              onClick={() => setIsContractsOpen(!isContractsOpen)}
              style={{ padding: '4px 8px', fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', transition: 'background-color 0.2s', borderRadius: '4px' }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-panel-hover)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                {isContractsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <Folder size={14} style={{ color: 'var(--gold)' }} /> src/contracts
              </div>
              <Plus 
                size={14} 
                style={{ cursor: 'pointer', color: 'var(--text-muted)' }} 
                onClick={handleNewFile}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--text-primary)'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
              />
            </div>
            
            {isContractsOpen && localFiles.map(file => (
              <div 
                key={file.name}
                onClick={() => handleSelectContract(file.name)}
                style={{ 
                  padding: '4px 8px 4px 32px', 
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '13px',
                  backgroundColor: activeContract?.id === file.name ? 'var(--bg-panel-hover)' : 'transparent',
                  color: activeContract?.id === file.name ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  borderLeft: activeContract?.id === file.name ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  transition: 'background-color 0.2s'
                }}
                onMouseEnter={(e) => { if (activeContract?.id !== file.name) e.currentTarget.style.backgroundColor = 'var(--bg-panel-hover)' }}
                onMouseLeave={(e) => { if (activeContract?.id !== file.name) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <File size={14} style={{ color: activeContract?.id === file.name ? 'var(--accent-primary)' : 'var(--text-muted)', flexShrink: 0 }} /> 
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
                </div>
                <Trash2 
                  size={12} 
                  style={{ color: 'var(--text-muted)', opacity: activeContract?.id === file.name ? 1 : 0.4, cursor: 'pointer', flexShrink: 0 }} 
                  onClick={(e) => handleDeleteFile(file.name, e)}
                  onMouseEnter={(e) => e.currentTarget.style.color = 'var(--danger)'}
                  onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                />
              </div>
            ))}

            {/* Connected Agents Folder */}
            <div 
              onClick={() => setIsAgentsOpen(!isAgentsOpen)}
              style={{ padding: '4px 8px', fontSize: '12px', fontWeight: 'bold', color: 'var(--text-secondary)', marginTop: '16px', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', transition: 'background-color 0.2s', borderRadius: '4px' }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-panel-hover)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
            >
              {isAgentsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <Folder size={14} style={{ color: 'var(--primary)' }} /> connected_agents
            </div>
            
            {isAgentsOpen && agents.map(agent => (
              <div 
                key={agent.id}
                onClick={() => handleSelectAgent(agent.id)}
                style={{ 
                  padding: '4px 16px 4px 32px', 
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '13px',
                  backgroundColor: activeAgent?.id === agent.id ? 'var(--bg-panel-hover)' : 'transparent',
                  color: activeAgent?.id === agent.id ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  borderLeft: activeAgent?.id === agent.id ? '2px solid var(--accent-primary)' : '2px solid transparent',
                  transition: 'background-color 0.2s'
                }}
                onMouseEnter={(e) => { if (activeAgent?.id !== agent.id) e.currentTarget.style.backgroundColor = 'var(--bg-panel-hover)' }}
                onMouseLeave={(e) => { if (activeAgent?.id !== agent.id) e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <Cpu size={14} style={{ color: activeAgent?.id === agent.id ? 'var(--accent-primary)' : 'var(--text-muted)' }} /> {agent.id.substring(0, 8)}...{agent.id.substring(agent.id.length - 4)}
              </div>
            ))}
          </div>
        </div>

        {/* Center Panel - Editor */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-main)', minHeight: 0 }}>
          <div style={{ display: 'flex', backgroundColor: 'var(--bg-sidebar)', borderBottom: '1px solid var(--border-color)', overflowX: 'auto' }}>
            {openTabs.map(tab => (
              <div 
                key={tab}
                onClick={() => handleSelectContract(tab)}
                style={{ 
                  padding: '8px 16px', 
                  backgroundColor: activeContract?.id === tab ? 'var(--bg-main)' : 'transparent', 
                  color: activeContract?.id === tab ? 'var(--accent-primary)' : 'var(--text-muted)', 
                  fontSize: '13px', 
                  borderTop: activeContract?.id === tab ? '2px solid var(--accent-primary)' : '2px solid transparent', 
                  borderRight: '1px solid var(--border-color)',
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '8px',
                  cursor: 'pointer'
                }}
              >
                <File size={14} /> {tab}
                <X size={14} style={{ opacity: 0.6, cursor: 'pointer' }} onClick={(e) => handleCloseTab(tab, e)} onMouseEnter={(e) => e.currentTarget.style.opacity = '1'} onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'} />
              </div>
            ))}
            {openTabs.length === 0 && (
              <div style={{ padding: '8px 16px', color: 'var(--text-muted)', fontSize: '13px' }}>No open files</div>
            )}
          </div>
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            {activeContract ? (
              <Editor
                height="100%"
                defaultLanguage="solidity"
                theme="vs-dark"
                value={getContractCode(activeContract.id)}
                onChange={handleEditorChange}
                beforeMount={registerSolidityLanguage}
                options={{
                  minimap: { enabled: true },
                  fontSize: 14,
                  fontFamily: 'inherit',
                  scrollBeyondLastLine: false,
                  readOnly: false,
                }}
              />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '14px' }}>
                Select a contract to view its source
              </div>
            )}
          </div>
        </div>

        {/* Right Panel - Context/Agent Details */}
        <div style={{ width: '380px', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-sidebar)', borderLeft: '1px solid var(--border-color)', minHeight: 0 }}>
          <div style={{ display: 'flex', backgroundColor: 'var(--bg-sidebar)', borderBottom: '1px solid var(--border-color)' }}>
            <div 
              onClick={() => setRightPanelTab('agent')}
              style={{ flex: 1, cursor: 'pointer', padding: '8px 16px', backgroundColor: rightPanelTab === 'agent' ? 'var(--bg-main)' : 'transparent', color: rightPanelTab === 'agent' ? 'var(--primary)' : 'var(--text-muted)', fontSize: '13px', borderTop: rightPanelTab === 'agent' ? '2px solid var(--primary)' : '2px solid transparent', borderRight: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
              <Cpu size={14} /> Inspector
            </div>
            <div 
              onClick={() => setRightPanelTab('deployed')}
              style={{ flex: 1, cursor: 'pointer', padding: '8px 16px', backgroundColor: rightPanelTab === 'deployed' ? 'var(--bg-main)' : 'transparent', color: rightPanelTab === 'deployed' ? 'var(--primary)' : 'var(--text-muted)', fontSize: '13px', borderTop: rightPanelTab === 'deployed' ? '2px solid var(--primary)' : '2px solid transparent', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
              <Play size={14} /> Deployed
            </div>
          </div>
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            {rightPanelTab === 'agent' ? (
              activeAgent ? (
                <div className="custom-scrollbar" style={{ padding: '24px', overflowY: 'auto', height: '100%', fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#d4d4d4', backgroundColor: '#1e1e1e' }}>
                <div style={{ marginBottom: '16px', color: '#569cd6' }}>
                  <ShieldCheck style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} size={16} />
                  // AgentPrimitivesFactory: 7 Primitive Contract Statuses
                </div>
                
                {isLoadingAgent ? (
                  <div style={{ color: '#ce9178' }}>&gt; Fetching primitives from registry...</div>
                ) : agentPrimitives ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ color: '#6a9955', marginBottom: '8px' }}>/* Discovered primitives for {activeAgent.name} */</div>
                    {[
                      { key: 'sovereign_agent', label: 'Sovereign Agent (Core)' },
                      { key: 'state_anchor', label: 'State Anchor' },
                      { key: 'reputation_registry', label: 'Reputation Registry' },
                      { key: 'slasher', label: 'Slasher' },
                      { key: 'verifier_registry', label: 'Verifier Registry' },
                      { key: 'compliance_gate', label: 'Compliance Gate' },
                      { key: 'agent_profile', label: 'Agent Profile' },
                    ].map((prim) => {
                      const address = agentPrimitives[prim.key as keyof typeof agentPrimitives];
                      const isValid = address && address !== '0x0000000000000000000000000000000000000000';
                      const paddedLabel = prim.label.padEnd(25, '.');
                      return (
                        <div key={prim.key} style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
                          <span style={{ color: '#9cdcfe', minWidth: '180px' }}>{paddedLabel}</span>
                          <span>
                            {isValid ? <span style={{ color: '#4ec9b0' }}>[ OK ]</span> : <span style={{ color: '#f44336' }}>[ ERR ]</span>}
                          </span>
                        </div>
                      );
                    })}

                    {agentAis && (
                      <div style={{ marginTop: '24px', borderTop: '1px dashed #444', paddingTop: '16px' }}>
                        <div style={{ color: '#c586c0', marginBottom: '12px' }}>&gt; AIS_Telemetry_Snapshot()</div>
                        <div style={{ display: 'flex', gap: '16px', alignItems: 'baseline' }}>
                          <span style={{ color: '#9cdcfe' }}>System.Score:</span>
                          <span style={{ fontSize: '18px', fontWeight: 'bold', color: agentAis.ais >= 700 ? '#4ec9b0' : '#d7ba7d' }}>
                            {agentAis.ais} <span style={{ fontSize: '12px', fontWeight: 'normal', color: '#808080' }}>/ 1000</span>
                          </span>
                        </div>
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px', color: '#d4d4d4' }}>
                          <div>Entropy: <span style={{ color: '#b5cea8' }}>{agentAis.components.entropy}</span></div>
                          <div>Grounding: <span style={{ color: '#b5cea8' }}>{agentAis.components.grounding}</span></div>
                          <div>Sacrifice: <span style={{ color: '#b5cea8' }}>{agentAis.components.sacrifice}</span></div>
                          <div>Compliance: <span style={{ color: '#b5cea8' }}>{agentAis.components.compliance}</span></div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ color: '#f44336' }}>[!] Agent not found in registry.</div>
                )}
              </div>
            ) : (
              <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
                Select an agent from the workspace to inspect its on-chain primitives and telemetry profile.
              </div>
            )
          ) : (
              <div className="custom-scrollbar" style={{ padding: '24px', overflowY: 'auto', height: '100%', fontFamily: 'var(--font-mono)', fontSize: '13px', color: '#d4d4d4', backgroundColor: '#1e1e1e' }}>
                <div style={{ marginBottom: '16px', color: '#569cd6' }}>
                  <Play style={{ display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} size={16} />
                  // Deployed Contracts (Local Base Sepolia Fork)
                </div>
                {deployedContracts.length > 0 ? deployedContracts.map((contract, i) => (
                  <div key={i} style={{ marginBottom: '16px', padding: '12px', border: '1px solid #333', borderRadius: '4px', backgroundColor: '#252526' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ color: '#4ec9b0', fontWeight: 'bold' }}>{contract.name}</span>
                      <span style={{ color: '#ce9178' }}>{contract.address.substring(0,8)}...{contract.address.substring(38)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                      {(() => {
                        const matches = getContractCode(contract.name).match(/function\s+([a-zA-Z0-9_]+)/g);
                        if (matches && matches.length > 0) {
                          return matches.slice(0, 6).map((m, j) => (
                            <button key={j} className="btn btn-secondary" style={{ flex: '1 1 45%', padding: '4px 8px', fontSize: '12px', border: '1px solid #444', backgroundColor: '#333', color: '#d4d4d4', overflow: 'hidden', textOverflow: 'ellipsis' }} onClick={() => appendLog(`[system] Transaction: ${m.replace('function ', '')}() on ${contract.name}`)}>
                              {m.replace('function ', '')}
                            </button>
                          ));
                        } else {
                          return (
                            <button className="btn btn-secondary" style={{ flex: 1, padding: '4px 8px', fontSize: '12px', border: '1px solid #444', backgroundColor: '#333', color: '#d4d4d4' }} onClick={() => appendLog(`[system] Interactive ABI for ${contract.name} called.`)}>
                              Interact
                            </button>
                          );
                        }
                      })()}
                    </div>
                  </div>
                )) : (
                  <div style={{ color: '#808080' }}>
                    No contracts deployed in this session.<br/><br/>
                    Open a contract in the editor and click "Deploy" to simulate deployment.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Bottom Panel - Terminal */}
      <div style={{ height: '220px', flexShrink: 0, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-panel)', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '12px', textTransform: 'uppercase', fontWeight: 'bold' }}>
          <Terminal size={14} /> System Console (tty1)
        </div>
        <div 
          ref={terminalRef}
          style={{ 
            flex: 1, padding: '12px', overflowY: 'auto', 
            fontSize: '13px', 
            display: 'flex', flexDirection: 'column', gap: '4px'
          }}
        >
          {logs.map((log, i) => (
            <div key={i} style={{ 
              color: log.includes('error') ? 'var(--danger)' : log.includes('success') ? 'var(--success)' : 'var(--text-secondary)',
              wordBreak: 'break-all'
            }}>
              {log}
            </div>
          ))}
        </div>
      </div>
      </div>
    </div>
  );
};
