import { resolve } from 'node:path';
import { defineConfig } from 'drizzle-kit';

export default defineConfig({
	schema: './src/lib/server/schema.ts',
	dialect: 'sqlite',
	dbCredentials: {
		url: process.env.PANTO_DB ?? resolve(process.cwd(), '..', 'runs', 'pantomime.db')
	}
});
