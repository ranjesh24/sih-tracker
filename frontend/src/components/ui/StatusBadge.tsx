import React from 'react';
import { Check, CircleDot, AlertTriangle, XCircle, PowerOff } from 'lucide-react';
import { cn } from '../../lib/cn';

export type StatusType = 'confirmed' | 'probable' | 'ambiguous' | 'rejected' | 'offline';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, className }) => {
  const configs = {
    confirmed: {
      defaultLabel: 'Confirmed',
      icon: Check,
      bg: 'bg-[var(--status-confirmed-tint)]',
      text: 'text-[var(--accent-text)]',
      border: 'border-[var(--status-confirmed)]/30',
    },
    probable: {
      defaultLabel: 'Probable',
      icon: CircleDot,
      bg: 'bg-[var(--status-probable-tint)]',
      text: 'text-[var(--text-secondary)]',
      border: 'border-[var(--status-probable)]/30',
    },
    ambiguous: {
      defaultLabel: 'Ambiguous',
      icon: AlertTriangle,
      bg: 'bg-[var(--status-ambiguous-tint)]',
      text: 'text-[var(--status-ambiguous)]',
      border: 'border-[var(--status-ambiguous)]/30',
    },
    rejected: {
      defaultLabel: 'Rejected',
      icon: XCircle,
      bg: 'bg-[var(--status-rejected-tint)]',
      text: 'text-[var(--status-rejected)]',
      border: 'border-[var(--status-rejected)]/30',
    },
    offline: {
      defaultLabel: 'Offline',
      icon: PowerOff,
      bg: 'bg-[var(--status-offline-tint)]',
      text: 'text-[var(--status-offline)]',
      border: 'border-[var(--status-offline)]/30',
    },
  }[status];

  const IconComponent = configs.icon;
  const displayLabel = label || configs.defaultLabel;

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 h-5 px-1.5 rounded-[var(--radius-sm)] border text-[11px] font-medium select-none',
        configs.bg,
        configs.text,
        configs.border,
        className
      )}
    >
      <IconComponent className="w-3 h-3 shrink-0" />
      <span>{displayLabel}</span>
    </div>
  );
};
