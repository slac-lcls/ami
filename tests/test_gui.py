import asyncio
import pytest
import zmq
import time
import multiprocessing as mp
import ami.client.flowchart_messages as fcMsgs
from ami.client.flowchart import MessageBroker
from asyncqt import QEventLoop


class BrokerHelper:
    def __init__(self, ipcdir, comm):
        # we are in a forked process so create a new event loop (needed in some cases).
        self.loop = asyncio.new_event_loop()
        # set this new event loop as the default one so zmq picks it up
        asyncio.set_event_loop(self.loop)
        self.broker = MessageBroker("", "", ipcdir=ipcdir)
        self.comm = comm
        self.loop.run_until_complete(self.run())
        self.loop.close()

    async def run(self):
        await asyncio.gather(self.broker.run(),
                             self.loop.run_in_executor(None, self.communicate))

    def communicate(self):
        while True:
            name = self.comm.recv()
            self.comm.send(getattr(self.broker, name))

    @staticmethod
    def execute(ipcdir, comm):
        return BrokerHelper(ipcdir, comm)


class BrokerProxy:
    def __init__(self, comm):
        self.comm = comm

    def __getattr__(self, name):
        self.comm.send(name)
        return self.comm.recv()


@pytest.yield_fixture()
def q_event_loop(qapp):
    loop = QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope='function')
def broker(ipc_dir):
    parent_comm, child_comm = mp.Pipe()
    # start the manager process
    proc = mp.Process(
        name='broker',
        target=BrokerHelper.execute,
        args=(ipc_dir, child_comm),
        daemon=False
    )
    proc.start()

    yield BrokerProxy(parent_comm)

    # cleanup the manager process
    proc.terminate()
    proc.join()
    return proc.exitcode


def test_broker_sub(broker):
    ctx = zmq.Context()
    socket = ctx.socket(zmq.XPUB)
    socket.connect(broker.broker_sub_addr)
    # wait for the subscriber to connect
    assert socket.recv_string() == '\x01'

    name = "Projection"
    msg = fcMsgs.CreateNode(name, "Projection")
    socket.send_string(name, zmq.SNDMORE)
    socket.send_pyobj(msg)

    # check that broker msgs are empty
    msgs = broker.msgs
    assert not msgs

    # send a node close msg
    msg = fcMsgs.CloseNode()
    socket.send_string(name, zmq.SNDMORE)
    socket.send_pyobj(msg)

    # wait to see if the broker msgs are updated
    start = time.time()
    while not msgs:
        end = time.time()
        if end - start > 10:
            assert False, "Timeout waiting for broker update"
        msgs = broker.msgs
    # check the msg
    assert name in msgs
    assert isinstance(msgs[name], fcMsgs.CloseNode)
