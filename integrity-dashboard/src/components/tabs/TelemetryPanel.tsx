import { ProtocolStats } from '../ui/ProtocolStats';
import { TelemetryStream } from '../ui/TelemetryStream';
import { TelemetryGraphs } from '../ui/TelemetryGraphs';
import { useIsMobile } from '../../utils/useIsMobile';
export function TelemetryPanel() {
  const isMobile = useIsMobile();
  return (
    <div style={{ position: 'relative', overflow: 'hidden', paddingBottom: '40px' }}>
      {/* Radar Grid Background */}
      <div style={{
          position: 'absolute', inset: 0, opacity: 0.1, pointerEvents: 'none',
          backgroundImage: 'linear-gradient(rgba(16, 185, 129, 0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(16, 185, 129, 0.5) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          borderRadius: '24px'
      }} />
      
      <div style={{ margin: '0 auto', position: 'relative', zIndex: 1 }}>
          <ProtocolStats />
          <div style={{ marginTop: '40px' }}>
              <TelemetryGraphs />
          </div>

          <div style={{ marginTop: '40px' }}>
              <div style={{ background: 'rgba(0,0,0,0.4)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', height: isMobile ? '600px' : '700px', overflow: 'hidden', padding: 0, boxShadow: '0 20px 40px rgba(0,0,0,0.4)' }}>
                  <TelemetryStream />
              </div>
          </div>
      </div>
    </div>
  );
}

