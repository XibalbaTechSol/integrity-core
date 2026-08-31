import type { ReactNode } from 'react';

export function ControlHeader({ eyebrow, title, description, actions }: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="control-header">
      <div>
        <span className="control-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="control-header-actions">{actions}</div>}
    </header>
  );
}
