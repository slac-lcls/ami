import asyncio
import pytest
import zmq
import time
import amitypes as at
import multiprocessing as mp
# from ami.client import GraphAddress
from ami.client.flowchart import MessageBroker
import ami.client.flowchart_messages as fcMsgs
# from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.NodeLibrary import SourceLibrary
from collections import OrderedDict


class BrokerHelper:
    def __init__(self, ipcdir, comm):
        # we are in a forked process so create a new event loop (needed in some cases).
        self.loop = asyncio.new_event_loop()
        # set this new event loop as the default one so zmq picks it up
        asyncio.set_event_loop(self.loop)
        self.broker = MessageBroker("", "", "", ipcdir=ipcdir)
        self.comm = comm
        self.task = asyncio.ensure_future(self.broker.run())

        self.loop.run_until_complete(self.loop.run_in_executor(None, self.communicate))

        # if the message brokers task is still running cancel it
        if not self.task.done():
            self.task.cancel()
        self.comm.send('exit')

    def communicate(self):
        while True:
            request = self.comm.recv()
            if request is None:
                break
            else:
                self.comm.send(getattr(self.broker, request))

    @staticmethod
    def execute(ipcdir, comm):
        return BrokerHelper(ipcdir, comm)


class BrokerProxy:
    def __init__(self, comm):
        self.comm = comm

    def exit(self):
        self.comm.send(None)
        return self.comm.recv() == 'exit'

    def __getattr__(self, name):
        self.comm.send(name)
        return self.comm.recv()


@pytest.fixture(scope='function')
def broker(ipc_dir):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    parent_comm, child_comm = mp.Pipe()
    # start the manager process
    proc = mp.Process(
        name='broker',
        target=BrokerHelper.execute,
        args=(ipc_dir, child_comm),
        daemon=False
    )
    proc.start()

    broker = BrokerProxy(parent_comm)
    yield broker

    # cleanup the manager process
    broker.exit()
    proc.join(2)
    # if ami still hasn't exitted then kill it
    if proc.is_alive():
        proc.terminate()
        proc.join(1)
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


@pytest.mark.parametrize('start_ami', ['static'], indirect=True)
def test_source_library(complex_graph_file, start_ami):
    comm_handler = start_ami
    comm_handler.load(complex_graph_file)

    start = time.time()
    while comm_handler.graphVersion != comm_handler.featuresVersion:
        end = time.time()
        if end - start > 10:
            raise TimeoutError

    sources = comm_handler.sources
    source_library = SourceLibrary()

    for source, node_type in sources.items():
        root, *_ = source.split(':')
        source_library.addNodeType(source, node_type, [[root]])

    assert source_library.sourceList == {'cspad': at.Array2d, 'delta_t': int,
                                         'heartbeat': int, 'laser': int, 'timestamp': int}
    assert source_library.getSourceType('cspad') == at.Array2d

    try:
        source_library.addNodeType('cspad', at.Array2d, [[]])
    except Exception:
        pass

    try:
        source_library.getSourceType('')
    except Exception:
        pass

    assert source_library.getSourceTree() == OrderedDict([('delta_t', OrderedDict([('delta_t', 'delta_t')])),
                                                          ('cspad', OrderedDict([('cspad', 'cspad')])),
                                                          ('laser', OrderedDict([('laser', 'laser')])),
                                                          ('timestamp', OrderedDict([('timestamp', 'timestamp')])),
                                                          ('heartbeat', OrderedDict([('heartbeat', 'heartbeat')]))])

    labelTree = OrderedDict([('cspad', "<class 'amitypes.Array2d'>"),
                             ('delta_t', "<class 'int'>"),
                             ('heartbeat', "<class 'int'>"),
                             ('laser', "<class 'int'>"),
                             ('timestamp', "<class 'int'>")])

    assert source_library.getLabelTree() == labelTree
    assert source_library.getLabelTree() == labelTree


# @pytest.mark.parametrize('start_ami', ['static'], indirect=True)
# def test_editor(qtbot, broker, start_ami):

#     comm_handler = start_ami
#     time.sleep(1)
#     sources = comm_handler.sources

#     source_library = SourceLibrary()
#     for source, node_type in sources.items():
#         root, *_ = source.split(':')
#         source_library.addNodeType(source, node_type, [[root]])

#     graphmgr = GraphAddress("graph", comm_handler._addr)

#     fc = Flowchart(broker_addr=broker.broker_sub_addr,
#                    graphmgr_addr=graphmgr,
#                    node_addr=broker.node_addr,
#                    checkpoint_addr=broker.checkpoint_pub_addr)

#     qtbot.addWidget(fc.widget())

#     fc.createNode('Roi')
#     nodes = fc.nodes()
#     assert 'Roi.0' in nodes

#     # cleanup zmq context
#     fc.ctx.destroy()
