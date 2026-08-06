import { useEffect, useRef, useState } from 'react';
import { oracle, type StreamEvent, type AisResponse } from '../services/oracle';

interface UseOracleStreamResult {
    /** Rolling buffer of the most recent frames, newest first, capped at maxEvents. */
    events: StreamEvent[];
    /** True once the browser's EventSource has actually opened the connection. */
    connected: boolean;
    /** The most recent AisUpdate frame, if any have arrived this session. */
    latestAis: AisResponse | null;
}

// ---------------------------------------------------------------------------
// Shared, ref-counted, visibility-aware EventSource pool.
//
// FIXED 2026-07-17 — this hook used to open a brand-new `EventSource` per
// consumer, per mount, and only ever close it on unmount. That is a real
// resource leak against a hard browser limit, not a style problem:
//
//   * Chrome (and every HTTP/1.1 browser) caps concurrent connections at
//     6 PER ORIGIN. An SSE stream holds one of those 6 open indefinitely by
//     design -- that is what a stream is.
//   * The dashboard opens TWO streams per tab on its own (DashboardPage's
//     `useOracleStream(selectedAgent?.id)` plus WidgetRegistry's
//     EventsWidget `useOracleStream(undefined, 12)`), and TraceAnalyticsPage
//     opens a third on its route.
//   * So ~3 open dashboard tabs exhausts all 6 sockets to the oracle. Every
//     subsequent `fetch()` to that origin then queues FOREVER -- no error, no
//     timeout, no console message, just permanently-pending requests and a UI
//     stuck on empty/"—" states.
//
// Confirmed empirically, not theorised: with the UI wedged, `ss -tnp` showed
// Chrome's network process holding 7 established connections to [::1]:8080
// while `curl` to the same endpoint returned instantly, and navigating the
// same browser directly to /v1/agents rendered all 17 agents immediately --
// i.e. the server was fine and the browser's per-origin pool was the
// bottleneck. This is a user-facing bug (it presents as "no agents listed"),
// not merely a test-harness artifact.
//
// Two fixes, both needed:
//   1. SHARE one real EventSource per stream URL across every consumer of
//      that URL, ref-counted, instead of one per hook call. Collapses the
//      dashboard's own 2 sockets into 1 whenever both consumers watch the
//      same URL.
//   2. DISCONNECT while the page is hidden (Page Visibility API) and
//      reconnect on return. A background tab holding a socket open is pure
//      cost -- nothing is rendering its events -- and this is what keeps N
//      open tabs from linearly consuming the whole per-origin budget.
//
// A real HTTP/2 origin would multiplex all of this over a single connection
// and make the limit moot, but the oracle serves plain HTTP/1.1 today (see
// backend/src/routes.rs -- no TLS/h2 termination), so the client has to be
// the one to behave.
// ---------------------------------------------------------------------------

type FrameListener = (event: StreamEvent) => void;
type ConnectionListener = (connected: boolean) => void;

interface SharedStream {
    /** Null while intentionally disconnected (page hidden) but still referenced. */
    source: EventSource | null;
    /** How many mounted hooks want this URL open. Closed for real at 0. */
    refs: number;
    connected: boolean;
    frameListeners: Set<FrameListener>;
    connectionListeners: Set<ConnectionListener>;
}

const _streams = new Map<string, SharedStream>();

function _open(url: string, stream: SharedStream): void {
    if (stream.source) return;

    const source = new EventSource(url);
    stream.source = source;

    const setConnected = (value: boolean) => {
        stream.connected = value;
        stream.connectionListeners.forEach((listener) => listener(value));
    };

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    const handleFrame = (raw: MessageEvent<string>) => {
        let event: StreamEvent;
        try {
            event = JSON.parse(raw.data);
        } catch {
            return;
        }
        stream.frameListeners.forEach((listener) => listener(event));
    };

    // Named event types the oracle actually emits — see backend/src/stream.rs.
    source.addEventListener('telemetry', handleFrame);
    source.addEventListener('otel_span', handleFrame);
    source.addEventListener('ais_update', handleFrame);
}

function _close(stream: SharedStream): void {
    if (!stream.source) return;
    stream.source.close();
    stream.source = null;
    stream.connected = false;
    stream.connectionListeners.forEach((listener) => listener(false));
}

// One document-level visibility handler for every shared stream, registered
// lazily so this module stays inert (and SSR/test-safe) until a hook actually
// subscribes.
let _visibilityBound = false;

function _bindVisibility(): void {
    if (_visibilityBound || typeof document === 'undefined') return;
    _visibilityBound = true;
    document.addEventListener('visibilitychange', () => {
        _streams.forEach((stream, url) => {
            if (stream.refs === 0) return;
            if (document.hidden) _close(stream);
            else _open(url, stream);
        });
    });
}

function _acquire(url: string, onFrame: FrameListener, onConnection: ConnectionListener): () => void {
    _bindVisibility();

    let stream = _streams.get(url);
    if (!stream) {
        stream = { source: null, refs: 0, connected: false, frameListeners: new Set(), connectionListeners: new Set() };
        _streams.set(url, stream);
    }

    stream.refs += 1;
    stream.frameListeners.add(onFrame);
    stream.connectionListeners.add(onConnection);

    // A consumer mounting into an already-open stream should not have to wait
    // for the next onopen to learn it is connected.
    onConnection(stream.connected);

    if (typeof document === 'undefined' || !document.hidden) _open(url, stream);

    return () => {
        stream.frameListeners.delete(onFrame);
        stream.connectionListeners.delete(onConnection);
        stream.refs -= 1;
        if (stream.refs <= 0) {
            _close(stream);
            _streams.delete(url);
        }
    };
}

/**
 * Subscribes to the oracle's real SSE stream (GET /v1/stream or
 * /v1/agent/{id}/stream — see backend/src/stream.rs). Pass `agentId` to scope to one
 * agent, omit it to receive every agent's events.
 *
 * Every consumer of the same URL shares ONE underlying EventSource, and the
 * connection is dropped while the page is hidden — see this module's header for
 * why that is load-bearing rather than an optimisation. Each consumer still keeps
 * its own independently-capped `events` buffer, so `maxEvents` stays per-consumer.
 *
 * The browser's native EventSource reconnects on a dropped connection by itself,
 * so there is still no manual retry logic here.
 */
export function useOracleStream(agentId?: string, maxEvents = 50): UseOracleStreamResult {
    const [events, setEvents] = useState<StreamEvent[]>([]);
    const [connected, setConnected] = useState(false);
    const [latestAis, setLatestAis] = useState<AisResponse | null>(null);
    const maxEventsRef = useRef(maxEvents);
    maxEventsRef.current = maxEvents;

    useEffect(() => {
        const url = oracle.streamUrl(agentId);

        const onFrame: FrameListener = (event) => {
            setEvents((prev) => [event, ...prev].slice(0, maxEventsRef.current));
            if (event.type === 'AisUpdate') {
                const { type: _type, ...ais } = event;
                setLatestAis(ais as AisResponse);
            }
        };

        return _acquire(url, onFrame, setConnected);
    }, [agentId]);

    return { events, connected, latestAis };
}
