
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

from ami.comm import Ports
from ami.manager import run_manager
from ami.worker import run_worker, run_collector


class AmiTBase(object):

    def setup(self):
        port = Ports.Comm
        tcp = False
        ipcdir = None
        source = 'static://examples/worker.json'
        num_workers = 2
        heartbeat = 10
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

        for i in range(num_workers):
            proc = mp.Process(
                name='worker%03d-n0' % i,
                target=run_worker,
                args=(i, num_workers, heartbeat, src_cfg, collector_addr, graph_addr)
            )
            proc.daemon = True
            proc.start()
            self.procs.append(proc)

        collector_proc = mp.Process(
            name='nodecol-n0',
            target=run_collector,
            args=(0, num_workers, collector_addr, finalcol_addr)
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

        return 0

    def teardown(self):

        for proc in self.procs:
            proc.terminate()
            proc.join()
            if proc.exitcode == 0 or proc.exitcode == -signal.SIGTERM:
                print('%s exited successfully' % proc.name)
            else:
                print('%s exited with non-zero status code: %d' % (proc.name, proc.exitcode))
                return 1

        return 0


class TestAMI(AmiTBase):

    def test1(self):
        # do test
        return

    def test2(self):
        # do a different test
        return
