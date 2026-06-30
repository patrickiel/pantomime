import { error, json } from '@sveltejs/kit';
import { listTests } from '$lib/server/tests';
import { currentProject } from '$lib/server/project';
import { anyRunning, startRun } from '$lib/server/runner';
import type { RequestHandler } from './$types';

/** Launch a test run. Body: `{ testId: string, dryRun?: boolean }`. */
export const POST: RequestHandler = async (event) => {
	const body = (await event.request.json().catch(() => ({}))) as { testId?: string; dryRun?: boolean };
	if (!body.testId) throw error(400, 'testId is required');

	const project = currentProject();

	const meta = listTests(project.root).find((t) => t.id === body.testId);
	if (!meta) throw error(404, `Unknown test: ${body.testId}`);
	if (meta.parseError) throw error(400, `Test cannot be run: ${meta.parseError}`);
	if (anyRunning()) throw error(409, 'A test run is already in progress.');

	try {
		// `window` comes from the trusted YAML, never the client.
		const run = startRun({
			testId: meta.id,
			relPath: meta.relPath,
			window: meta.window,
			dryRun: !!body.dryRun,
			root: project.root,
			db: project.db
		});
		return json({ ok: true, run });
	} catch (e) {
		throw error(409, e instanceof Error ? e.message : String(e));
	}
};
