import re

with open("src/components/Sidebar.tsx", "r") as f:
    code = f.read()

# Add imports
imports = """import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { LockKeyhole, LogOut, Settings, User } from 'lucide-react';
import { userapi } from '../services/userapi';
"""
code = code.replace("import { Link, useLocation } from 'react-router-dom';", imports)
code = code.replace("import { LockKeyhole } from 'lucide-react';", "")

# Add state and logout handler inside Sidebar()
state_and_handler = """export function Sidebar() {
  const [profileOpen, setProfileOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await userapi.logout();
    } catch(e) {}
    navigate('/auth');
  };
"""
code = code.replace("export function Sidebar() {", state_and_handler)

# Replace the foot with the profile + foot
foot = """      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div className="protocol-sidebar-foot"><LockKeyhole size={15} /><span>Key material never rendered</span><small>Protocol surface v1</small></div>
        
        <div className={`sidebar-profile ${profileOpen ? 'open' : ''}`} onClick={() => setProfileOpen(!profileOpen)}>
          <div className="profile-avatar"><User size={15} /></div>
          <div className="profile-info">
            <span>Operator</span>
            <small>Authenticated</small>
          </div>
          
          {profileOpen && (
            <div className="profile-dropdown">
              <Link to="/system" onClick={(e) => e.stopPropagation()}><Settings size={14} /> System settings</Link>
              <button onClick={(e) => { e.stopPropagation(); handleLogout(); }}><LogOut size={14} /> Disconnect</button>
            </div>
          )}
        </div>
      </div>
    </aside>"""
code = re.sub(r'<div className="protocol-sidebar-foot">.*?</aside>', foot, code, flags=re.DOTALL)

with open("src/components/Sidebar.tsx", "w") as f:
    f.write(code)

with open("src/pages/ProtocolDashboardPage.css", "a") as f:
    f.write("""
/* Sidebar Profile Widget */
.sidebar-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  margin: 0 10px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--protocol-line, #213246);
  border-radius: 8px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s, border-color 0.2s;
}
.sidebar-profile:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
}
.profile-avatar {
  width: 28px;
  height: 28px;
  border-radius: 14px;
  background: var(--protocol-blue, #36a7ff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.profile-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.profile-info span {
  font-size: 13px;
  font-weight: 600;
  color: #eef5fb;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.profile-info small {
  font-size: 11px;
  color: #8ea1b4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.profile-dropdown {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  right: 0;
  background: var(--surface-color, #0d1824);
  border: 1px solid var(--protocol-line, #213246);
  border-radius: 8px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  z-index: 100;
  animation: fadeUp 0.15s ease-out;
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
.profile-dropdown a, .profile-dropdown button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  color: #8ea1b4;
  background: transparent;
  border: none;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  font-family: inherit;
}
.profile-dropdown a:hover, .profile-dropdown button:hover {
  background: rgba(255,255,255,0.06);
  color: #eef5fb;
}

@media (max-width: 1000px) {
  .sidebar-profile {
    justify-content: center;
    padding: 10px;
    margin: 10px;
  }
  .profile-info {
    display: none;
  }
}
""")
print("Patched Sidebar and CSS")
