# Memory audit against the six-GB server budget

Request: check the original 6 GB RAM restriction for the entire server.
Date: 2026-10-25. No limits or host settings were modified during this audit.
Report is outside docs/agents/ because the user forbids editing docs/.

## What was measured

All five working Compose containers: FastAPI, Java backend, PostgreSQL, frontend
and pgAdmin. Initial docker stats working-set sum was approximately 1.45 GiB.
This excludes part of the file cache, so it is not the complete cgroup usage.

Measured memory.current, memory.peak, memory.swap.current, memory.max,
memory.swap.max and memory.events for each container. Twenty-five parallel
sampling rounds ran while the real working FastAPI process handled ten HTTP
rank-java requests: cold/warm 1, 10, 100 candidates, followed by four concurrent
requests with 100 distinct passages each. All ten returned 200, ranked all
candidates and recommended at most three. Synthetic requests changed no Java
application data. Backend health and frontend GET returned 200 afterward.

## Results

- Largest sampled sum of all five memory.current values: 2767511552 bytes,
  approximately 2.77 decimal GB / 2.58 GiB, including charged file caches.
- Sum of each container's historical memory.peak: 2806923264 bytes. These peaks
  are not simultaneous; counters cover the containers' lifetimes, including
  earlier startup and download work.
- FastAPI historical peak: 1773.54 MiB / approximately 1.73 GiB. Enforced memory
  cap is 2147483648 bytes (2 GiB). Docker stats after load: about 828 MiB excluding
  reclaimable inactive file cache.
- Other historical peaks: Java 395.85 MiB, PostgreSQL 145.78 MiB, pgAdmin
  338.06 MiB and frontend 23.66 MiB.
- Swap use: zero for every container. No OOM or OOM-kill events. FastAPI remains
  healthy. Current FastAPI memory+swap configuration allows 4 GiB total, although
  this run used no swap; it is not configured as a no-swap deployment.

## Limitations and conclusion

This is NOT a completed strict six-GB host acceptance test. Docker Engine currently
has 7912751104 bytes (7.37 GiB) available, and only FastAPI has an explicit container
memory cap. Java, PostgreSQL, pgAdmin and frontend are unlimited at the container
level. The measurements exclude host OS/Docker VM overhead and do not stress Java
or the database with concurrent full business journeys. Container image builds
were not part of the measured workload.

The measured application workload fits below 6 GB, with substantial observed
headroom, but no guarantee for a server restricted to 6 GB follows from this run.
Strict acceptance requires a genuinely constrained host/VM and representative
Java/database workload, or an explicitly budgeted deployment tested under its
limits. No global Docker/WSL memory settings were changed without a request.

Additional observation: cold 100-candidate requests took 3.63 s sequentially;
four simultaneous cold requests completed in 3.66–14.89 s because inference is
serialized. The last two exceed the Java client's current maximum 10 s timeout.
This is a latency/capacity concern for a worst-case burst, not a RAM failure.
No performance or timeout settings were changed during the memory audit.

## Evidence and Git

Raw report: work/ml-acceptance/stack-memory-six-gb-check.json.
Harness: work/ml-acceptance/verify_stack_memory.py and
memory_load_in_container.py (ignored local verification artifacts).
Commands: docker stats, docker info, docker inspect and cgroup reads via docker
exec; the load used actual HTTP against the existing uvicorn process, with the
API key read inside the container and never printed.

No production code, .env, secrets, model, threshold, docs or limits changed by this
audit. Previous uncommitted Docker cache fixes remain. No commit or push.
