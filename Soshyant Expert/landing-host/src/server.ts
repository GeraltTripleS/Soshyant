/* Entry point on Prisma Compute: the port comes from Composer and the server binds 0.0.0.0. */
import service from "./service.ts";
import { handle } from "./site.ts";

Bun.serve({ port: service.port(), hostname: "0.0.0.0", fetch: handle });
