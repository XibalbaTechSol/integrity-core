import { Settings, Save, GripHorizontal, Plus, RotateCcw } from 'lucide-react';
import { TopBar } from '../components/TopBar';
import { useState, useEffect, useRef } from 'react';
import { Responsive } from 'react-grid-layout';
import type { Layout } from 'react-grid-layout';
import { oracle } from '../services/oracle';
import { useOracleStream } from '../hooks/useOracleStream';
import { WidgetRegistry } from '../components/widgets/WidgetRegistry';
import { WidgetWrapper } from '../components/widgets/WidgetWrapper';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgent } from '../contexts/AgentContext';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const ResponsiveGridLayout = (props: any) => {
  const [width, setWidth] = useState(1200);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver((entries) => {
      if (entries[0]) {
        setWidth(entries[0].contentRect.width);
      }
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} style={{ width: '100%' }}>
      <Responsive width={width} {...props} />
    </div>
  );
};

const DEFAULT_WIDGETS = [
  { id: 'tri-metric', type: 'tri-metric' },
  { id: 'cognition', type: 'cognition' },
  { id: 'gauge', type: 'gauge' },
  { id: 'costAnalytics', type: 'costAnalytics' },
  { id: 'latency', type: 'latency' },
  { id: 'leaderboard', type: 'leaderboard' },
  { id: 'nodes', type: 'nodes' },
  { id: 'events', type: 'events' },
  { id: 'sandbox', type: 'sandbox' }
];

const DEFAULT_LAYOUTS = {
  lg: [
    { i: 'tri-metric', x: 0, y: 0, w: 12, h: 3, minW: 6, minH: 3 },
    { i: 'cognition', x: 0, y: 3, w: 12, h: 2, minW: 8, minH: 2 },
    { i: 'gauge', x: 0, y: 5, w: 3, h: 2, minW: 3, minH: 2 },
    { i: 'costAnalytics', x: 3, y: 5, w: 6, h: 2, minW: 4, minH: 2 },
    { i: 'latency', x: 9, y: 5, w: 3, h: 2, minW: 3, minH: 2 },
    { i: 'leaderboard', x: 0, y: 7, w: 4, h: 3, minW: 3, minH: 3 },
    { i: 'nodes', x: 4, y: 7, w: 4, h: 3, minW: 4, minH: 2 },
    { i: 'events', x: 8, y: 7, w: 4, h: 3, minW: 4, minH: 2 },
    { i: 'sandbox', x: 0, y: 10, w: 12, h: 7, minW: 6, minH: 3 }
  ],
  md: [
    { i: 'tri-metric', x: 0, y: 0, w: 10, h: 3, minW: 6, minH: 3 },
    { i: 'cognition', x: 0, y: 3, w: 10, h: 2, minW: 8, minH: 2 },
    { i: 'gauge', x: 0, y: 5, w: 4, h: 2, minW: 3, minH: 2 },
    { i: 'costAnalytics', x: 4, y: 5, w: 6, h: 2, minW: 3, minH: 2 },
    { i: 'leaderboard', x: 0, y: 7, w: 5, h: 3, minW: 3, minH: 3 },
    { i: 'nodes', x: 5, y: 7, w: 5, h: 3, minW: 4, minH: 2 },
    { i: 'events', x: 0, y: 10, w: 5, h: 3, minW: 4, minH: 2 },
    { i: 'latency', x: 5, y: 10, w: 5, h: 3, minW: 3, minH: 2 },
    { i: 'sandbox', x: 0, y: 13, w: 10, h: 7, minW: 6, minH: 3 }
  ]
};

export const DashboardPage = () => {
  const { selectedAgent } = useAgent();
  const [isEditing, setIsEditing] = useState(false);
  const { latestAis } = useOracleStream(selectedAgent?.id);
  const [agentScores, setAgentScores] = useState<Record<string, number>>({});
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [widgets, setWidgets] = useState<Array<{ id: string; type: string }>>([]);
  const [layouts, setLayouts] = useState<any>({ lg: [], md: [] });
  const [aisDistribution, setAisDistribution] = useState<{ name: string; count: number; fill: string }[] | null>(null);
  const [highIntegrityPct, setHighIntegrityPct] = useState<number | null>(null);

  // Initial load from LocalStorage
  useEffect(() => {
    const savedWidgets = localStorage.getItem('integrity_dashboard_widgets_v4');
    const savedLayouts = localStorage.getItem('integrity_dashboard_layouts_v4');
    
    if (savedWidgets && savedLayouts) {
      try {
        setWidgets(JSON.parse(savedWidgets));
        const parsedLayouts = JSON.parse(savedLayouts);
        // Defensively ensure sandbox has enough height
        Object.keys(parsedLayouts).forEach(breakpoint => {
          parsedLayouts[breakpoint] = parsedLayouts[breakpoint].map((l: any) => {
            if (l.i === 'sandbox' && l.h < 7) {
              return { ...l, h: 7 };
            }
            return l;
          });
        });
        setLayouts(parsedLayouts);
      } catch {
        setWidgets(DEFAULT_WIDGETS);
        setLayouts(DEFAULT_LAYOUTS);
      }
    } else {
      setWidgets(DEFAULT_WIDGETS);
      setLayouts(DEFAULT_LAYOUTS);
    }
  }, []);

  // Fetch Oracle Node data
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const summaries = await oracle.listAgents();
        const scoresMap: Record<string, number> = {};
        await Promise.all(summaries.map(async (a) => {
            try {
                const res = await oracle.getAis(a.id);
                scoresMap[a.id] = res.ais;
            } catch (e) {
                // Ignore error, score is not mapped
            }
        }));
        if (cancelled) return;
        setAgentScores(scoresMap);
        // Handled by the agentScores effect now
      } catch {
        if (!cancelled) setAisDistribution(null);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedAgent]);

  // Update real-time score map and distribution
  useEffect(() => {
    if (latestAis) {
      setAgentScores(prev => ({
        ...prev,
        [latestAis.agent_id]: latestAis.ais
      }));
    }
  }, [latestAis]);

  useEffect(() => {
    // If an agent is selected, maybe we show just that agent's stats
    const scores = selectedAgent && agentScores[selectedAgent.id] !== undefined
        ? [agentScores[selectedAgent.id]]
        : Object.values(agentScores);
    
    const total = scores.length;
    const high = scores.filter(s => s >= 900).length;
    const mid = scores.filter(s => s >= 700 && s < 900).length;
    const low = scores.filter(s => s < 700).length;
    setAisDistribution([
        { name: 'High (900+)', count: high, fill: 'var(--success)' },
        { name: 'Medium (700-899)', count: mid, fill: 'var(--warning)' },
        { name: 'Low (<700)', count: low, fill: 'var(--danger)' },
    ]);
    if (total > 0) {
      if (selectedAgent && agentScores[selectedAgent.id] !== undefined) {
          // Display raw AIS score instead of percentage for a single agent
          setHighIntegrityPct(Math.round(agentScores[selectedAgent.id]));
      } else {
          setHighIntegrityPct(Math.round((high / total) * 100));
      }
    } else {
      setHighIntegrityPct(0);
    }
  }, [agentScores, selectedAgent]);

  const onLayoutChange = (_layout: Layout[], allLayouts: any) => {
    // Only update layouts state, don't write to localStorage until saved or editing
    setLayouts(allLayouts);
  };

  const handleSave = () => {
    localStorage.setItem('integrity_dashboard_widgets_v4', JSON.stringify(widgets));
    localStorage.setItem('integrity_dashboard_layouts_v4', JSON.stringify(layouts));
    setIsEditing(false);
  };

  const handleResetDefault = () => {
    setWidgets(DEFAULT_WIDGETS);
    setLayouts(DEFAULT_LAYOUTS);
    localStorage.removeItem('integrity_dashboard_widgets_v4');
    localStorage.removeItem('integrity_dashboard_layouts_v4');
    setIsEditing(false);
  };

  const handleDeleteWidget = (id: string) => {
    const nextWidgets = widgets.filter(w => w.id !== id);
    setWidgets(nextWidgets);

    // Clean up layouts
    const nextLayouts = { ...layouts };
    Object.keys(nextLayouts).forEach(breakpoint => {
      nextLayouts[breakpoint] = nextLayouts[breakpoint].filter((l: any) => l.i !== id);
    });
    setLayouts(nextLayouts);
  };

  const handleAddWidget = (type: string) => {
    const id = `${type}_${Date.now()}`;
    const registryEntry = WidgetRegistry[type];
    if (!registryEntry) return;

    const newWidget = { id, type };
    setWidgets([...widgets, newWidget]);

    // Position new widget at the bottom/next available slot
    const defaultW = registryEntry.defaultSize.w;
    const defaultH = registryEntry.defaultSize.h;

    const nextLayouts = { ...layouts };
    Object.keys(nextLayouts).forEach(breakpoint => {
      const currentBreakpointLayouts = nextLayouts[breakpoint] || [];
      // Find max y
      const maxY = currentBreakpointLayouts.reduce((max: number, item: any) => Math.max(max, item.y + item.h), 0);
      nextLayouts[breakpoint] = [
        ...currentBreakpointLayouts,
        { i: id, x: 0, y: maxY, w: defaultW, h: defaultH, minW: 3, minH: 2 }
      ];
    });

    setLayouts(nextLayouts);
    setShowAddMenu(false);
  };

  return (
    <div className="main-content" style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <TopBar title="Intelligence Command">
        {isEditing && (
          <button 
            className="btn btn-secondary glass-panel-hover"
            onClick={() => setShowAddMenu(!showAddMenu)}
            style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Plus size={16} /> Add Block
          </button>
        )}
        <button 
          className="btn btn-secondary glass-panel-hover"
          onClick={handleResetDefault}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          title="Reset to default dashboard"
        >
          <RotateCcw size={16} /> Reset
        </button>
        <button 
          className={`btn ${isEditing ? 'btn-primary' : 'btn-secondary glass-panel-hover'}`}
          onClick={() => {
            if (isEditing) {
              handleSave();
            } else {
              setIsEditing(true);
            }
          }}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          {isEditing ? <><Save size={16} /> Save Layout</> : <><Settings size={16} /> Edit Layout</>}
        </button>
      </TopBar>

      <div className="page-content custom-scrollbar" style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', paddingBottom: '32px', position: 'relative' }}>
        
        {/* Animated Background Gradients */}
        <div style={{ position: 'absolute', top: '-10%', left: '-10%', width: '40vw', height: '40vw', background: 'radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none', zIndex: 0 }} />
        <div style={{ position: 'absolute', bottom: '-10%', right: '-10%', width: '50vw', height: '50vw', background: 'radial-gradient(circle, rgba(34,197,94,0.05) 0%, transparent 60%)', filter: 'blur(100px)', pointerEvents: 'none', zIndex: 0 }} />

        {/* Add Block Dropdown */}
        <AnimatePresence>
          {showAddMenu && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              style={{
                position: 'absolute',
                top: '16px',
                right: '16px',
                width: '320px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
                zIndex: 100,
                padding: '12px'
              }}
            >
              <h4 style={{ margin: '0 0 12px 0', fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px' }}>
                Select Block Type
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {Object.entries(WidgetRegistry).map(([key, value]) => (
                  <button
                    key={key}
                    onClick={() => handleAddWidget(key)}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      width: '100%',
                      padding: '8px 12px',
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid transparent',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'background-color 0.2s, border-color 0.2s'
                    }}
                    className="add-block-item"
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.06)';
                      e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)';
                      e.currentTarget.style.borderColor = 'transparent';
                    }}
                  >
                    <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)' }}>{value.name}</span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{value.description}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {isEditing && (
          <div style={{ padding: '12px 16px', background: 'rgba(59, 130, 246, 0.1)', border: '1px dashed var(--primary)', borderRadius: 'var(--radius-md)', color: 'var(--primary)', marginBottom: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            <GripHorizontal size={16} /> Drag handles to move, pull bottom-right corner to resize. Click "Save Layout" when done.
          </div>
        )}

        {widgets.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '64px', color: 'var(--text-muted)' }}>
            <h3>Your dashboard is empty</h3>
            <p>Click "Edit Layout" and add widgets to customize your workspace.</p>
          </div>
        ) : (
          <ResponsiveGridLayout
            className={`layout ${isEditing ? 'is-editing' : ''}`}
            layouts={layouts}
            breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
            cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
            rowHeight={150}
            onLayoutChange={onLayoutChange}
            isDraggable={isEditing}
            isResizable={isEditing}
            draggableHandle=".drag-handle"
            margin={[24, 24]}
          >
            {widgets.map((widget) => {
              const registryItem = WidgetRegistry[widget.type];
              if (!registryItem) return null;

              const WidgetComponent = registryItem.component;

              return (
                <div key={widget.id}>
                  <WidgetWrapper
                    id={widget.id}
                    isEditing={isEditing}
                    onDelete={() => handleDeleteWidget(widget.id)}
                  >
                    <WidgetComponent
                      aisDistribution={aisDistribution}
                      highIntegrityPct={highIntegrityPct}
                    />
                  </WidgetWrapper>
                </div>
              );
            })}
          </ResponsiveGridLayout>
        )}

      </div>
    </div>
  );
};
