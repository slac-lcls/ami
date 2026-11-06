import itertools

import pytest

from ami.graph_nodes import PickN, RollingBuffer, SumN
from ami.graphkit_wrapper import Graph


@pytest.fixture(scope="function")
def pickN_graph():
    graph = Graph(name="graph")
    graph.add(PickN(name="cspad_pickN", N=9, inputs=["cspad"], outputs=["ncspads"]))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickn(pickN_graph):
    pickN_graph({"cspad": 1}, color="worker")
    worker1 = pickN_graph({"cspad": 2}, color="worker")
    pickN_graph({"cspad": 3}, color="worker")
    worker2 = pickN_graph({"cspad": 4}, color="worker")

    pickN_graph(worker1, color="localCollector")
    localCollector1 = pickN_graph(worker2, color="localCollector")

    # N=9 with 4 workers: the global collector must wait for at least 9 contributions.
    # Before the fix, the global N was rounded down to (9 // 4) * 4 = 8, so feeding the
    # 4-item localCollector1 batch twice (8 items) would have completed it here.
    globalCollector = pickN_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    globalCollector = pickN_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    # a third batch (12 items total) pushes the count past 9 and completes it.
    globalCollector = pickN_graph(localCollector1, color="globalCollector")

    assert worker1 == {"ncspads_worker": [1, 2]}
    assert worker2 == {"ncspads_worker": [3, 4]}

    assert localCollector1 == {"ncspads_localCollector": [1, 2, 3, 4]}
    assert len(globalCollector["ncspads"]) == 9
    assert set(globalCollector["ncspads"]) <= {1, 2, 3, 4}


@pytest.fixture(scope="function")
def pickMultiple_graph():
    graph = Graph(name="graph")
    graph.add(PickN(name="cspad_pickN", N=9, inputs=["cspad", "delta_t"], outputs=["ncspads"]))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickMultiple(pickMultiple_graph):
    pickMultiple_graph({"cspad": 1, "delta_t": 10}, color="worker")
    worker1 = pickMultiple_graph({"cspad": 2, "delta_t": 20}, color="worker")
    pickMultiple_graph({"cspad": 3, "delta_t": 30}, color="worker")
    worker2 = pickMultiple_graph({"cspad": 4, "delta_t": 40}, color="worker")

    pickMultiple_graph(worker1, color="localCollector")
    localCollector1 = pickMultiple_graph(worker2, color="localCollector")

    # N=9 with 4 workers: global collector needs >= 9 contributions (see test_pickn).
    globalCollector = pickMultiple_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    globalCollector = pickMultiple_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    globalCollector = pickMultiple_graph(localCollector1, color="globalCollector")

    assert worker1 == {"ncspads_worker": [(1, 10), (2, 20)]}
    assert worker2 == {"ncspads_worker": [(3, 30), (4, 40)]}

    assert localCollector1 == {"ncspads_localCollector": [(1, 10), (2, 20), (3, 30), (4, 40)]}
    assert len(globalCollector["ncspads"]) == 9
    assert set(globalCollector["ncspads"]) <= {(1, 10), (2, 20), (3, 30), (4, 40)}


@pytest.fixture(scope="function")
def pickList_graph():
    graph = Graph(name="graph")
    graph.add(PickN(name="cspad_pickN", N=9, inputs=["cspad"], outputs=["ncspads"]))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickList(pickList_graph):
    pickList_graph({"cspad": [1, 2]}, color="worker")
    worker1 = pickList_graph({"cspad": [3, 4]}, color="worker")
    pickList_graph({"cspad": [-1, -2]}, color="worker")
    worker2 = pickList_graph({"cspad": [-3, -4]}, color="worker")

    pickList_graph(worker1, color="localCollector")
    localCollector1 = pickList_graph(worker2, color="localCollector")

    # N=9 with 4 workers: global collector needs >= 9 contributions (see test_pickn).
    globalCollector = pickList_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    globalCollector = pickList_graph(localCollector1, color="globalCollector")
    assert not globalCollector["ncspads"]

    globalCollector = pickList_graph(localCollector1, color="globalCollector")

    assert worker1 == {"ncspads_worker": [[1, 2], [3, 4]]}
    assert worker2 == {"ncspads_worker": [[-1, -2], [-3, -4]]}

    assert localCollector1 == {"ncspads_localCollector": [[1, 2], [3, 4], [-1, -2], [-3, -4]]}
    expected_items = [[1, 2], [3, 4], [-1, -2], [-3, -4]]
    assert len(globalCollector["ncspads"]) == 9
    assert all(item in expected_items for item in globalCollector["ncspads"])


@pytest.fixture(scope="function")
def sumN_graph(request):
    N, nworkers, ncollectors, expected = request.param

    graph = Graph(name="graph")
    graph.add(SumN(name="cspad_sumN", N=N, inputs=["cspad"], outputs=["cspad_counts", "cspad_sum"]))
    graph.compile(num_workers=nworkers, num_local_collectors=ncollectors)
    return graph, expected


@pytest.mark.parametrize(
    "sumN_graph",
    [
        # N=9 with 4 workers/2 local collectors: the global collector's threshold is now
        # the user's N (9), not the pre-fix rounded-down value (9 // 4) * 4 = 8. Feeding
        # the localCollector's (4, 10) result twice only reaches count 8 < 9, so nothing
        # is emitted yet; a third feed reaches count 12 >= 9 and emits (12, 30). This case
        # uses the 5-tuple form (steps, (w1), (w2), (localCollector), (global)) since the
        # global result no longer follows the simple count3*2/sum3*2 relationship the
        # 4-tuple form assumes.
        (9, 4, 2, (2, (2, 3), (2, 7), (4, 10), (12, 30))),
        (8, 4, 2, (2, (2, 3), (2, 7))),
        (4, 4, 2, (1, (1, 1), (1, 2))),
        (12, 4, 2, (2, (None, None), (None, None))),
        (12, 4, 2, (3, (3, 6), (3, 15))),
        (4, 4, 2, (2, (1, 2), (1, 4))),
        (1, 4, 2, (2, (1, 2), (1, 4), (1, 4), (1, 4))),
        (4, 1, 1, (4, (4, 10), (4, 26), (4, 26), (4, 26))),
        (4, 1, 1, (2, (None, None), (None, None))),
    ],
    indirect=True,
)
def test_sumN(sumN_graph):
    sumN_graph, expected = sumN_graph
    try:
        steps, (count1, sum1), (count2, sum2) = expected
        if count1 is not None and count2 is not None:
            count3 = count1 + count2
        else:
            count3 = None
        if sum1 is not None and sum2 is not None:
            sum3 = sum1 + sum2
        else:
            sum3 = None
        if count3 is not None:
            count4 = count3 * 2
        else:
            count4 = None
        if sum3 is not None:
            sum4 = sum3 * 2
        else:
            sum4 = None
    except ValueError:
        steps, (count1, sum1), (count2, sum2), (count3, sum3), (count4, sum4) = expected

    start = 1
    stop = start + steps
    for i in range(start, stop):
        worker1 = sumN_graph({"cspad": i}, color="worker")
    sumN_graph.reset()
    start = stop
    stop = start + steps
    for i in range(start, stop):
        worker2 = sumN_graph({"cspad": i}, color="worker")

    sumN_graph(worker1, color="localCollector")
    localCollector = sumN_graph(worker2, color="localCollector")

    # Since the fix (active/01-global-n-is-user-n.md in global-op-n-splitting/), the
    # global collector's threshold is the user's N, not a rounded-down value, so it may
    # need more than 2 contributions from localCollector to complete (e.g. N=9 with 4
    # workers needs 3 feeds of a 4-item localCollector result to reach 12 >= 9). Keep
    # feeding until it completes (matching the old fixed-2-feeds behavior for cases where
    # 2 feeds is already enough), or stop after 2 feeds for cases that should never
    # complete.
    if count4 is not None:
        for _ in range(10):
            globalCollector = sumN_graph(localCollector, color="globalCollector")
            if globalCollector.get("cspad_counts") is not None:
                break
    else:
        sumN_graph(localCollector, color="globalCollector")
        globalCollector = sumN_graph(localCollector, color="globalCollector")

    if count1 is not None and sum1 is not None:
        assert worker1 == {"cspad_counts_worker": count1, "cspad_sum_worker": sum1}
    else:
        assert not worker1

    if count2 is not None and sum2 is not None:
        assert worker2 == {"cspad_counts_worker": count2, "cspad_sum_worker": sum2}
    else:
        assert not worker2

    if count3 is not None and sum3 is not None:
        assert localCollector == {"cspad_counts_localCollector": count3, "cspad_sum_localCollector": sum3}
    else:
        assert not localCollector

    if count4 is not None and sum4 is not None:
        assert globalCollector == {"cspad_counts": count4, "cspad_sum": sum4}
    else:
        assert not globalCollector


@pytest.fixture(scope="function")
def rollingBuffer_graph(request):
    N, nworkers, ncollectors, expected = request.param

    graph = Graph(name="graph")
    graph.add(RollingBuffer(name="cspad_rollingBuffer", N=N, inputs=["cspad"], outputs=["count", "ncspads"]))
    graph.compile(num_workers=nworkers, num_local_collectors=ncollectors)
    return graph, expected


@pytest.mark.parametrize(
    "rollingBuffer_graph",
    [
        (9, 4, 2, (2, [1, 2], [3, 4])),
        (8, 4, 2, (2, [1, 2], [3, 4])),
        (4, 4, 2, (1, [1], [2])),
        (12, 4, 2, (2, [1, 2], [3, 4])),
        (12, 4, 2, (3, [1, 2, 3], [4, 5, 6])),
        (4, 4, 2, (2, [2], [4])),
        (1, 4, 2, (2, [2], [4], [4], [4])),
        (4, 1, 1, (4, [1, 2, 3, 4], [5, 6, 7, 8], [5, 6, 7, 8], [5, 6, 7, 8])),
        (4, 1, 1, (2, [1, 2], [3, 4], [1, 2, 3, 4], [1, 2, 3, 4])),
    ],
    indirect=True,
)
def test_rollingBuffer(rollingBuffer_graph):
    rollingBuffer_graph, expected = rollingBuffer_graph
    try:
        steps, expected1, expected2 = expected
        expected3 = expected1 + expected2
        expected4 = expected3 * 2
    except ValueError:
        steps, expected1, expected2, expected3, expected4 = expected

    start = 1
    stop = start + steps
    for i in range(start, stop):
        worker1 = rollingBuffer_graph({"cspad": i}, color="worker")
    rollingBuffer_graph.reset()
    start = stop
    stop = start + steps
    for i in range(start, stop):
        worker2 = rollingBuffer_graph({"cspad": i}, color="worker")

    rollingBuffer_graph(worker1, color="localCollector")
    localCollector = rollingBuffer_graph(worker2, color="localCollector")

    rollingBuffer_graph(localCollector, color="globalCollector")
    globalCollector = rollingBuffer_graph(localCollector, color="globalCollector")

    assert worker1 == {"count_worker": steps, "ncspads_worker": expected1}
    assert worker2 == {"count_worker": steps, "ncspads_worker": expected2}

    assert localCollector == {"count_localCollector": 2 * steps, "ncspads_localCollector": expected3}
    assert globalCollector == {"count": 4 * steps, "ncspads": expected4}


def _ok(result):
    """Drop keys whose value is None (mirrors how the real Store ignores None updates)."""
    return {k: v for k, v in (result or {}).items() if v is not None}


def _run_global_op_minimum(
    cls, N, num_workers, num_local_collectors, events_per_worker, num_heartbeats, outputs=("c", "v"), **extra
):
    """
    Simulates `num_heartbeats` heartbeats of a global operation (SumN/PickN/RollingBuffer)
    expanded across `num_workers` workers and `num_local_collectors` local collectors,
    each worker receiving `events_per_worker` events per heartbeat. Each worker gets a
    distinct graph instance (as in the real deployment, where each worker/local
    collector/global collector is a separate process with its own compiled graph).

    `outputs` must match the node type's real output arity: SumN and RollingBuffer each
    return a `(count, value)` tuple and need 2 output names; PickN returns a single value
    (a list, or a scalar when N==1) and needs exactly 1 output name.

    Returns the list of global-collector outputs that were emitted (i.e. where the global
    collector's node completed), across all heartbeats, in emission order.
    """

    def make(name):
        g = Graph(name="g")
        g.add(cls(name=name, N=N, inputs=["x"], outputs=list(outputs), **extra))
        g.compile(num_workers=num_workers, num_local_collectors=num_local_collectors)
        return g

    workers_per_local = num_workers // num_local_collectors
    workers = [make("s") for _ in range(num_workers)]
    locals_ = [make("s") for _ in range(num_local_collectors)]
    glob = make("s")

    emitted = []
    value_counter = itertools.count(1)
    for _hb in range(num_heartbeats):
        local_results = []
        for li in range(num_local_collectors):
            for wi in range(workers_per_local):
                worker = workers[li * workers_per_local + wi]
                worker_out = {}
                for _e in range(events_per_worker):
                    r = _ok(worker({"x": next(value_counter)}, color="worker"))
                    if r:
                        worker_out = r
                if worker_out:
                    r = _ok(locals_[li](worker_out, color="localCollector"))
                    if r:
                        local_results.append(r)
        for w in workers:
            w.heartbeat_finished()
        for lc in locals_:
            lc.heartbeat_finished()
        for r in local_results:
            g = _ok(glob(r, color="globalCollector"))
            if g:
                emitted.append(g)
        glob.heartbeat_finished()

    return emitted


# (N, num_workers) pairs covering every qualitative case for the fix in
# `global-op-n-splitting/active/01-global-n-is-user-n.md` (the arithmetic is linear, so
# one representative per case is enough -- no need to sweep many N values):
#   - N divisible by num_workers: old (floored) and new (exact) N agree -- sanity, no
#     regression expected.
#   - N not divisible by num_workers, with 2+ local collectors: the bug case -- old code
#     floored N down, new code keeps the user's N exactly.
#   - N < num_workers: floors to 0 pre-fix (then clamped to 1) -- the RollingBuffer/PickN
#     collapse case.
#   - N == 1 and num_workers == 1: trivial edges, both should always equal 1/N regardless.
#   - the real MFX 2x7/2x8 layout (14/16 workers), the case that motivated this fix.
_N_STRUCTURAL_CASES = [
    (8, 4),  # divisible: no change expected
    (9, 4),  # the classic bug case (used throughout the tests above)
    (5, 4),  # N < num_workers: floors to 1 pre-fix
    (1, 4),  # N == 1 edge case
    (4, 1),  # num_workers == 1 edge case
    (10, 16),  # real MFX 2x8 layout
    (10, 14),  # real MFX 2x7 layout
]


@pytest.mark.parametrize("N,num_workers", _N_STRUCTURAL_CASES)
def test_global_collector_N_is_user_N(N, num_workers):
    """
    Direct regression test for `global-op-n-splitting/active/01-global-n-is-user-n.md`:
    the compiled global collector's `N` must equal the user's `N` exactly, not
    `(N // num_workers) * num_workers`. Checks the compiled graph structure directly, with
    no heartbeat simulation -- cheap, and pinpoints the arithmetic itself rather than one
    of its downstream symptoms.

    Loops over all three affected node types (SumN/PickN/RollingBuffer) within a single
    test case instead of parametrizing on node type separately: the fix is one shared line
    in `Graph._expand_global_operations`, not per-node-type logic, so a regression here
    would affect all three identically for a given (N, num_workers) -- there's no failure
    mode where this breaks one type but not the others for the same case. Each assertion
    names the failing type so `pytest -v` output still identifies it precisely.
    """
    for cls in (SumN, PickN, RollingBuffer):
        outputs = ["v"] if cls is PickN else ["c", "v"]
        g = Graph(name="g")
        g.add(cls(name="s", N=N, inputs=["x"], outputs=outputs))
        g.compile(num_workers=num_workers, num_local_collectors=min(2, num_workers))

        global_collector_nodes = [n for n in g.graph.nodes if getattr(n, "color", None) == "globalCollector"]
        assert len(global_collector_nodes) == 1, f"{cls.__name__}: expected exactly 1 global collector node"
        assert global_collector_nodes[0].N == N, (
            f"{cls.__name__}: global collector N was {global_collector_nodes[0].N}, expected the user's N={N} "
            f"(num_workers={num_workers})"
        )


# A small curated set of (N, num_workers, num_local_collectors, events_per_worker) cases
# for the end-to-end (heartbeat-simulating) test below, covering: the classic bug case,
# the N < num_workers collapse case, the real MFX 2x8 layout, and a single-local-collector
# sanity/no-regression case (where the bug can't manifest at the global tier at all, since
# the local collector's own N already enforces the minimum). See
# `test_global_collector_N_is_user_N` above for direct coverage of the underlying
# arithmetic across more (N, num_workers) pairs, including the MFX 2x7 layout.
_N_MINIMUM_CASES = [
    (9, 4, 2, 1),
    (2, 4, 2, 1),
    (10, 16, 2, 1),
    (1, 4, 1, 1),
]


def _enough_heartbeats(N, num_workers, events_per_worker, margin=5):
    """
    Enough heartbeats for at least one emission to be possible. A naive
    ceil(N / (num_workers * events_per_worker)) undercounts because contributions can
    straddle heartbeats unevenly (a local/global collector may need to accumulate several
    heartbeats' worth of events before its own threshold is reached -- see
    `.opencode/plans/global-op-n-splitting/research/n-splitting-analysis-2026-11-05.md`).
    Empirically, 3x the naive estimate plus a margin covers every case in
    `_N_MINIMUM_CASES` (verified against the real expansion code, not just this formula).
    """
    events_per_heartbeat = max(num_workers * events_per_worker, 1)
    naive = -(-N // events_per_heartbeat)  # ceil(N / events_per_heartbeat)
    return 3 * naive + margin


@pytest.mark.parametrize("N,num_workers,num_local_collectors,events_per_worker", _N_MINIMUM_CASES)
def test_global_minimum_n_respected(N, num_workers, num_local_collectors, events_per_worker):
    """
    End-to-end regression test for `global-op-n-splitting/active/01-global-n-is-user-n.md`,
    covering all three affected node types in one test case (see
    `test_global_collector_N_is_user_N` for why combining is appropriate here). Runs the
    full worker -> local collector -> global collector pipeline (via
    `_run_global_op_minimum`) separately for each type and checks its specific invariant:
    - SumN: the global collector's displayed count is always >= N (never rounded down).
    - PickN: every emission has exactly N items (the ring buffer is never undersized).
    - RollingBuffer: the steady-state (last-emitted) buffer length is exactly N (not
      collapsed, as happened before the fix for e.g. N=10 at num_workers=16).
    """
    num_heartbeats = _enough_heartbeats(N, num_workers, events_per_worker, margin=10)

    sumN_emitted = _run_global_op_minimum(SumN, N, num_workers, num_local_collectors, events_per_worker, num_heartbeats)
    assert sumN_emitted, f"SumN: expected at least one emission within {num_heartbeats} heartbeats"
    for result in sumN_emitted:
        assert result["c"] >= N, (
            f"SumN displayed only {result['c']} contributions, fewer than the requested N={N} "
            f"(num_workers={num_workers}, num_local_collectors={num_local_collectors}, "
            f"events_per_worker={events_per_worker})"
        )

    pickn_emitted = _run_global_op_minimum(
        PickN, N, num_workers, num_local_collectors, events_per_worker, num_heartbeats, outputs=("v",)
    )
    assert pickn_emitted, f"PickN: expected at least one emission within {num_heartbeats} heartbeats"
    for result in pickn_emitted:
        # PickN returns a bare scalar (not a 1-element list) when N == 1.
        items = result["v"] if N > 1 else [result["v"]]
        assert len(items) == N, (
            f"PickN emitted {len(items)} items, expected exactly N={N} "
            f"(num_workers={num_workers}, num_local_collectors={num_local_collectors}, "
            f"events_per_worker={events_per_worker})"
        )

    rolling_emitted = _run_global_op_minimum(
        RollingBuffer, N, num_workers, num_local_collectors, events_per_worker, num_heartbeats
    )
    assert rolling_emitted, f"RollingBuffer: expected at least one emission within {num_heartbeats} heartbeats"
    # only check steady state (the last emission) -- the buffer fills up over the first
    # few heartbeats before reaching length N.
    last = rolling_emitted[-1]
    assert len(last["v"]) == N, (
        f"RollingBuffer displayed a buffer of length {len(last['v'])}, expected exactly N={N} "
        f"(num_workers={num_workers}, num_local_collectors={num_local_collectors}, "
        f"events_per_worker={events_per_worker})"
    )
