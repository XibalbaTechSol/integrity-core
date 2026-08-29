import { forwardRef, useEffect, useMemo, useRef, useState, useImperativeHandle } from 'react';
import ForceGraph3D, { type ForceGraphMethods, type NodeObject, type LinkObject } from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import * as THREE from 'three';
import type { ShieldDashboardSummary } from '../services/shieldBackend';

const NODE_COLORS: Record<string, string> = {
    tenant: '#334155',
    device: '#2563eb',
    policy: '#7c3aed',
    decision_bad: '#dc2626',
    decision_good: '#16a34a',
    export: '#0f766e',
    integration: '#f59e0b',
    metrics: '#0f766e',
};

const EDGE_COLORS: Record<string, string> = {
    enrollment: '#64748b',
    policy: '#7c3aed',
    decision: '#f97316',
    export: '#0f766e',
    integration: '#0f766e',
    metrics: '#0f766e',
};

// react-force-graph-3d's canvas does not track its container's actual size on its own
function useContainerSize<T extends HTMLElement>() {
    const ref = useRef<T>(null);
    const [size, setSize] = useState({ width: 0, height: 0 });

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const observer = new ResizeObserver(([entry]) => {
            const { width, height } = entry.contentRect;
            setSize({ width, height });
        });
        observer.observe(el);
        return () => observer.disconnect();
    }, []);

    return [ref, size] as const;
}

const NODE_RADIUS = 5;
const GRID_SPACING = 40;
const GRID_EXTENT = 2000;
const GRID_DIVISIONS = GRID_EXTENT / GRID_SPACING;

export interface ShieldEvidenceGraphHandle {
    zoomToFit: () => void;
}

interface Props {
    summary: ShieldDashboardSummary | null;
    background: 'light' | 'dark' | 'plain' | 'blueprint';
    edgeType: string;
}

export const ShieldEvidenceGraph = forwardRef<ShieldEvidenceGraphHandle, Props>(function ShieldEvidenceGraph(
    { summary, background, edgeType },
    ref,
) {
    const [containerRef, { width, height }] = useContainerSize<HTMLDivElement>();
    const fgRef = useRef<ForceGraphMethods>(undefined);
    const snapEnabledRef = useRef(false);

    useImperativeHandle(ref, () => ({
        zoomToFit: () => fgRef.current?.zoomToFit(600, 80),
    }));

    const backgroundColor = useMemo(() => {
        if (background === 'dark') return '#0f172a';
        if (background === 'blueprint') return '#1e3a8a';
        if (background === 'plain') return '#ffffff';
        return '#f8fafc'; // light
    }, [background]);

    const showGrid = background !== 'plain';
    const gridLineColor = background === 'blueprint' ? 0x3b82f6 : background === 'dark' ? 0x334155 : 0xe2e8f0;
    const gridCenterLineColor = background === 'blueprint' ? 0x60a5fa : background === 'dark' ? 0x475569 : 0xcbd5e1;

    const graphData = useMemo(() => {
        if (!summary) return { nodes: [], links: [] };

        const nodes: any[] = [];
        const links: any[] = [];

        const tenantId = `tenant_${summary.tenant_id}`;
        nodes.push({ id: tenantId, label: `Tenant: ${summary.tenant_id}`, type: 'tenant' });

        const policies = new Set<string>();

        summary.devices.forEach((device) => {
            const devId = `device_${device.device_id}`;
            nodes.push({ id: devId, label: device.device_id, type: 'device' });
            if (edgeType === 'all' || edgeType === 'enrollment') {
                links.push({ source: tenantId, target: devId, type: 'enrollment' });
            }

            if (device.policy_hash) {
                const polId = `policy_${device.policy_hash}`;
                if (!policies.has(polId)) {
                    nodes.push({ id: polId, label: `Policy ${device.policy_hash.slice(0, 8)}`, type: 'policy' });
                    policies.add(polId);
                }
                if (edgeType === 'all' || edgeType === 'policy') {
                    links.push({ source: devId, target: polId, type: 'policy' });
                }
            }
        });

        summary.latest_decisions.forEach((decision, idx) => {
            const decId = `decision_${idx}`;
            const devId = `device_${decision.decision.device_id || 'unknown'}`;
            const action = decision.decision.decision?.action || 'unknown';
            const isGood = action === 'allow' || action === 'log_only';
            nodes.push({ id: decId, label: action, type: isGood ? 'decision_good' : 'decision_bad' });
            if (edgeType === 'all' || edgeType === 'decision') {
                links.push({ source: devId, target: decId, type: 'decision' });
            }
            const exportInfo = decision.decision.export as { decision_exported?: boolean; authorized?: boolean } | undefined;
            if (exportInfo?.decision_exported || exportInfo?.authorized) {
                const expId = `export_${idx}`;
                nodes.push({ id: expId, label: 'Export', type: 'export' });
                if (edgeType === 'all' || edgeType === 'export') {
                    links.push({ source: decId, target: expId, type: 'export' });
                }
            }
        });

        summary.integrations?.forEach((int) => {
            const intId = `integration_${int.integration_id}`;
            nodes.push({ id: intId, label: int.kind, type: 'integration' });
            if (edgeType === 'all' || edgeType === 'integration') {
                links.push({ source: tenantId, target: intId, type: 'integration' });
            }
        });

        if (summary.latest_metrics) {
            const metId = `metrics_latest`;
            nodes.push({ id: metId, label: 'Metrics', type: 'metrics' });
            if (edgeType === 'all' || edgeType === 'metrics') {
                links.push({ source: tenantId, target: metId, type: 'metrics' });
            }
        }

        return { nodes, links };
    }, [summary, edgeType]);

    useEffect(() => {
        snapEnabledRef.current = false;
        const timer = setTimeout(() => {
            snapEnabledRef.current = true;
            fgRef.current?.d3ReheatSimulation();
        }, 3000);
        return () => clearTimeout(timer);
    }, [graphData]);

    useEffect(() => {
        const initialFit = setTimeout(() => fgRef.current?.zoomToFit(600, 80), 1800);
        const postSnapFit = setTimeout(() => fgRef.current?.zoomToFit(600, 80), 3600);
        return () => {
            clearTimeout(initialFit);
            clearTimeout(postSnapFit);
        };
    }, [graphData]);

    const isFirstSize = useRef(true);
    useEffect(() => {
        if (width === 0 || height === 0) return;
        if (isFirstSize.current) {
            isFirstSize.current = false;
            return;
        }
        const timer = setTimeout(() => fgRef.current?.zoomToFit(400, 80), 120);
        return () => clearTimeout(timer);
    }, [width, height]);

    useEffect(() => {
        const fg = fgRef.current;
        if (!fg || !showGrid) return;
        const scene = fg.scene();
        const half = GRID_EXTENT / 2;

        const makeFace = (rotation: [number, number, number], position: [number, number, number]) => {
            const face = new THREE.GridHelper(GRID_EXTENT, GRID_DIVISIONS, gridLineColor, gridCenterLineColor);
            face.rotation.set(...rotation);
            face.position.set(...position);
            return face;
        };

        const faces = [
            makeFace([0, 0, 0], [0, -half, 0]),
            makeFace([0, 0, 0], [0, half, 0]),
            makeFace([Math.PI / 2, 0, 0], [0, 0, -half]),
            makeFace([Math.PI / 2, 0, 0], [0, 0, half]),
            makeFace([0, 0, Math.PI / 2], [-half, 0, 0]),
            makeFace([0, 0, Math.PI / 2], [half, 0, 0]),
        ];

        faces.forEach((f) => scene.add(f));
        return () => {
            faces.forEach((f) => {
                scene.remove(f);
                f.geometry.dispose();
                (f.material as THREE.Material).dispose();
            });
        };
    }, [width, height, showGrid, gridLineColor, gridCenterLineColor]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
            <div ref={containerRef} style={{ width: '100%', height: '420px', position: 'relative' }}>
                {width > 0 && height > 0 && (
                    <ForceGraph3D
                        ref={fgRef}
                        width={width}
                        height={height}
                        graphData={graphData}
                        nodeId="id"
                        nodeRelSize={NODE_RADIUS}
                        nodeColor={(node: NodeObject) => {
                            const n = node as unknown as { type: string };
                            return NODE_COLORS[n.type] ?? '#94a3b8';
                        }}
                        nodeOpacity={0.92}
                        nodeThreeObject={(node: NodeObject) => {
                            const n = node as unknown as { type: string; label: string };
                            const sprite = new SpriteText(n.label);
                            sprite.color = background === 'dark' || background === 'blueprint' ? '#f8fafc' : '#0f172a';
                            sprite.textHeight = 1.2;
                            sprite.backgroundColor = background === 'dark' || background === 'blueprint' ? 'rgba(15, 23, 42, 0.7)' : 'rgba(255, 255, 255, 0.7)';
                            sprite.padding = 1;
                            (sprite as unknown as { position: { set(x: number, y: number, z: number): void } }).position.set(0, NODE_RADIUS + 2, 0);
                            return sprite;
                        }}
                        nodeThreeObjectExtend={true}
                        linkColor={(link: LinkObject) => {
                            const l = link as unknown as { type: string };
                            return EDGE_COLORS[l.type] ?? '#475569';
                        }}
                        linkWidth={1}
                        linkOpacity={0.6}
                        linkDirectionalArrowLength={4}
                        linkDirectionalParticles={1}
                        linkDirectionalParticleWidth={1.5}
                        linkDirectionalParticleSpeed={0.005}
                        linkDirectionalParticleColor={(link: LinkObject) => {
                            const l = link as unknown as { type: string };
                            return EDGE_COLORS[l.type] ?? '#475569';
                        }}
                        onEngineTick={() => {
                            if (!snapEnabledRef.current) return;
                            for (const node of graphData.nodes) {
                                const n = node as unknown as {
                                    x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number;
                                };
                                if (typeof n.x === 'number') n.x = Math.round(n.x / GRID_SPACING) * GRID_SPACING;
                                if (typeof n.y === 'number') n.y = Math.round(n.y / GRID_SPACING) * GRID_SPACING;
                                if (typeof n.z === 'number') n.z = Math.round(n.z / GRID_SPACING) * GRID_SPACING;
                                n.vx = 0;
                                n.vy = 0;
                                n.vz = 0;
                            }
                        }}
                        backgroundColor={backgroundColor}
                    />
                )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', padding: '12px 14px', borderTop: '1px solid var(--border-color, #e7ebf0)', background: 'var(--bg-color, #f8fafc)', opacity: 0.9 }}>
                <div>
                    <h3 style={{ margin: '0 0 8px', fontSize: '13px', textTransform: 'uppercase', color: 'var(--text-secondary, #485361)' }}>Nodes</h3>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', display: 'inline-block', border: '1px solid rgba(0,0,0,.14)', flex: '0 0 auto', background: '#334155' }}></span>Tenant root and control plane scope.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', display: 'inline-block', border: '1px solid rgba(0,0,0,.14)', flex: '0 0 auto', background: '#2563eb' }}></span>Device enrolled with Shield backend.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', display: 'inline-block', border: '1px solid rgba(0,0,0,.14)', flex: '0 0 auto', background: '#7c3aed' }}></span>Policy bundle and trusted hash boundary.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', display: 'inline-block', border: '1px solid rgba(0,0,0,.14)', flex: '0 0 auto', background: '#dc2626' }}></span>Deny, escalate, contain, or export-gap decision.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '12px', height: '12px', borderRadius: '50%', display: 'inline-block', border: '1px solid rgba(0,0,0,.14)', flex: '0 0 auto', background: '#16a34a' }}></span>Allowed/log-only decision or healthy export path.</div>
                </div>
                <div>
                    <h3 style={{ margin: '0 0 8px', fontSize: '13px', textTransform: 'uppercase', color: 'var(--text-secondary, #485361)' }}>Connections</h3>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '24px', height: '0', borderTop: '3px solid #64748b', display: 'inline-block', flex: '0 0 auto' }}></span>Enrollment links tenant to devices.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '24px', height: '0', borderTop: '3px solid #7c3aed', display: 'inline-block', flex: '0 0 auto' }}></span>Policy links device to active bundle metadata.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '24px', height: '0', borderTop: '3px solid #f97316', display: 'inline-block', flex: '0 0 auto' }}></span>Decision links device to observed policy outcome.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '6px 0', color: 'var(--text-primary, #38424e)' }}><span style={{ width: '24px', height: '0', borderTop: '3px solid #0f766e', display: 'inline-block', flex: '0 0 auto' }}></span>Export, integration, and metrics links show evidence flow.</div>
                </div>
            </div>
        </div>
    );
});
