# JobAgent

## Phase 0 status

This repository currently contains only the Phase 0 compatibility scaffold.
Product services, data stores, Agent behavior, and user interface flows have
not been implemented.

Batch01 established the readiness baseline. Batch02 locked Astryx core and CLI
at `0.1.4` and verified all 16 required public components. The ShopAIKey, PDF
extraction, and embedding compatibility gates are still pending.

## Repository layout

- `frontend/`: minimal frontend package scaffold; no UI flow exists.
- `backend/`: minimal Python package and evaluation scaffold; no service exists.
- `infrastructure/`: empty Docker, Neo4j, and script placeholders only.

## Local prerequisites

Check the tools used by Phase 0 with these single-purpose commands:

```powershell
python --version
node --version
npm --version
docker compose version
```

Run the focused Astryx compatibility gate from `frontend/` after installing the
exact lockfile:

```powershell
npm ci --ignore-scripts
npm run check:astryx
```

There is no application run or build command yet.

## Configuration and private inputs

`.env.example` documents the root configuration contract. Real credentials
belong only in the ignored root `.env`; nested frontend or backend `.env` files
are unsupported. Private evaluation inputs belong in the ignored
`backend/evaluation/**/local-private/` locations, while committed manifests
contain only generic identifiers and non-identifying metadata.
