"""Only so many generations may be at the provider at once.

There was no cap. start_job spawns an unbounded OS thread per click and
_parallel adds up to BUILD_CONCURRENCY more for a guided build, so six could be
in flight together. That does not finish them sooner — kie serialises at its
end and every one waits. Measured on a real outfit with six running: 509s wall
clock against kie's own render time of 76.8s, with the job stream sitting at
"generating (waiting)", which is kie reporting the task QUEUED.

Moving the queue here changes nothing about throughput and everything about
feedback: a waiting job can say it is waiting. A job blocked on a silent
semaphore looks exactly like a hung one, which is the failure mode this project
keeps rediscovering.
"""
from __future__ import annotations

import threading
import time

from backend import generate as G


def test_cap_is_enforced():
    peak = cur = 0
    lock = threading.Lock()

    def work():
        nonlocal peak, cur
        with G._slot(None):                                  # noqa: SLF001
            with lock:
                cur += 1
                peak = max(peak, cur)
            time.sleep(0.05)
            with lock:
                cur -= 1

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak <= G.GEN_CONCURRENCY, f"{peak} ran at once, cap is {G.GEN_CONCURRENCY}"


def test_a_waiting_job_says_so():
    """The whole point. A silent queue is indistinguishable from a hang."""
    seen = []
    hold = threading.Event()

    def blocker():
        with G._slot(None):                                  # noqa: SLF001
            hold.wait(2)

    blockers = [threading.Thread(target=blocker) for _ in range(G.GEN_CONCURRENCY)]
    [t.start() for t in blockers]
    time.sleep(0.1)                                          # let them take the slots

    def waiter():
        prog = {}
        with G._slot(prog):                                  # noqa: SLF001
            seen.append(prog.get("stage"))

    w = threading.Thread(target=waiter)
    w.start()
    time.sleep(0.1)
    hold.set()
    w.join(3)
    [t.join(3) for t in blockers]

    assert seen and seen[0] and "queued" in seen[0], (
        f"a queued job reported {seen!r} instead of saying it was queued")


def test_the_slot_is_released_when_the_provider_raises():
    """A provider that throws must not leak its slot, or the cap becomes a
    deadlock after N failures — strictly worse than having no cap."""
    for _ in range(G.GEN_CONCURRENCY + 2):
        try:
            with G._slot(None):                              # noqa: SLF001
                raise RuntimeError("provider refused")
        except RuntimeError:
            pass
    got = G._GEN_SLOTS.acquire(blocking=False)               # noqa: SLF001
    assert got, "slots leaked on the error path — the cap would deadlock"
    G._GEN_SLOTS.release()                                   # noqa: SLF001
