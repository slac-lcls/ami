import asyncio
import pytest
import zmq
import time
import os
import signal
import json
import amitypes as at
import multiprocessing as mp
import ami.client.flowchart_messages as fcMsgs
from ami.client import GraphMgrAddress
from ami.client.flowchart import MessageBroker
from ami.flowchart.Flowchart import Flowchart
from ami.flowchart.library.common import SourceNode
from ami.local import build_parser, run_ami
from ami.comm import GraphCommHandler
from collections import OrderedDict


class BrokerHelper:
    def __init__(self, graphmgr_addr, ipcdir, comm):
        # we are in a forked process so create a new event loop (needed in some cases).
        self.loop = asyncio.new_event_loop()
        # set this new event loop as the default one so zmq picks it up
        asyncio.set_event_loop(self.loop)
        self.broker = MessageBroker(graphmgr_addr, "", ipcdir=ipcdir)
        self.comm = comm
        self.task = asyncio.ensure_future(self.broker.run())

        self.loop.run_until_complete(self.loop.run_in_executor(None, self.communicate))

        # if the message brokers task is still running cancel it
        if not self.task.done():
            self.task.cancel()

        # cleanup the broker
        self.broker.close()

    def communicate(self):
        while True:
            request = self.comm.recv()
            if request is None:
                break
            else:
                self.comm.send(getattr(self.broker, request))

    @staticmethod
    def execute(graphmgr_addr, ipcdir, comm):
        return BrokerHelper(graphmgr_addr, ipcdir, comm)


class BrokerProxy:
    def __init__(self, comm):
        self.comm = comm

    def exit(self):
        self.comm.send(None)

    def __getattr__(self, name):
        self.comm.send(name)
        return self.comm.recv()


@pytest.fixture(scope='function')
def event_loop(qevent_loop):
    """
    Adding this overrides the event_loop fixture from pytest-asyncio. This lets
    us use the qevent_loop when using the @pytest.mark.asyncio decorator
    """
    yield qevent_loop
    # clean up the event loop after test
    qevent_loop.close()


@pytest.fixture(scope='function')
def graphmgr_addr(ipc_dir):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    comm_addr = "ipc://%s/comm" % ipc_dir
    view_addr = "ipc://%s/view" % ipc_dir
    graphinfo_addr = "ipc://%s/info" % ipc_dir

    graphmgr = GraphMgrAddress("graph", comm_addr, view_addr, graphinfo_addr)

    yield graphmgr


@pytest.fixture(scope='function')
def broker(ipc_dir, graphmgr_addr):
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
        args=(graphmgr_addr, ipc_dir, child_comm),
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
        proc.join()
    return proc.exitcode


@pytest.fixture(scope='function')
def flowchart(request, workerjson, broker, ipc_dir, graphmgr_addr, qevent_loop):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              '%s://%s' %
                              (request.param, workerjson)])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        # wait for ami to be fully up before updating the sources
        with GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm) as comm:
            while not comm.sources:
                time.sleep(0.1)

        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:

            qevent_loop.run_until_complete(fc.updateSources(init=True))

            yield (fc, broker)

    except Exception as e:
        # let the fixture exit 'gracefully' if it fails
        print("error setting up flowchart fixture:", e)
        yield None
    finally:
        queue.put(None)
        ami.join(2)
        # if ami still hasn't exitted then kill it
        if ami.is_alive():
            ami.terminate()
            ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1


@pytest.fixture(scope='function')
def flowchart_hdf(request, tmp_path, qtbot, broker, ipc_dir, graphmgr_addr, qevent_loop):
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass

    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "repeat": True,
        "files": [os.path.join('tests/graphs', request.param[0])]
    }

    fname = os.path.join(tmp_path, 'worker.json')
    with open(fname, 'w') as fd:
        json.dump(cfg, fd)

    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              'hdf5://%s' % fname])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    try:
        # wait for ami to be fully up before updating the sources
        comm = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)
        while not comm.sources:
            time.sleep(0.1)

        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:

            qevent_loop.run_until_complete(fc.updateSources(init=True))

            qtbot.addWidget(fc.widget())
            fc.loadFile(os.path.join('tests/graphs', request.param[1]))

            yield (fc, broker, comm)

    except Exception as e:
        # let the fixture exit 'gracefully' if it fails
        print("error setting up flowchart fixture:", e)
        yield None
    finally:
        queue.put(None)
        ami.join(2)
        # if ami still hasn't exitted then kill it
        if ami.is_alive():
            ami.terminate()
            ami.join()

        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print('AMI exited with non-zero status code: %d' % ami.exitcode)
            return 1


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

    # cleanup the zmq context
    ctx.destroy()


@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
def test_sources(qtbot, flowchart):
    flowchart = flowchart[0]
    source_library = flowchart.source_library

    source_tree = source_library.getSourceTree()
    sources = set(source_tree.keys())
    assert sources == set(['delta_t', 'cspad', 'laser', 'eventid', 'timestamp', 'heartbeat', 'source'])

    label_tree = OrderedDict([('cspad', "<class 'amitypes.array.Array2d'>"),
                              ('delta_t', "<class 'int'>"),
                              ('eventid', "<class 'int'>"),
                              ('heartbeat', "<class 'int'>"),
                              ('laser', "<class 'int'>"),
                              ('source', "<class 'amitypes.source.DataSource'>"),
                              ('timestamp', "<class 'float'>")])
    assert source_library.getLabelTree() == label_tree
    # test cached version
    assert source_library.getLabelTree() == label_tree

    assert source_library.getSourceType('cspad') == at.Array2d

    try:
        source_library.getSourceType('')
    except KeyError:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
async def test_editor(qtbot, flowchart, tmp_path):
    flowchart, broker = flowchart

    qtbot.addWidget(flowchart.widget())

    flowchart.createNode('Roi2D')
    roi_node = flowchart.nodes(data='node')['Roi2D.0']

    node_name = 'cspad'
    node_type = flowchart.source_library.getSourceType(node_name)
    node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})

    flowchart.addNode(node=node)
    cspad_node = flowchart.nodes(data='node')['cspad']

    cspad_out = cspad_node._outputs['Out']
    roi_in = roi_node._inputs['In']

    cspad_out().connectTo(roi_in())
    assert len(flowchart._graph.edges()) == 1

    widget = flowchart.widget()

    pth = os.path.join(tmp_path, 'graph.fc')
    widget.setCurrentFile(pth)
    widget.saveClicked()

    # await widget.clear()
    # assert len(flowchart._graph.edges()) == 0

    # await flowchart.loadFile(pth)
    # assert len(flowchart._graph.edges()) == 1


# @pytest.mark.asyncio
# @pytest.mark.parametrize('flowchart_hdf', [('run22.h5', 'run22.fc')], indirect=True)
# async def test_run22(qtbot, flowchart_hdf, graphmgr_addr):
#     flowchart, broker, comm = flowchart_hdf

#     ctrl = flowchart.widget()
#     viewbox = ctrl.viewBox()
#     scene = ctrl.scene()
#     chartWidget = ctrl.chartWidget
#     await ctrl.applyClicked()

#     outputs = [n for n, d in flowchart._graph.out_degree() if d == 0]

#     for output in outputs:
#         node = flowchart._graph.nodes[output]['node']
#         graphicsItem = node.graphicsItem()
#         graphicsItem.setSelected(True)
#         graphicsItem.update()
#         await chartWidget.selectionChanged()
#         graphicsItem.setSelected(False)
#         graphicsItem.update()
#         break

#     while not comm.features:
#         time.sleep(0.1)

#     print(comm.features)
