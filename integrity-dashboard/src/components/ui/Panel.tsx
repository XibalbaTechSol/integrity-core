import type { ReactNode } from 'react';

interface PanelProps {
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export function Panel({ title, icon, action, children, className = '', style }: PanelProps) {
  return (
    <div className={`protocol-panel ${className}`} style={style}>
      {(title || action) && (
        <div className="panel-heading">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {icon && <span style={{ color: 'var(--protocol-blue)', display: 'flex' }}>{icon}</span>}
            {title && (typeof title === 'string' ? <h2 style={{ margin: 0, fontSize: '17px', letterSpacing: '-0.02em' }}>{title}</h2> : title)}
          </div>
          {action && <div style={{ display: 'flex', alignItems: 'center' }}>{action}</div>}
        </div>
      )}
      <div style={{ padding: '20px' }}>
        {children}
      </div>
    </div>
  );
}
