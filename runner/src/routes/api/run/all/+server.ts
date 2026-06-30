import { json } from '@sveltejs/kit';
import { listTests } from '$lib/server/tests';
import { currentProject } from '$lib/server/project';
import { enqueueRuns, clearQueue } from '$lib/server/runner';
import type { RequestHandler } from './$types';

/**
 * Queue every runnable test to run one after another. Single-flight means they
 * can't run in parallel, so the runner drains the queue as each child exits.
 * Body: `{ dryRun?: boolean }`.
 */
export const POST: RequestHandler = async ({ request }) => {
	const body = (await request.json().catch(() => ({}))) as { dryRun?: boolean };
	const project = currentProject();

	// `window` comes from the trusted YAML, never the client (mirrors /api/run).
	const items = listTests(project.root)
		.filter((t) => !t.parseError)
		.map((t) => ({
			testId: t.id,
			relPath: t.relPath,
			window: t.window,
			dryRun: !!body.dryRun,
			root: project.root,
			db: project.db
		}));

	enqueueRuns(items);
	return json({ ok: true, queued: items.length });
};

/** Cancel the batch: drop every still-pending test. The in-flight run keeps going. */
export const DELETE: RequestHandler = async () => {
	return json({ cleared: clearQueue() });
};
