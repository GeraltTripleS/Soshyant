/* Local check without Prisma: bun run src/local.ts, then open http://localhost:8787 */
import { handle } from "./site.ts";

const server = Bun.serve({ port: Number(process.env.PORT) || 8787, fetch: handle });
console.log(`Landing page on ${server.url}`);
