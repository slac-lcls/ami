import pytest
import zmq
import multiprocessing as mp

from ami.sync import run_syncer


@pytest.fixture(scope='function')
def sync_proc(request, ipc_dir):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    interval = 10
    addr = "ipc://%s/sync" % ipc_dir
    comm_addr = "ipc://%s/sync-comm" % ipc_dir
    if isinstance(request.param, tuple):
        nclients, start = request.param
    else:
        nclients = request.param
        start = 0

    sync_proc = mp.Process(target=run_syncer,
                           args=(addr, comm_addr, start, interval),
                           name='syncer',
                           daemon=True)
    sync_proc.start()

    ctx = zmq.Context()
    # socket for communicating with syncer
    comm = ctx.socket(zmq.REQ)
    comm.connect(comm_addr)

    # sync socket to return from the fixture
    syncs = []
    for _ in range(nclients):
        sync = ctx.socket(zmq.REQ)
        sync.connect(addr)
        syncs.append(sync)
    yield syncs, start

    # cleanup the syncer
    comm.send_string('exit')
    ret = comm.recv_pyobj()
    # join syncer thread
    sync_proc.join(2)
    # if ami still hasn't exitted then kill it
    if sync_proc.is_alive():
        print("try killing sync_proc")
        sync_proc.terminate()
        sync_proc.join(1)

    # cleanup zmq
    ctx.destroy()

    return ret


@pytest.mark.parametrize('iterations', range(4))
@pytest.mark.parametrize('sync_proc', [1, 2, 3, (2, 45)], indirect=True)
def test_timestamps(sync_proc, iterations):
    syncs, start = sync_proc
    nclients = len(syncs)

    for i in range(iterations):
        for c, sync in enumerate(syncs):
            sync.send_string('ts')
            ts = sync.recv_pyobj()

            # check the returned timestamp
            assert isinstance(ts, int)
            assert ts == start + (nclients * i + c)


@pytest.mark.parametrize('sync_proc', [1], indirect=True)
def test_badrequests(sync_proc):
    syncs, expected = sync_proc
    # check that only one client was returned
    assert len(syncs) == 1
    sync = syncs[0]

    # send a good request
    sync.send_string('ts')
    ts = sync.recv_pyobj()

    # check the returned timestamp
    assert isinstance(ts, int)
    assert ts == expected

    # increment the expected value
    expected += 1

    # send a bad request
    sync.send_string('bad')
    ts = sync.recv_pyobj()

    # check that no timestamp is returned
    assert ts is None

    # send a good request
    sync.send_string('ts')
    ts = sync.recv_pyobj()

    # check the returned timestamp
    assert isinstance(ts, int)
    assert ts == expected
