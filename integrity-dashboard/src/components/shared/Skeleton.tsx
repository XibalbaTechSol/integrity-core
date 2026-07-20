import React from 'react';

export function Skeleton({ className = '', style }: { className?: string, style?: React.CSSProperties }) {
  return <div className={`skeleton ${className}`} style={{ minHeight: '1em', ...style }} />;
}
