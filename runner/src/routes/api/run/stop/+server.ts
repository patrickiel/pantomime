import { error, json } from '@sveltejs/kit';
import { stopRun } from '$lib/server/runner';
import type { RequestHandler } from './$types';

/** Stop a running test. Body: `{ testId: string }`. */
export const POST: RequestHandler = async ({ request }) => {
	const body = (await request.json().catch(() => ({}))) as { testId?: string };
	if (!body.testId) throw error(400, 'testId is required');
	return json({ stopped: stopRun(body.testId) });
};
