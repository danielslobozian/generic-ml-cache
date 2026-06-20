<div align="center">

# Asynchronous Executions

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Synchronous execution](#synchronous-execution)
- [Asynchronous execution](#asynchronous-execution)
- [Conceptual commands](#conceptual-commands)
- [Generated files in async mode](#generated-files-in-async-mode)
- [Event logs](#event-logs)

---

Asynchronous execution is a delivery mode for the same execution model.

It is not the daemon itself. A daemon can later expose the same model through a
resident transport.

## Synchronous execution

In synchronous mode:

```text
submit request
  -> execute or replay
  -> return stdout/stderr/exit
  -> materialize files immediately when applicable
```

The caller waits for the result.

## Asynchronous execution

In asynchronous mode:

```text
submit request
  -> receive execution id
  -> query status
  -> watch or replay events
  -> fetch result
  -> materialize generated files explicitly
```

The launch command exits after returning an execution ID.

## Conceptual commands

The exact CLI may change, but the conceptual operations are:

```text
gmlcache run --detach ...
  returns execution_id

gmlcache execution status <execution_id>
  shows queued/running/succeeded/failed/timed-out

gmlcache execution watch <execution_id>
  streams or replays execution events

gmlcache execution result <execution_id>
  returns final stdout/stderr/exit/files metadata

gmlcache execution materialize <execution_id> --output-dir <path>
  writes generated files explicitly
```

For sessions:

```text
gmlcache session watch <session_id>
  streams or replays events for all executions in the session
```

## Generated files in async mode

Detached async runs should not silently write generated files into the caller’s
folder after the launching process has exited.

The files should remain captured as execution result data until the caller
explicitly materializes them.

This avoids surprising late writes and makes async behavior predictable.

## Event logs

A watch operation should work even after an execution has finished by replaying
the persisted event log. Live subscription and historical replay are two views of
the same execution events.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
