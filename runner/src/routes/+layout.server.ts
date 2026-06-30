import { currentProject } from '$lib/server/project';
import type { LayoutServerLoad } from './$types';

/** The project this runner instance is scoped to — shown in the header. */
export const load: LayoutServerLoad = async () => {
	return { projectName: currentProject().name };
};
