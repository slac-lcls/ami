#!/usr/bin/env python
import zmq
import sys
import dill
import logging
import argparse
from ami import LogConfig
from ami.comm import Ports, Colors, Collector, EventBuilder
from ami.data import MsgTypes


logger = logging.getLogger(__name__)


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
        self.graph_comm = self.ctx.socket(zmq.SUB)
        self.graph_comm.setsockopt_string(zmq.SUBSCRIBE, "")
        self.graph_comm.connect(graph_addr)
        self.register(self.graph_comm, self.recv_graph)

    def recv_graph(self):
        topic = self.graph_comm.recv_string()
        nwork, ncol, version = self.graph_comm.recv_pyobj()
        if topic == 'graph':
            self.graph = self.graph_comm.recv()
            self.store.set_graph(version, nwork, ncol, self.graph)
        elif topic == "add":
            add_update = dill.loads(self.graph_comm.recv())
            if self.graph is not None:
                updated_graph = dill.loads(self.graph)
                updated_graph.add(add_update)
                self.graph = dill.dumps(updated_graph)
                self.store.set_graph(version, nwork, ncol, self.graph)
            else:
                logger.error("Add requested on empty graph")
        elif topic == "del":
            name = dill.loads(self.graph_comm.recv())
            if self.graph is not None:
                updated_graph = dill.loads(self.graph)
                updated_graph.remove(name)
                # check if the resulting graph is empty
                if not updated_graph:
                    updated_graph = None
                self.graph = dill.dumps(updated_graph)
                self.store.set_graph(version, nwork, ncol, self.graph)
            else:
                logger.error("Delete requested on empty graph")
        else:
            logger.warn("invalid topic: %s", topic)

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Transition:
            self.store.transition(msg.identity, msg.payload.ttype)
            if self.store.transition_ready(msg.payload.ttype):
                self.store.message(msg.mtype, self.node, msg.payload)
        elif msg.mtype == MsgTypes.Datagram:
            self.store.update(msg.heartbeat, msg.identity, msg.version, msg.payload)
            self.store.heartbeat(msg.identity, msg.heartbeat)
            if self.store.heartbeat_ready(msg.heartbeat):
                self.store.complete(self.node, msg.heartbeat)
                # prune entries older than the current heartbeat
                self.store.prune(msg.heartbeat)
            else:
                # prune older entries from the event builder
                self.store.prune()


def run_collector(node_num, num_contribs, color, collector_addr, upstream_addr, graph_addr):
    logger.info('Starting collector on node # %d', node_num)
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

    parser.add_argument(
        '--log-level',
        default=LogConfig.Level,
        help='the logging level of the application (default %s)' % LogConfig.Level
    )

    parser.add_argument(
        '--log-file',
        help='an optional file to write the log output to'
    )

    args = parser.parse_args()
    collector_addr = "tcp://*:%d" % (args.collector)
    downstream_addr = "tcp://%s:%d" % (args.host, args.downstream)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        run_collector(args.node_num, args.num_contribs, color, collector_addr, downstream_addr, graph_addr)

        return 0
    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


def node_main():
    return main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector)


def global_main():
    return main(Colors.GlobalCollector, Ports.FinalCollector, Ports.Results)


if __name__ == '__main__':
    sys.exit(main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector))
