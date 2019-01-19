
"""
Note: pytest-xprocess seems like the `approved` way to start an
external server, but not sure if it is the right thing to do

To use:
1. Inheret from AmiTBase
2. Implement one or more test() functions
"""

import signal
import multiprocessing as mp
import pytest
import time
import os

from ami.comm import Ports, GraphCommHandler
from ami.local import build_parser, run_ami


@pytest.fixture(scope='class')
def start_ami(pytestconfig):
    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-t', '--headless',
                              'static://%s' % os.path.join(pytestconfig.rootdir, 'tests', 'worker_test.json')])

    queue = mp.Queue()
    ami = mp.Process(name='ami',
                     target=run_ami,
                     args=(args, queue))
    ami.start()

    host = "127.0.0.1"
    comm_addr = "tcp://%s:%d" % (host, Ports.Comm+3)
    comm_handler = GraphCommHandler(comm_addr)

    yield (comm_handler, pytestconfig.rootdir)

    queue.put(None)
    ami.join()

    if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
        print('AMI exited successfully')
    else:
        print('AMI exited with non-zero status code: %d' % ami.exitcode)
        return 1

    return 0


@pytest.mark.usefixtures("start_ami")
class TestAMI(object):

    def test_complex_graph(self, complex_graph, start_ami):
        comm_handler, root_dir = start_ami
        comm_handler.load(complex_graph)
        start = time.time()
        while comm_handler.graphVersion != comm_handler.featuresVersion:
            end = time.time()
            if end - start > 10:
                break
        sig = comm_handler.fetch('signal')
        assert sig == {1: 10000.0}
