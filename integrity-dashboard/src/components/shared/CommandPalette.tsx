import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Activity, Wallet, FileCode, Shield, Users, Command, BookOpen, Fingerprint } from 'lucide-react';
import { useDashboard } from '../../context/useDashboard';

interface Action {
  id: string;
  title: string;
  icon: React.ReactNode;
  category: string;
  onSelect: () => void;
}

export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const { setActiveTab, addToast } = useDashboard();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  const actions: Action[] = [
    { id: 'nav-telemetry', title: 'Go to Telemetry', icon: <Activity size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('telemetry'); setIsOpen(false); } },
    { id: 'nav-wallet', title: 'Go to Wallet', icon: <Wallet size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('wallet'); setIsOpen(false); } },
    { id: 'nav-contracts', title: 'Go to Contracts Factory', icon: <FileCode size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('factory'); setIsOpen(false); } },
    { id: 'nav-shield', title: 'Go to Xibalba Shield', icon: <Shield size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('shield'); setIsOpen(false); } },
    { id: 'nav-identity', title: 'Manage Identity (DIDs)', icon: <Fingerprint size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('identity'); setIsOpen(false); } },
    { id: 'nav-ledger', title: 'View Decentralized Ledger', icon: <BookOpen size={16} />, category: 'Navigation', onSelect: () => { setActiveTab('ledger'); setIsOpen(false); } },
    { id: 'action-theme', title: 'Toggle Theme', icon: <Command size={16} />, category: 'Settings', onSelect: () => { addToast('info', 'Theme toggled'); setIsOpen(false); } },
  ];

  const filteredActions = query 
    ? actions.filter(action => action.title.toLowerCase().includes(query.toLowerCase()) || action.category.toLowerCase().includes(query.toLowerCase()))
    : actions;

  // Handle arrow keys
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % filteredActions.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredActions.length) % filteredActions.length);
      } else if (e.key === 'Enter' && filteredActions.length > 0) {
        e.preventDefault();
        filteredActions[selectedIndex]?.onSelect();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, filteredActions, selectedIndex]);

  // Reset index on query change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '15vh' }}>
          <motion.div 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            exit={{ opacity: 0 }} 
            onClick={() => setIsOpen(false)}
            style={{ position: 'absolute', inset: 0, background: 'rgba(5, 13, 24, 0.7)', backdropFilter: 'blur(8px)' }} 
          />
          <motion.div 
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            style={{ 
              position: 'relative', 
              width: '100%', 
              maxWidth: '600px', 
              background: 'var(--navy-deep)', 
              border: '1px solid var(--glass-border)', 
              borderRadius: 'var(--radius-lg)', 
              overflow: 'hidden',
              boxShadow: '0 30px 60px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05)',
              margin: '0 16px'
            }}
          >
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Search size={20} color="var(--primary)" />
              <input 
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search commands or jump to..." 
                style={{ 
                  flex: 1, 
                  background: 'transparent', 
                  border: 'none', 
                  outline: 'none', 
                  color: 'white', 
                  fontSize: '1.1rem',
                  padding: 0
                }}
              />
              <div style={{ display: 'flex', gap: '4px' }}>
                <kbd style={{ background: 'var(--bg-secondary)', padding: '4px 8px', borderRadius: '4px', fontSize: '0.7rem', color: 'var(--text-muted)', border: '1px solid var(--glass-border)', fontWeight: 600 }}>ESC</kbd>
              </div>
            </div>
            
            <div style={{ maxHeight: '400px', overflowY: 'auto', padding: '12px' }}>
              {filteredActions.length === 0 ? (
                <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
                  <Search size={32} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
                  <p style={{ margin: 0, fontSize: '0.95rem' }}>No commands found for "{query}"</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {filteredActions.map((action, idx) => {
                    const isSelected = idx === selectedIndex;
                    return (
                      <button
                        key={action.id}
                        onClick={action.onSelect}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          width: '100%',
                          padding: '12px 16px',
                          background: isSelected ? 'var(--bg-secondary)' : 'transparent',
                          border: 'none',
                          borderRadius: 'var(--radius-md)',
                          color: isSelected ? 'white' : 'var(--text-primary)',
                          cursor: 'pointer',
                          textAlign: 'left',
                          transition: 'background 0.1s',
                        }}
                      >
                        <div style={{ color: isSelected ? 'var(--primary)' : 'var(--text-muted)' }}>
                          {action.icon}
                        </div>
                        <div style={{ flex: 1, fontSize: '0.9rem', fontWeight: 500 }}>
                          {action.title}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', background: 'rgba(255,255,255,0.05)', padding: '2px 8px', borderRadius: '10px' }}>
                          {action.category}
                        </div>
                        {isSelected && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--primary)', fontWeight: 600, display: 'flex', alignItems: 'center' }}>
                            ↵ Enter
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            
            <div style={{ padding: '10px 16px', background: 'var(--navy-light)', borderTop: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: '16px', color: 'var(--text-muted)', fontSize: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ display: 'flex', gap: '4px' }}>
                  <kbd style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: '3px', fontSize: '0.65rem' }}>↑</kbd>
                  <kbd style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: '3px', fontSize: '0.65rem' }}>↓</kbd>
                </span>
                to navigate
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <kbd style={{ background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: '3px', fontSize: '0.65rem' }}>↵</kbd>
                to select
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
