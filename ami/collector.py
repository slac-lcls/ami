#!/usr/bin/env python
import zmq
import sys
import dill
import argparse
from ami.graph import Graph
from ami.comm import Ports, Collector, EventBuilder, PickNBuilder
from ami.data import MsgTypes, Strategies


class NodeCollector(Collector):
    def __init__(self, node, num_workers, collector_addr, downstream_addr, graph_addr):
        super(__class__, self).__init__(collector_addr)
        self.node = node
        self.num_workers = num_workers
        self.store = EventBuilder(
            self.num_workers, 10, downstream_addr, self.ctx)
        self.pickers = {}
        self.strategies = {}

        self.downstream_addr = downstream_addr

        self.graph = None
        self.graph_comm = self.ctx.socket(zmq.SUB)
        self.graph_comm.setsockopt_string(zmq.SUBSCRIBE, "graph")
        self.graph_comm.connect(graph_addr)
        self.register(self.graph_comm, self.recv_graph)

    def recv_graph(self):
        topic = self.graph_comm.recv_string()
        if topic == 'graph':
            self.graph = dill.loads(self.graph_comm.recv())
        else:
            print("invalid topic: %s"%topic)

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Transition:
            self.store.transition(msg.identity, msg.payload.ttype)
            if self.store.transition_ready(msg.payload.ttype):
                self.store.send(msg)
        elif msg.mtype == MsgTypes.Heartbeat:
            self.store.heartbeat(msg.identity, msg.payload)
            if self.store.heartbeat_ready(msg.payload):
                #print("completing heartbeat", msg.payload)
                self.store.complete(self.node, msg.payload)
                if self.graph is not None:
                    self.store.set_graph(msg.payload+1, self.graph)
        elif msg.mtype == MsgTypes.Datagram:
            #print(msg.payload)
            self.store.update(msg.heartbeat, msg.identity, msg.payload)
            """
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
        """

def run_collector(node_num, num_workers, collector_addr, upstream_addr, graph_addr):
    print('Starting collector on node # %d' % node_num)
    collector = NodeCollector(
        node_num,
        num_workers,
        collector_addr,
        upstream_addr,
        graph_addr)
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
        '-c',
        '--collector',
        type=int,
        default=Ports.FinalCollector,
        help='port for final collector (default: %d)' % Ports.FinalCollector
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

    args = parser.parse_args()
    collector_addr = "tcp://127.0.0.1:%d" % (Ports.NodeCollector)
    upstream_addr = "tcp://%s:%d" % (args.host, args.collector)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)

    try:
        run_collector(args.node_num, args.num_workers, collector_addr, upstream_addr, graph_addr)

        return 0
    except KeyboardInterrupt:
        print("Worker killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
