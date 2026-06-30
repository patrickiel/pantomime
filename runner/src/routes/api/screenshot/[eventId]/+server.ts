import { error } from '@sveltejs/kit';
import { eq } from 'drizzle-orm';
import { getDb } from '$lib/server/db';
import { events } from '$lib/server/schema';
import { currentProject } from '$lib/server/project';
import type { RequestHandler } from './$types';

/** Serve a single event's redacted PNG screenshot straight from the SQLite blob. */
export const GET: RequestHandler = async (event) => {
	const id = Number(event.params.eventId);
	if (!Number.isInteger(id)) throw error(400, 'bad event id');

	const db = getDb(currentProject().db);
	const row = db.select({ shot: events.screenshot }).from(events).where(eq(events.id, id)).get();
	const shot = row?.shot;
	if (!shot) throw error(404, 'no screenshot for this event');

	const bytes = shot as Buffer;
	return new Response(new Uint8Array(bytes), {
		headers: {
			'content-type': 'image/png',
			'cache-control': 'public, max-age=31536000, immutable'
		}
	});
};
