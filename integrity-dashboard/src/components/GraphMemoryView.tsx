import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import ForceGraph3D, { type ForceGraphMethods, type NodeObject, type LinkObject } from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import * as THREE from 'three';
import type { GraphEdge, GraphPayload } from '../services/graphMemory';

// Type-color pairs, distinct per node type / relation vs. similarity edge -- picked for
// contrast against the dashboard's dark panel backgrounds, not the marketing-site palette.
const NODE_COLORS: Record<string, string> = {
    memory: '#5b8def',
    entity: '#f59e0b',
};
const EDGE_COLORS: Record<string, string> = {
    relation: '#64748b',
    similarity: '#10b981',
};

// react-force-graph-3d's canvas does not track its container's actual size on its own -- left
// unset, it measures the container once (often before sibling panels like the search-results/
// side-panel columns exist) and never re-measures, so it can end up wider than its flex parent
// and visually cover those siblings. A ResizeObserver on the wrapping div, with explicit
// width/height passed to ForceGraph3D, keeps the canvas honestly sized to the space it's
// actually given, including when a side panel opens and shrinks that space.
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

const NODE_RADIUS = 5; // matches nodeRelSize below (default nodeVal=1 -> sphere radius = nodeRelSize)
const GRID_SPACING = 40; // world units between grid intersections -- both the visible grid lines
// and node-snapping below share this constant, so nodes actually land where the lines cross.
const GRID_EXTENT = 2000;
const GRID_DIVISIONS = GRID_EXTENT / GRID_SPACING;
const GRID_LINE_COLOR = 0x1e293b;
const GRID_CENTER_LINE_COLOR = 0x0f172a;

export interface GraphMemoryViewHandle {
    zoomToFit: () => void;
}

export type NodeSizeBy = 'connections' | 'length' | 'uniform';

interface Props {
    data: GraphPayload;
    onNodeClick: (nodeId: string) => void;
    onLinkClick?: (edge: GraphEdge) => void;
    selectedNodeId: string | null;
    showGrid: boolean;
    backgroundColor: string;
    sizeBy: NodeSizeBy;
}

export const GraphMemoryView = forwardRef<GraphMemoryViewHandle, Props>(function GraphMemoryView(
    { data, onNodeClick, onLinkClick, selectedNodeId, showGrid, backgroundColor, sizeBy },
    ref,
) {
    const [containerRef, { width, height }] = useContainerSize<HTMLDivElement>();
    const fgRef = useRef<ForceGraphMethods>(undefined);
    const snapEnabledRef = useRef(false);

    const graphData = useMemo(() => {
        console.log("GraphMemoryView graphData", data);
        return {
            nodes: data.nodes.map((n) => ({ ...n })),
            links: data.edges.map((e) => ({ ...e })),
        };
    }, [data]);

    // Degree (connection count) and adjacency, computed once per dataset from the *original*
    // edge list -- not graphData.links, which react-force-graph mutates in place (source/target
    // go from plain id strings to live node object references once the simulation starts), so
    // recomputing from it later would be reading a moving target.
    const { degreeById, neighborsById } = useMemo(() => {
        const degree = new Map<string, number>();
        const neighbors = new Map<string, Set<string>>();
        for (const node of data.nodes) {
            degree.set(node.id, 0);
            neighbors.set(node.id, new Set());
        }
        for (const edge of data.edges) {
            degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
            degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
            neighbors.get(edge.source)?.add(edge.target);
            neighbors.get(edge.target)?.add(edge.source);
        }
        return { degreeById: degree, neighborsById: neighbors };
    }, [data]);

    // Character count of each node's label -- a proxy for "how much content this node
    // represents," available client-side without a backend change. Caveat, documented not
    // hidden: local_api truncates memory labels to 80 chars server-side (graph_payload() slices
    // memory["content"][:80]), so this differentiates "short vs. near-80-char" memories well but
    // can't distinguish two memories that are both longer than that. Entity labels (canonical
    // names) aren't truncated, so they're exact.
    const lengthById = useMemo(() => {
        const lengths = new Map<string, number>();
        for (const node of data.nodes) lengths.set(node.id, node.label.length);
        return lengths;
    }, [data]);

    const nodeSizeValue = (nodeId: string): number => {
        if (sizeBy === 'length') return 1 + Math.sqrt(lengthById.get(nodeId) ?? 1);
        if (sizeBy === 'uniform') return 2;
        return 1 + Math.sqrt(degreeById.get(nodeId) ?? 0); // 'connections'
    };

    // Knowledge-graph "focus mode": selecting a node highlights it and its direct neighbors at
    // full color/width, and mutes everything else to grey -- the standard way to make a dense
    // graph (113 nodes, 200+ edges here) legible once you're looking at one specific node,
    // rather than every node/edge competing for attention all the time.
    const highlightedNeighborIds = selectedNodeId ? neighborsById.get(selectedNodeId) ?? new Set<string>() : null;
    const isDimmed = (nodeId: string) =>
        highlightedNeighborIds !== null && nodeId !== selectedNodeId && !highlightedNeighborIds.has(nodeId);
    const isLinkDimmed = (sourceId: string, targetId: string) =>
        highlightedNeighborIds !== null && selectedNodeId !== sourceId && selectedNodeId !== targetId;

    useImperativeHandle(ref, () => ({
        zoomToFit: () => fgRef.current?.zoomToFit(600, 80),
    }));

    // Grid-snapping can't engage immediately: 3d-force-graph starts every node clustered near
    // the origin and relies on many ticks of charge-repulsion to spread them into a readable
    // layout. Snapping (and zeroing velocity) from tick 1 rounds that near-origin cluster onto
    // the SAME grid intersection and traps it there, since repulsion is killed before it can
    // build enough momentum to escape -- verified by inspecting the canvas after enabling
    // snapping immediately: nothing rendered, all nodes had collapsed onto one point. Letting
    // the natural force layout settle first, then engaging the grid snap as a final discretizing
    // pass, avoids that collapse and keeps the organic clustering the force layout produces.
    // d3ReheatSimulation() guarantees onEngineTick keeps firing at that point even if the
    // simulation had already cooled down and stopped ticking on its own by then.
    useEffect(() => {
        snapEnabledRef.current = false;
        const timer = setTimeout(() => {
            snapEnabledRef.current = true;
            fgRef.current?.d3ReheatSimulation();
        }, 3000);
        return () => clearTimeout(timer);
    }, [graphData]);

    // Auto-fit the camera twice per dataset load: once after the initial force spread (so the
    // user isn't staring at a tiny cluster near the origin while physics runs) and again after
    // grid-snapping settles (node positions shift when they discretize onto the grid, so the
    // pre-snap framing can end up off). Manual zoomToFit (the toolbar button) still works
    // independently via the imperative handle above.
    useEffect(() => {
        const initialFit = setTimeout(() => fgRef.current?.zoomToFit(600, 80), 1800);
        const postSnapFit = setTimeout(() => fgRef.current?.zoomToFit(600, 80), 3600);
        return () => {
            clearTimeout(initialFit);
            clearTimeout(postSnapFit);
        };
    }, [graphData]);

    // Also re-fit whenever the container itself resizes -- e.g. the search-results or memory
    // detail side panel opening/closing narrows the graph's available width. Without this, the
    // camera keeps its pre-resize framing and previously-visible content can end up entirely
    // outside the new (narrower) viewport, reading as "the graph vanished." Skipped on the very
    // first size (0 -> real) since the dataset-load effect above already handles that case.
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

    // A real 3D grid enclosure -- six GridHelper planes, one per cube face, forming a closed
    // "technical blueprint" box around the graph (the standard 3D-scatter-plot box look, e.g.
    // matplotlib's 3D axes), not just a floor or an open corner. Added directly to the three.js
    // scene (via ForceGraph3D's own scene() accessor) since the library's `backgroundColor` prop
    // only takes a flat color, not a pattern. GRID_SPACING is shared with the node-snapping in
    // onEngineTick below, so nodes actually rest where grid lines cross rather than the grid
    // being purely decorative. Toggleable via the showGrid prop.
    useEffect(() => {
        const fg = fgRef.current;
        if (!fg || !showGrid) return;
        const scene = fg.scene();
        const half = GRID_EXTENT / 2;

        const makeFace = (rotation: [number, number, number], position: [number, number, number]) => {
            const face = new THREE.GridHelper(GRID_EXTENT, GRID_DIVISIONS, GRID_LINE_COLOR, GRID_CENTER_LINE_COLOR);
            face.rotation.set(...rotation);
            face.position.set(...position);
            return face;
        };

        const faces = [
            makeFace([0, 0, 0], [0, -half, 0]), // floor
            makeFace([0, 0, 0], [0, half, 0]), // ceiling
            makeFace([Math.PI / 2, 0, 0], [0, 0, -half]), // back wall
            makeFace([Math.PI / 2, 0, 0], [0, 0, half]), // front wall
            makeFace([0, 0, Math.PI / 2], [-half, 0, 0]), // left wall
            makeFace([0, 0, Math.PI / 2], [half, 0, 0]), // right wall
        ];

        faces.forEach((f) => scene.add(f));
        return () => {
            faces.forEach((f) => {
                scene.remove(f);
                f.geometry.dispose();
                (f.material as THREE.Material).dispose();
            });
        };
    }, [width, height, showGrid]);
    console.log("GraphMemoryView render", width, height);
    return (
        <div ref={containerRef} style={{ position: 'absolute', inset: 0 }}>
            {width > 0 && height > 0 && (
                <ForceGraph3D
                    ref={fgRef}
                    width={width}
                    height={height}
                    graphData={graphData}
                    nodeId="id"
                    nodeRelSize={NODE_RADIUS}
                    // Sizing meaning is user-selectable (sizeBy prop): connection count (a hub
                    // entity or heavily-cross-referenced memory reads as visually more important
                    // -- the standard knowledge-graph "centrality" cue), content length, or
                    // uniform. sqrt in nodeSizeValue keeps a large value from dwarfing everything
                    // else on a 113-node graph.
                    nodeVal={(node: NodeObject) => nodeSizeValue((node as unknown as { id: string }).id)}
                    nodeColor={(node: NodeObject) => {
                        const n = node as unknown as { id: string; type: string };
                        if (n.id === selectedNodeId) return '#ef4444';
                        if (isDimmed(n.id)) return '#334155';
                        return NODE_COLORS[n.type] ?? '#94a3b8';
                    }}
                    nodeOpacity={0.92}
                    // Permanent text-sprite labels (not hover-only tooltips), anchored just above
                    // each node's sphere -- nodeThreeObjectExtend:true keeps the default sphere
                    // and adds the sprite as a child of it (so it inherits the sphere's position
                    // and moves with it during the force simulation) rather than replacing the
                    // sphere with free-floating text. Entities get their full canonical name;
                    // memories get a short truncation (full text goes in the side panel on click).
                    //
                    // Sized small by default (113 nodes' worth of full-size labels is unreadable
                    // clutter, especially over the dense wiki entity cluster) and grown + made
                    // opaque only for the selected node, so the graph reads as a shape at a
                    // glance and reveals detail exactly where the user clicked. Dimmed nodes
                    // (outside the selection's neighborhood) drop their label entirely -- focus
                    // mode should quiet the whole node, not just its sphere.
                    nodeThreeObject={(node: NodeObject) => {
                        const n = node as unknown as { id: string; type: string; label: string };
                        const isSelected = n.id === selectedNodeId;
                        const dimmed = isDimmed(n.id);
                        if (dimmed) return new THREE.Object3D(); // empty -- no label while dimmed
                        const text = n.type === 'entity' ? n.label : n.label.slice(0, 28);
                        const sprite = new SpriteText(text);
                        sprite.color = isSelected ? '#ef4444' : (NODE_COLORS[n.type] ?? '#e2e8f0');
                        sprite.textHeight = isSelected ? 3.6 : n.type === 'entity' ? 1.1 : 0.8;
                        sprite.backgroundColor = isSelected ? 'rgba(2, 6, 23, 0.9)' : 'rgba(2, 6, 23, 0.4)';
                        sprite.padding = isSelected ? 2 : 0.5;
                        // SpriteText's bundled .d.ts doesn't surface the inherited THREE.Object3D
                        // members (position/rotation/etc.) even though it extends THREE.Sprite at
                        // runtime -- a type-defs gap, not a real absence of `.position`.
                        (sprite as unknown as { position: { set(x: number, y: number, z: number): void } }).position.set(
                            0,
                            NODE_RADIUS + (isSelected ? 4 : 1.5),
                            0,
                        );
                        return sprite;
                    }}
                    nodeThreeObjectExtend={true}
                    linkColor={(link: LinkObject) => {
                        const l = link as unknown as { source: string | { id: string }; target: string | { id: string }; type: string };
                        const sourceId = typeof l.source === 'string' ? l.source : l.source.id;
                        const targetId = typeof l.target === 'string' ? l.target : l.target.id;
                        if (isLinkDimmed(sourceId, targetId)) return 'rgba(51, 65, 85, 0.25)';
                        return EDGE_COLORS[l.type] ?? '#475569';
                    }}
                    linkWidth={(link: LinkObject) => {
                        const l = link as unknown as { type: string; cosine_similarity?: number };
                        return l.type === 'similarity' ? Math.max(1, (l.cosine_similarity ?? 0.75) * 2) : 0.6;
                    }}
                    linkOpacity={0.55}
                    linkDirectionalArrowLength={(link: LinkObject) =>
                        (link as unknown as { type: string }).type === 'relation' ? 3 : 0
                    }
                    // Small animated particles flowing along relation edges (subject -> object) --
                    // reads as "live data flowing through the graph" rather than a static diagram,
                    // and doubles as a directionality cue clearer than the arrowhead alone.
                    linkDirectionalParticles={(link: LinkObject) =>
                        (link as unknown as { type: string }).type === 'relation' ? 1 : 0
                    }
                    linkDirectionalParticleWidth={1.6}
                    linkDirectionalParticleSpeed={0.004}
                    linkDirectionalParticleColor={() => EDGE_COLORS.relation}
                    onNodeClick={(node: NodeObject) => onNodeClick((node as unknown as { id: string }).id)}
                    onLinkClick={(link: LinkObject) => onLinkClick?.(link as unknown as GraphEdge)}
                    // Snaps every node onto the nearest grid intersection each simulation tick,
                    // once enabled (see snapEnabledRef above -- disabled for the first few
                    // seconds so the natural force layout can spread out first). 3d-force-graph
                    // has no native grid-constraint option, so this is the standard way to
                    // influence it: mutate the same node objects the force engine is already
                    // ticking, in place. Velocity is zeroed after snapping so a node settles once
                    // it reaches its cell instead of oscillating between two adjacent
                    // intersections as the force engine keeps nudging a continuous position that
                    // snapping keeps discretizing.
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
    );
});
