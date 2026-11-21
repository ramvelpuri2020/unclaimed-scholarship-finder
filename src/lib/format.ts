import type { Program } from './types';
export const formatMoney = (value: number) => new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(value);
export const totalFound = (programs: Program[]) => programs.reduce((sum, item) => sum + (item.amountMax ?? 0), 0);
export const matchLabel = (confidence: number) => confidence >= .85 ? 'Strong match' : confidence >= .65 ? 'Likely' : 'Maybe';
export function daysUntil(date: string | null): number | null { if (!date) return null; return Math.floor((new Date(`${date}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()) / 86400000); }
export function deadlineText(program: Program): string { if (!program.deadline) return program.deadlineLabel || 'Rolling'; const n = daysUntil(program.deadline) ?? 0; return n === 0 ? 'Due today' : n === 1 ? 'Due tomorrow' : `Due in ${n} days`; }
export function relativeTime(value: string): string { const mins = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000)); if (mins < 1) return 'just now'; if (mins < 60) return `${mins} min ago`; const hours = Math.floor(mins / 60); if (hours < 24) return `${hours} hours ago`; return `${Math.floor(hours / 24)} days ago`; }
