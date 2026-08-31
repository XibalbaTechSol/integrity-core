import type { LucideIcon } from 'lucide-react';

export type ControlTab<T extends string> = {
  id: T;
  label: string;
  icon: LucideIcon;
  description?: string;
};

export function ControlTabs<T extends string>({ tabs, active, onChange, label }: {
  tabs: ControlTab<T>[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
}) {
  return (
    <div className="control-tabs" role="tablist" aria-label={label}>
      {tabs.map(({ id, label: tabLabel, icon: Icon }) => (
        <button
          key={id}
          type="button"
          role="tab"
          aria-selected={active === id}
          onClick={() => onChange(id)}
          className={active === id ? 'active' : undefined}
        >
          <Icon size={16} />
          <span>{tabLabel}</span>
        </button>
      ))}
    </div>
  );
}
