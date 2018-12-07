#!/usr/bin/env python
import zmq
import sys
import dill
import argparse
from ami.graphkit_wrapper import Graph
from ami.comm import Ports, Colors, Collector, EventBuilder
from ami.data import MsgTypes


class GraphCollector(Collector):
    def __init__(self, node, num_workers, color, collector_addr, downstream_addr, graph_addr):
        super(__class__, self).__init__(collector_addr)
        self.node = node
        self.num_workers = num_workers
        self.store = EventBuilder(
            self.num_workers, 10, color, downstream_addr, self.ctx)
        self.pickers = {}
        self.strategies = {}

        self.downstream_addr = downstream_addr

        self.graph = None
        self.graph_nwork = None
        self.graph_ncol = None
        self.graph_comm = self.ctx.socket(zmq.SUB)
        self.graph_comm.setsockopt_string(zmq.SUBSCRIBE, "")
        self.graph_comm.connect(graph_addr)
        self.register(self.graph_comm, self.recv_graph)

    def recv_graph(self):
        topic = self.graph_comm.recv_string()
        self.graph_nwork, self.graph_ncol = self.graph_comm.recv_pyobj()
        if topic == 'graph':
            self.graph = self.graph_comm.recv()
        elif topic == "add":
            add_update = dill.loads(self.graph_comm.recv())
            if self.graph is not None:
                updated_graph = dill.loads(self.graph)
                updated_graph.add(add_update)
                self.graph = dill.dumps(updated_graph)
            else:
                print("Add requested on empty graph")
        else:
            print("invalid topic: %s" % topic)

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Transition:
            self.store.transition(msg.identity, msg.payload.ttype)
            if self.store.transition_ready(msg.payload.ttype):
                self.store.message(msg.mtype, self.node, msg.payload)
        elif msg.mtype == MsgTypes.Datagram:
            self.store.update(msg.heartbeat, msg.identity, msg.payload)
            self.store.heartbeat(msg.identity, msg.heartbeat)
            if self.store.heartbeat_ready(msg.heartbeat):
                self.store.complete(self.node, msg.heartbeat)
                if self.graph is not None:
                    self.store.set_graph(msg.heartbeat+1, self.graph_nwork, self.graph_ncol, self.graph)


def run_collector(node_num, num_contribs, color, collector_addr, upstream_addr, graph_addr):
    print('Starting collector on node # %d' % node_num)
    collector = GraphCollector(
        node_num,
        num_contribs,
        color,
        collector_addr,
        upstream_addr,
        graph_addr)
    return collector.run()


def run_node_collector(node_num, num_contribs, collector_addr, upstream_addr, graph_addr):
    return run_collector(node_num, num_contribs, Colors.LocalCollector, collector_addr, upstream_addr, graph_addr)


def run_global_collector(node_num, num_contribs, collector_addr, upstream_addr, graph_addr):
    return run_collector(node_num, num_contribs, Colors.GlobalCollector, collector_addr, upstream_addr, graph_addr)


def main(color, upstream_port, downstream_port):
    parser = argparse.ArgumentParser(description='AMII Collector App')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-c',
        '--collector',
        type=int,
        default=upstream_port,
        help='port of the collector (default: %d)' % upstream_port
    )

    parser.add_argument(
        '-d',
        '--downstream',
        type=int,
        default=downstream_port,
        help='port for global collector (default: %d)' % downstream_port
    )

    parser.add_argument(
        '-g',
        '--graph',
        type=int,
        default=Ports.Graph,
        help='port for graph communication (default: %d)' % Ports.Graph
    )

    parser.add_argument(
        '-n',
        '--num-contribs',
        type=int,
        default=1,
        help='number of contributer processes (default: 1)'
    )

    parser.add_argument(
        '-N',
        '--node-num',
        type=int,
        default=0,
        help='node identification number (default: 0)'
    )

    args = parser.parse_args()
    collector_addr = "tcp://*:%d" % (args.collector)
    downstream_addr = "tcp://%s:%d" % (args.host, args.downstream)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)

    try:
        run_collector(args.node_num, args.num_contribs, color, collector_addr, downstream_addr, graph_addr)

        return 0
    except KeyboardInterrupt:
        print("Worker killed by user...")
        return 0


def node_main():
    return main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector)


def global_main():
    return main(Colors.GlobalCollector, Ports.FinalCollector, Ports.Results)


if __name__ == '__main__':
    sys.exit(main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector))
