import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d';
import type { GraphEdge, GraphNode, GraphPayload } from '../../services/graphMemory';

const NODE_COLOR: Record<string, string> = { memory: '#5b8def', entity: '#f59e0b' };
const EDGE_COLOR: Record<string, string> = { relation: '#64748b', similarity: '#10b981', contradiction: '#ef4444' };

export type EvidenceGraph2DHandle = { zoomToFit: () => void };

function useContainerSize() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, size] as const;
}

export const EvidenceGraph2D = forwardRef<EvidenceGraph2DHandle, {
  data: GraphPayload;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
}>(function EvidenceGraph2D({ data, selectedNodeId, onSelectNode }, ref) {
  const [containerRef, size] = useContainerSize();
  const graphRef = useRef<ForceGraphMethods<NodeObject<GraphNode>, LinkObject<GraphNode, GraphEdge>> | undefined>(undefined);
  const graphData = useMemo(() => ({ nodes: data.nodes.map((node) => ({ ...node })), links: data.edges.map((edge) => ({ ...edge })) }), [data]);

  useImperativeHandle(ref, () => ({ zoomToFit: () => graphRef.current?.zoomToFit(450, 44) }));
  useEffect(() => {
    const timer = window.setTimeout(() => graphRef.current?.zoomToFit(500, 44), 700);
    return () => window.clearTimeout(timer);
  }, [graphData, size.width]);

  return (
    <div ref={containerRef} className="evidence-graph-2d">
      {size.width > 0 && <ForceGraph2D
        ref={graphRef}
        width={size.width}
        height={size.height}
        graphData={graphData}
        nodeId="id"
        backgroundColor="rgba(0,0,0,0)"
        nodeRelSize={5}
        nodeColor={(node) => node.id === selectedNodeId ? '#f8fafc' : NODE_COLOR[String((node as { type?: string }).type)] ?? '#94a3b8'}
        nodeVal={(node) => node.id === selectedNodeId ? 2.2 : (node as { type?: string }).type === 'entity' ? 1.45 : 1}
        linkColor={(link) => EDGE_COLOR[String((link as { type?: string }).type)] ?? '#475569'}
        linkWidth={(link) => (link as { type?: string }).type === 'contradiction' ? 1.8 : 0.8}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkCurvature={(link) => (link as { type?: string }).type === 'similarity' ? 0.08 : 0}
        cooldownTicks={90}
        d3VelocityDecay={0.35}
        onNodeClick={(node) => onSelectNode(String(node.id))}
        nodeCanvasObject={(node, context, scale) => {
          const label = String((node as { label?: string }).label ?? node.id);
          const fontSize = Math.max(9, 11 / Math.sqrt(scale));
          const radius = node.id === selectedNodeId ? 6 : (node as { type?: string }).type === 'entity' ? 5 : 3.8;
          const x = typeof node.x === 'number' ? node.x : 0;
          const y = typeof node.y === 'number' ? node.y : 0;
          context.beginPath();
          context.arc(x, y, radius, 0, Math.PI * 2);
          context.fillStyle = node.id === selectedNodeId ? '#f8fafc' : NODE_COLOR[String((node as { type?: string }).type)] ?? '#94a3b8';
          context.fill();
          if (scale > 1.1 || node.id === selectedNodeId) {
            context.font = `${fontSize}px Raleway, sans-serif`;
            context.textAlign = 'center';
            context.textBaseline = 'top';
            context.fillStyle = '#cbd5e1';
            context.fillText(label.length > 34 ? `${label.slice(0, 31)}…` : label, x, y + radius + 3);
          }
        }}
        nodeCanvasObjectMode={() => 'replace'}
      />}
    </div>
  );
});
