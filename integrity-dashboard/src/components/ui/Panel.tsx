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
    <div className={`panel ${className}`} style={style}>
      {(title || action) && (
        <div className="panel-header">
          <div className="panel-title">
            {icon && <span style={{ color: 'var(--primary)' }}>{icon}</span>}
            {title}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      <div>
        {children}
      </div>
    </div>
  );
}
