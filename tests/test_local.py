
"""
Note: pytest-xprocess seems like the `approved` way to start an
external server, but not sure if it is the right thing to do

To use:
1. Inheret from AmiTBase
2. Implement one or more test() functions
"""


import re
import signal
import tempfile
import multiprocessing as mp
# import json
# import numpy as np

from ami.comm import Ports
from ami.manager import run_manager
from ami.worker import run_worker
from ami.collector import run_collector
from ami.client import CommunicationHandler


class AmiTBase(object):

    def setup(self):
        self.num_workers = 2
        port = Ports.Comm
        tcp = False
        ipcdir = None
        source = 'static://examples/worker.json'
        heartbeat = 3
        if tcp:
            host = "127.0.0.1"
            collector_addr = "tcp://%s:%d" % (host, port)
            finalcol_addr = "tcp://%s:%d" % (host, port+1)
            graph_addr = "tcp://%s:%d" % (host, port+2)
            comm_addr = "tcp://%s:%d" % (host, port+3)
        else:
            ipcdir = tempfile.mkdtemp()
            collector_addr = "ipc://%s/node_collector" % ipcdir
            finalcol_addr = "ipc://%s/collector" % ipcdir
            graph_addr = "ipc://%s/graph" % ipcdir
            comm_addr = "ipc://%s/comm" % ipcdir

        self.procs = []

        src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', source)
        if src_url_match:
            src_cfg = src_url_match.groups()
        else:
            print("Invalid data source config string:", source)
            return 1

        args = [(i, self.num_workers, heartbeat, src_cfg, collector_addr, graph_addr) for i in range(self.num_workers)]
        self.pool = mp.Pool(self.num_workers)
        self.workers = self.pool.starmap_async(run_worker, args)

        collector_proc = mp.Process(
            name='nodecol-n0',
            target=run_collector,
            args=(0, self.num_workers, collector_addr, finalcol_addr)
        )
        collector_proc.daemon = True
        collector_proc.start()
        self.procs.append(collector_proc)

        manager_proc = mp.Process(
            name='manager',
            target=run_manager,
            args=(finalcol_addr, graph_addr, comm_addr)
        )
        manager_proc.daemon = True
        manager_proc.start()
        self.procs.append(manager_proc)

        self.comm_handler = CommunicationHandler(comm_addr)

        return 0

    def teardown(self):

        self.pool.terminate()
        self.pool.join()

        for proc in self.procs:
            proc.terminate()
            proc.join()
            if proc.exitcode == 0 or proc.exitcode == -signal.SIGTERM:
                print('%s exited successfully' % proc.name)
            else:
                print('%s exited with non-zero status code: %d' % (proc.name, proc.exitcode))
                return 1

        return 0

    def get_feature(self, feat):

        self.comm_handler.sock.send_string("feature:%s" % feat)
        reply = self.comm_handler.sock.recv_string()

        if reply == 'ok':
            feature = self.comm_handler.sock.recv_pyobj()
            return feature


class TestAMI(AmiTBase):

    def test1(self):
        # do test
        """
        with open('examples/basic.ami', 'r') as cnf:
            graph = json.load(cnf)
            self.comm_handler.update(graph)

        self.workers.wait(timeout=10)

        cspad_sum = self.get_feature('cspad_sum')
        assert cspad_sum == 366149.0

        sum2 = self.get_feature('sum2')
        assert np.array_equal(sum2, np.ones((512, 512))*13)
        """
        return

    def test2(self):
        # do a different test
        return
