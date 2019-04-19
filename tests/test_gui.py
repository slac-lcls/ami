import asyncio
import pytest
import zmq
import zmq.asyncio
import ami.client.flowchart_messages as fcMsgs
from ami.client.flowchart import MessageBroker
from asyncqt import QEventLoop


@pytest.yield_fixture()
def q_event_loop(qapp):
    loop = QEventLoop(qapp)
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.mark.asyncio
@pytest.fixture(scope='function')
async def broker(ipc_dir):
    broker = MessageBroker("", "", ipcdir=ipc_dir)
    addrs = {'broker_sub_addr': broker.broker_sub_addr,
             'broker_pub_addr': broker.broker_pub_addr,
             'node_addr': broker.node_addr,
             'checkpoint_sub_addr': broker.checkpoint_sub_addr,
             'checkpoint_pub_addr': broker.checkpoint_pub_addr}

    task = broker.run()
    yield broker, addrs
    await task


@pytest.mark.asyncio
async def test_broker_sub(broker, event_loop):
    broker, addrs = broker
    ctx = zmq.asyncio.Context()
    socket = ctx.socket(zmq.PUB)
    socket.connect(addrs['broker_sub_addr'])

    name = "Projection"
    msg = fcMsgs.CreateNode(name, "Projection")
    await socket.send_string(name, zmq.SNDMORE)
    await socket.send_pyobj(msg)
    assert len(broker.msgs) == 1
