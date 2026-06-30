/** Presentation helpers for phases, statuses, and timestamps. */

export const PHASE_META: Record<string, { label: string; color: string }> = {
	goal: { label: 'Goal', color: 'text-goal border-goal/40 bg-goal/10' },
	sense: { label: 'Sense', color: 'text-info border-info/40 bg-info/10' },
	plan: { label: 'Plan', color: 'text-warning border-warning/40 bg-warning/10' },
	act: { label: 'Act', color: 'text-primary border-primary/40 bg-primary/10' },
	verify: { label: 'Verify', color: 'text-verify border-verify/40 bg-verify/10' },
	info: { label: 'Info', color: 'text-muted border-subtle/40 bg-subtle/10' }
};

export function phaseMeta(phase: string) {
	return PHASE_META[phase] ?? PHASE_META.info;
}

/** Solid fill classes for the duration bar, one per phase (text color reused for legend swatches). */
export const PHASE_FILL: Record<string, string> = {
	goal: 'bg-goal',
	sense: 'bg-info',
	plan: 'bg-warning',
	act: 'bg-primary',
	verify: 'bg-verify',
	info: 'bg-subtle'
};

export function phaseFill(phase: string): string {
	return PHASE_FILL[phase] ?? PHASE_FILL.info;
}

export function statusColor(status: string): string {
	if (status === 'passed') return 'text-primary bg-primary/15 border-primary/40';
	if (status === 'failed') return 'text-danger bg-danger/15 border-danger/40';
	if (status === 'running') return 'text-info bg-info/15 border-info/40 animate-pulse';
	if (status === 'canceled') return 'text-warning bg-warning/15 border-warning/40';
	if (status === 'queued') return 'text-info bg-info/10 border-info/30';
	if (status === 'never-run') return 'text-muted bg-subtle/10 border-border-strong/40';
	return 'text-muted bg-subtle/15 border-subtle/40';
}

/** Small-pill color classes, keyed by tone. Mirrors statusColor() for the bordered badges. */
export const BADGE_TONE: Record<string, string> = {
	primary: 'bg-primary/15 text-primary',
	danger: 'bg-danger/15 text-danger',
	warning: 'bg-warning/10 text-warning',
	muted: 'bg-elevated/50 text-muted'
};

export function badgeTone(tone: string): string {
	return BADGE_TONE[tone] ?? BADGE_TONE.muted;
}

export function statusLabel(status: string): string {
	if (status === 'never-run') return 'not run';
	return status;
}

export function fmtTime(ms: number | null): string {
	if (!ms) return '';
	return new Date(ms).toLocaleString();
}

export function fmtClock(ms: number | null): string {
	if (!ms) return '';
	return new Date(ms).toLocaleTimeString([], { hour12: false }) + '.' + String(ms % 1000).padStart(3, '0');
}

export function fmtDuration(s: number | null): string {
	if (s == null) return '';
	if (s < 60) return `${s.toFixed(1)}s`;
	const m = Math.floor(s / 60);
	return `${m}m ${(s % 60).toFixed(0)}s`;
}

/** Step duration from a millisecond gap: 0ms, 840ms, 2.3s, 1m 5s. */
export function fmtMs(ms: number | null): string {
	if (ms == null) return '';
	if (ms < 1000) return `${Math.round(ms)}ms`;
	const s = ms / 1000;
	if (s < 60) return `${s.toFixed(1)}s`;
	const m = Math.floor(s / 60);
	return `${m}m ${(s % 60).toFixed(0)}s`;
}

/** Compact token count: 0, 842, 12.3k, 1.20M. */
export function fmtTokens(n: number | null | undefined): string {
	if (!n) return '0';
	if (n < 1000) return String(n);
	if (n < 1_000_000) return (n / 1000).toFixed(n < 10_000 ? 1 : 0) + 'k';
	return (n / 1_000_000).toFixed(2) + 'M';
}

/** Cost in cents from a USD amount: 0¢, <0.1¢, 2.9¢, 42¢. */
export function fmtCost(usd: number | null | undefined): string {
	if (!usd) return '0¢';
	const c = usd * 100;
	if (c < 0.1) return '<0.1¢';
	if (c < 10) return c.toFixed(1) + '¢';
	return Math.round(c) + '¢';
}
