import re
import os
import sys
import zmq
import json
import shutil
import tempfile
import argparse
import multiprocessing as mp
from ami.graph import Graph, GraphConfigError, GraphRuntimeError
from ami.comm import Ports, Collector, ResultStore, EventBuilder, PickNBuilder
from ami.data import MsgTypes, Transitions, Transition, StaticSource, PsanaSource, Strategies


class Worker(object):
    def __init__(self, idnum, heartbeat_period, src, collector_addr, graph_addr):
        """
        idnum : int
            a unique integer identifying this worker
        src : object
            object with an events() method that is an iterable (like psana.DataSource)
        """

        self.idnum = idnum
        self.src = src
        self.ctx = zmq.Context()
        self.store = ResultStore(collector_addr, self.ctx)

        self.graph = Graph(self.store)

        self.graph_comm = self.ctx.socket(zmq.SUB)
        self.graph_comm.setsockopt_string(zmq.SUBSCRIBE, "graph")
        self.graph_comm.connect(graph_addr)
        self.requests = []
        self.last_timestamp = 0
        self.heartbeat_period = heartbeat_period

    def check_heartbeat_boundary(self, timestamp):
        ret = (timestamp // self.heartbeat_period) > (self.last_timestamp // self.heartbeat_period)
        self.last_timestamp = timestamp
        return ret

    def run(self):
        sources = []
        partition = self.src.partition()
        self.store.message(MsgTypes.Transition,
                           self.idnum,
                           Transition(Transitions.Allocate, partition))
        for name, dtype in partition:
            self.store.create(name, dtype)
            sources.append(name)

        for msg in self.src.events():
            # check to see if the graph has been reconfigured after update
            if msg.mtype == MsgTypes.Datagram:
                if self.check_heartbeat_boundary(msg.timestamp):
                    self.store.collect(self.idnum, msg.timestamp//self.heartbeat_period)
                    new_graph = None
                    while True:
                        try:
                            topic = self.graph_comm.recv_string(flags=zmq.NOBLOCK)
                            payload = self.graph_comm.recv_pyobj()
                            if topic == "graph":
                                new_graph = payload
                            else:
                                print(
                                    "worker%d: No handler for received topic: %s" %
                                    (self.idnum, topic))
                        except zmq.Again:
                            break
                    if new_graph is not None:

                        self.graph.update(new_graph)

                        print("worker%d: Received new configuration" % self.idnum)
                        try:
                            self.graph.configure(sources)
                            print("worker%d: Configuration complete" % self.idnum)
                        except GraphConfigError as graph_err:
                            print(
                                "worker%d: Configuration failed reverting to previous config:" %
                                self.idnum, graph_err)
                            # if this fails we just die
                            self.graph.revert()

                        self.new_graph_available = False
                    if new_graph is not None:
                        self.store.message(MsgTypes.Graph, self.idnum, new_graph)

                # clear old values from the store
                # self.store.clear()
                for dgram in msg.payload:
                    self.store.put(dgram.name, dgram.data)

                try:
                    self.graph.execute()
                except GraphRuntimeError as graph_err:
                    print(
                        "worker%s: Failure encountered executing graph:" %
                        self.idnum, graph_err)
                    return 1
            else:
                self.store.send(msg)


class NodeCollector(Collector):
    def __init__(self, node, num_workers, collector_addr, downstream_addr):
        super(__class__, self).__init__(collector_addr)
        self.node = node
        self.num_workers = num_workers
        self.store = EventBuilder(
            self.num_workers, 10, downstream_addr, self.ctx)
        self.pickers = {}
        self.strategies = {}

        self.downstream_addr = downstream_addr

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Transition:
            self.store.transition(msg.identity, msg.payload.ttype)
            if self.store.transition_ready(msg.payload.ttype):
                self.store.send(msg)
        elif msg.mtype == MsgTypes.Heartbeat:
            self.store.heartbeat(msg.identity, msg.payload)
            if self.store.heartbeat_ready(msg.payload):
                self.store.complete(self.node, msg.payload)
        elif msg.mtype == MsgTypes.Datagram:
            if msg.payload.name in self.strategies:
                if self.strategies[msg.payload.name] == Strategies.Sum.value:
                    self.store.sum(
                        msg.heartbeat,
                        msg.identity,
                        msg.payload.name,
                        msg.payload.data,
                        0)
                elif self.strategies[msg.payload.name] == Strategies.Avg.value:
                    self.store.sum(
                        msg.heartbeat,
                        msg.identity,
                        msg.payload.name,
                        msg.payload.data,
                        msg.payload.weight)
                elif self.strategies[msg.payload.name] == Strategies.Pick1.value:
                    self.store.put(
                        msg.heartbeat,
                        msg.identity,
                        msg.payload.name,
                        msg.payload.data)
                elif self.strategies[msg.payload.name] == "AverageN":
                    if msg.payload.name not in self.pickers:
                        self.pickers[msg.payload.name] = PickNBuilder(self.num_workers, self.downstream_addr, self.ctx)
                    self.pickers[msg.payload.name].put(msg.payload)
                else:
                    print("node_collector%d: Unknown collector strategy - %s" %
                          (self.node, self.strategies[msg.payload.name]))
            else:
                # We assume Pick1 for the stuff that comes from the raw data
                self.store.put(
                    msg.heartbeat,
                    msg.identity,
                    msg.payload.name,
                    msg.payload.data)
        elif msg.mtype == MsgTypes.Graph:
            self.strategies = Graph.extract_collection_strategies(msg.payload)


def run_worker(num, num_workers, hb_period, source, collector_addr, graph_addr):

    print(
        'Starting worker # %d, sending to collector at %s' %
        (num, collector_addr))

    if source[0] == 'static':
        try:
            with open(source[1], 'r') as cnf:
                src_cfg = json.load(cnf)
        except OSError as os_exp:
            print("worker%03d: problem opening json file:" % num, os_exp)
            return 1
        except json.decoder.JSONDecodeError as json_exp:
            print(
                "worker%03d: problem parsing json file (%s):" %
                (num, source[1]), json_exp)
            return 1

        src = StaticSource(num,
                           num_workers,
                           src_cfg['interval'],
                           src_cfg["init_time"],
                           src_cfg['config'])
    elif source[0] == 'psana':
        try:
            with open(source[1], 'r') as cnf:
                src_cfg = json.load(cnf)
        except OSError as os_exp:
            print("worker%03d: problem opening json file:" % num, os_exp)
            return 1
        except json.decoder.JSONDecodeError as json_exp:
            print(
                "worker%03d: problem parsing json file (%s):" %
                (num, source[1]), json_exp)
            return 1

        src = PsanaSource(num,
                          num_workers,
                          src_cfg['interval'],
                          src_cfg["init_time"],
                          src_cfg['config'])
    else:
        print("worker%03d: unknown data source type:" % num, source[0])
        return 1
    worker = Worker(num, hb_period, src, collector_addr, graph_addr)
    return worker.run()


def run_collector(node_num, num_workers, collector_addr, upstream_addr):
    print('Starting collector on node # %d' % node_num)
    collector = NodeCollector(
        node_num,
        num_workers,
        collector_addr,
        upstream_addr)
    return collector.run()


def main():
    parser = argparse.ArgumentParser(description='AMII Worker/Collector App')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for GUI-Manager communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-g',
        '--graph',
        type=int,
        default=Ports.Graph,
        help='port for graph communication (default: %d)' % Ports.Graph
    )

    parser.add_argument(
        '-c',
        '--collector',
        type=int,
        default=Ports.Collector,
        help='port for final collector (default: %d)' % Ports.Collector
    )

    parser.add_argument(
        '-n',
        '--num-workers',
        type=int,
        default=1,
        help='number of worker processes (default: 1)'
    )

    parser.add_argument(
        '-N',
        '--node-num',
        type=int,
        default=0,
        help='node identification number (default: 0)'
    )

    parser.add_argument(
        '-b',
        '--heartbeat',
        type=int,
        default=10,
        help='the heartbeat period (default: 10)'
    )

    parser.add_argument(
        'source',
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, psana://exp=xcsdaq13:run=14)'
    )

    args = parser.parse_args()
    ipcdir = tempfile.mkdtemp()
    collector_addr = "ipc://%s/node_collector" % ipcdir
    upstream_addr = "tcp://%s:%d" % (args.host, args.collector)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)

    procs = []
    failed_worker = False

    try:
        src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
        if src_url_match:
            src_cfg = src_url_match.groups()
        else:
            print("Invalid data source config string:", args.source)
            return 1

        for i in range(args.num_workers):
            proc = mp.Process(
                name='worker%03d-n%03d' % (i, args.node_num),
                target=run_worker,
                args=(i, args.num_workers, args.heartbeat, src_cfg, collector_addr, graph_addr)
            )
            proc.daemon = True
            proc.start()
            procs.append(proc)

        collector_proc = mp.Process(
            name='manager-n%03d' % args.node_num,
            target=run_collector,
            args=(
                args.node_num,
                args.num_workers,
                collector_addr,
                upstream_addr)
        )
        collector_proc.daemon = True
        collector_proc.start()
        procs.append(collector_proc)

        for proc in procs:
            proc.join()
            if proc.exitcode == 0:
                print('%s exited successfully' % proc.name)
            else:
                failed_worker = True
                print(
                    '%s exited with non-zero status code: %d' %
                    (proc.name, proc.exitcode))

        # return a non-zero status code if any workerss died
        if failed_worker:
            return 1

        return 0
    except KeyboardInterrupt:
        print("Worker killed by user...")
        return 0
    finally:
        if ipcdir is not None and os.path.exists(ipcdir):
            shutil.rmtree(ipcdir)


if __name__ == '__main__':
    sys.exit(main())
