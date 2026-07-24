# CV profile and multi-conversation destructive rollout

This release intentionally resets all pre-0005 application data. Legacy SQLite
rows, retained CV files, Saved Jobs, evaluations, interrupted checkpoints, and
Neo4j data are discarded. There is no legacy-data backfill. Export anything
that must be retained before running this procedure.

## Preconditions

- Run from the repository root with Docker Engine and Compose available.
- Use the disposable project name below; do not substitute a production project.
- Confirm `.env` exists locally without printing it or copying its values into logs.
- Close other JobAgent Compose projects that publish ports 5173, 7474, 7687, or 8000.
- Record the operator, date, branch SHA, and backup decision in the acceptance checklist.

## Disposable reset and smoke

Set the disposable project name:

```powershell
$project = 'jobagent-cv-profile-reset-smoke'
```

> **DATA-LOSS WARNING:** The next command permanently deletes this Compose
> project's SQLite/files and Neo4j volumes. Verify `$project` exactly before running it.

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project down -v --remove-orphans
```

The next command creates fresh disposable volumes and starts the three services:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project up --build -d --wait --wait-timeout 180
```

Verify the public health projection without printing configuration or secrets:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Rebuild only the derived JobAgent graph projection from authoritative fresh SQLite:

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project exec -T backend python -m app.graph.rebuild
```

Run the sanitized browser acceptance matrix in
`docs/acceptance/cv-profile-multi-conversation-checklist.md` while the disposable
stack is running. Do not record CV text, prompts, credentials, provider payloads,
filesystem paths, or raw database contents.

> **DATA-LOSS WARNING:** The final command permanently deletes all disposable
> smoke data and volumes. Verify the acceptance evidence is saved first.

```powershell
docker compose --env-file .env -f infrastructure/docker-compose.yml -p $project down -v --remove-orphans
```

## Required reset evidence

Before creating smoke data, record all of the following in the checklist:

- Alembic head is `0005_cv_profiles_multi_conversation`.
- `profiles`, `conversations`, and `job_posts` each contain zero rows.
- the retained-files directory contains no file from a prior volume;
- Neo4j contains only static seed data before the explicit rebuild/smoke flow;
- Compose resolves exactly `neo4j`, `backend`, and `frontend`;
- backend startup runs `alembic upgrade head` before Uvicorn and does not run
  provider extraction or SQLAlchemy `create_all`.

## Failure handling

- If startup or migration fails, capture only the failing command, exit code, and
  safe error summary. Do not dump environment variables or complete container logs.
- If the browser matrix fails, retain the disposable project only long enough to
  capture sanitized routes/statuses and screenshots, then run the final warned cleanup.
- Restore legacy data only into a separate checkout/Compose project from an
  operator-created backup. This release does not support in-place rollback.
