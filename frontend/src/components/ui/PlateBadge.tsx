import React from 'react';
import { cn } from '../../lib/cn';

interface PlateBadgeProps {
  plate?: string | null;
  confidence?: number | null;
  isCommercial?: boolean;
  isEv?: boolean;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const PlateBadge: React.FC<PlateBadgeProps> = ({
  plate,
  confidence,
  isCommercial = false,
  isEv = false,
  className,
  size = 'md',
}) => {
  if (!plate) {
    return (
      <div
        className={cn(
          'inline-flex items-center gap-1.5 px-2 py-0.5 rounded border border-dashed border-[var(--border-strong)] bg-[var(--surface-sunken)] text-[var(--text-muted)] font-mono text-xs',
          className
        )}
      >
        <span>No plate read</span>
      </div>
    );
  }

  // Visual color code for Indian license plates:
  // Private: Black on White
  // Commercial: Black on Yellow
  // EV: White on Green
  let plateStyle = 'bg-[var(--plate-private-bg)] text-[var(--plate-private-text)] border-[var(--plate-private-border)]';
  if (isCommercial) {
    plateStyle = 'bg-[var(--plate-commercial-bg)] text-[var(--plate-commercial-text)] border-[var(--plate-commercial-border)]';
  } else if (isEv) {
    plateStyle = 'bg-[var(--plate-ev-bg)] text-[var(--plate-ev-text)] border-[var(--plate-ev-border)]';
  }

  const sizeClasses = {
    sm: 'text-[11px] px-1.5 py-0.5 font-medium',
    md: 'text-[13px] px-2 py-0.5 font-semibold',
    lg: 'text-[16px] px-3 py-1 font-bold tracking-wider',
  }[size];

  return (
    <div className={cn('inline-flex items-center gap-1.5', className)}>
      <div
        className={cn(
          'font-mono uppercase rounded-[2px] border shadow-xs select-text tracking-wide',
          plateStyle,
          sizeClasses
        )}
      >
        {plate}
      </div>
      {confidence !== undefined && confidence !== null && (
        <span className="font-mono text-[11px] text-[var(--text-secondary)]">
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
    </div>
  );
};
