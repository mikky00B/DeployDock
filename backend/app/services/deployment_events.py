"""In-process notification bus for deployment log activity.

The runner and the SSE stream live in the same process, so a stream can be woken
the instant a log line is written instead of polling the database every second
per open connection. Polling remains as a backstop (bounded by
`IDLE_POLL_SECONDS`) so a stream still makes progress if a notification is
missed, and so it keeps working if the runner is ever moved out of process.
"""

import asyncio
import uuid
from collections import defaultdict


class DeploymentEventBus:
    def __init__(self) -> None:
        self._waiters: dict[uuid.UUID, set[asyncio.Event]] = defaultdict(set)

    def notify(self, deployment_id: uuid.UUID) -> None:
        for event in self._waiters.get(deployment_id, set()):
            event.set()

    async def wait(self, deployment_id: uuid.UUID, timeout: float) -> bool:
        """Block until activity is reported, or the timeout elapses.

        Returns True when woken by a notification, False on timeout.
        """
        event = asyncio.Event()
        self._waiters[deployment_id].add(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False
        finally:
            waiters = self._waiters.get(deployment_id)
            if waiters is not None:
                waiters.discard(event)
                if not waiters:
                    self._waiters.pop(deployment_id, None)


deployment_event_bus = DeploymentEventBus()
