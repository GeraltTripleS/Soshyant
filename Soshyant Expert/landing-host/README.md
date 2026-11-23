# Landing page hosting (Prisma Compute)

This folder puts `../landing` online with Prisma Compute. Prisma Compute runs a small Bun server, not plain files, so `src/site.ts` serves the four landing files from memory. The build inlines them into one file, `dist/server.mjs`.

The server adds:

- versioned CSS/JS URLs, cached for a year and replaced on every deploy;
- gzip and ETags;
- a Content-Security-Policy that allows only the page's own two inline scripts, by hash (recomputed at build, so editing `window.SOSHYANT` in `index.html` is fine);
- `/robots.txt`, `/healthz` and a 404 page.

Live now: https://soshyantexpert.site and https://www.soshyantexpert.site (also https://h4u0zo298eudufy2m89ynatd.cdg.prisma.build). Project `soshyant-landing`, service `web`, branch `main` (production), Paris (`eu-west-3`). DNS is on Cloudflare (`lilyana`/`max.ns.cloudflare.com`, both records DNS only); the domain is registered at Hostida.

## Requirements

- Bun (`%USERPROFILE%\.bun\bin\bun.exe`). The scripts run the Prisma CLI under Bun, because the CLI needs Node 22.18+ and this computer has 22.17.1.
- Internet access to npmjs.org and prisma.io. On this computer that works only with the VPN on.

## Check locally

```
bun run src/local.ts
```

Open http://localhost:8787.

## Deploy

Run these from this folder:

```
bun run setup
bun --bun x prisma auth login
bun run deploy
```

- `bun run setup` installs the packages from `bun.lock`. Don't use `npm install`, which fails here with an npm resolver bug.
- `prisma auth login` opens the browser. Sign in with your Prisma account. The session lasts about an hour.
- `bun run deploy` builds, deploys and prints the live address.

To publish a change to the page, run `bun run deploy` again.

## Domain

Custom domains attach to the production service `web`. Domain commands need `--project soshyant-landing --branch main`; without them, Prisma reports that the service doesn't exist. The CNAME target is `switchboard.cdg.prisma.build`.

The name servers must answer DNS worldwide. Hostida's default name servers (`ns101`/`ns102.hostidadns.com`) don't answer from outside Iran, which is why the domain's DNS is on Cloudflare.

1. At the DNS provider, add both records, each with the value `switchboard.cdg.prisma.build`:
   - a `CNAME` for `www`;
   - for the bare domain (`@`), a CNAME with flattening, or an ALIAS record. Cloudflare flattens a CNAME on `@` automatically. If you use Cloudflare, set both records to "DNS only" (grey cloud): Prisma issues the certificate itself.
2. Register both names:

   ```
   bun --bun x prisma service domain add www.soshyantexpert.site --service web --project soshyant-landing --branch main
   bun --bun x prisma service domain add soshyantexpert.site --service web --project soshyant-landing --branch main
   ```

3. Wait for TLS:

   ```
   bun --bun x prisma service domain wait www.soshyantexpert.site --service web --project soshyant-landing --branch main
   ```

Prisma allows up to 3 custom domains per app.

To see the state of a domain or retry a stuck one:

```
bun --bun x prisma service domain show <host> --service web --project soshyant-landing --branch main
bun --bun x prisma service domain retry <host> --service web --project soshyant-landing --branch main
```
