#!/usr/bin/env python
import sys
import logging
import argparse
from ami import LogConfig, Defaults
from ami.comm import Ports, Colors, Node, Collector, TransitionBuilder, EventBuilder
from ami.data import MsgTypes


logger = logging.getLogger(__name__)


class GraphCollector(Node, Collector):
    def __init__(self, node, base_name, num_workers, color, collector_addr, downstream_addr, graph_addr, msg_addr):
        Node.__init__(self, node, graph_addr, msg_addr)
        Collector.__init__(self, collector_addr, ctx=self.ctx)
        self.base_name = base_name
        self.num_workers = num_workers
        self.transitions = TransitionBuilder(self.num_workers, downstream_addr, self.ctx)
        self.store = EventBuilder(self.num_workers, 10, color, downstream_addr, self.ctx)
        self.pickers = {}
        self.strategies = {}

        self.downstream_addr = downstream_addr

        self.register(self.graph_comm.sock, self.graph_comm.recv)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def name(self):
        return self.base_name % self.node

    def close(self):
        self.ctx.destroy()

    def recv_graph(self, name, version, args, graph):
        self.store.set_graph(name, version, args, graph)

    def recv_graph_add(self, name, version, args, nodes):
        self.store.add_graph(name, version, args, nodes)

    def recv_graph_del(self, name, version, args, nodes):
        self.store.del_graph(name, version, args, nodes)

    def recv_graph_purge(self, name, version, args, graph):
        self.store.purge_graph(name, version, args, graph)

    def recv_graph_exception(self, name, version, exception):
        logger.exception("%s: Failure encountered updating graph (%s v%d):",
                         self.name, name, version)
        self.report("error", "Failure updating graph: %s" % exception)
        logger.error("%s: Purging graph (%s v%d)", self.name, name, version)
        self.store.destroy(name)
        self.report("purge", name)

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Transition:
            self.transitions.update(msg.payload.ttype, msg.identity, msg.payload.payload)
            if self.transitions.ready(msg.payload.ttype):
                self.transitions.complete(msg.payload.ttype, self.node)
        elif msg.mtype == MsgTypes.Datagram:
            self.store.update(msg.name, msg.heartbeat, msg.identity, msg.version, msg.payload)
            if self.store.ready(msg.name, msg.heartbeat):
                try:
                    # prune entries older than the current heartbeat
                    self.store.prune(msg.name, self.node, msg.heartbeat)
                    # complete the current heartbeat
                    times = self.store.complete(msg.name, msg.heartbeat, self.node)
                    if times:
                        self.report("profile", {'graph': msg.name,
                                                'heartbeat': msg.heartbeat,
                                                'times': times,
                                                'version': self.store.version(msg.name)})
                except Exception as e:
                    logger.exception("%s: Failure encountered while executing graph %s:", self.name, msg.name)
                    self.report("error", e)
                    logger.error("%s: Purging graph (%s v%d)", self.name, msg.name, self.store.version(msg.name))
                    self.store.destroy(msg.name)
                    self.report("purge", msg.name)
            else:
                # prune older entries from the event builder
                self.store.prune(msg.name, self.node)


def run_collector(node_num, base_name, num_contribs, color, collector_addr, upstream_addr, graph_addr, msg_addr):
    logger.info('Starting collector on node # %d', node_num)
    with GraphCollector(
            node_num,
            base_name,
            num_contribs,
            color,
            collector_addr,
            upstream_addr,
            graph_addr,
            msg_addr) as collector:
        return collector.run()


def run_node_collector(node_num, num_contribs, collector_addr, upstream_addr, graph_addr, msg_addr):
    return run_collector(node_num,
                         "localCollector%03d",
                         num_contribs,
                         Colors.LocalCollector,
                         collector_addr,
                         upstream_addr,
                         graph_addr,
                         msg_addr)


def run_global_collector(node_num, num_contribs, collector_addr, upstream_addr, graph_addr, msg_addr):
    return run_collector(node_num,
                         "globalCollector%03d",
                         num_contribs,
                         Colors.GlobalCollector,
                         collector_addr,
                         upstream_addr,
                         graph_addr,
                         msg_addr)


def main(color, upstream_port, downstream_port):
    parser = argparse.ArgumentParser(description='AMII Collector App')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
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
        '-m',
        '--message',
        type=int,
        default=Ports.Message,
        help='port for sending out-of-band messages from nodes (default: %d)' % Ports.Message
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
    msg_addr = "tcp://%s:%d" % (args.host, args.message)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        if color == Colors.LocalCollector:
            return run_node_collector(args.node_num,
                                      args.num_contribs,
                                      collector_addr,
                                      downstream_addr,
                                      graph_addr,
                                      msg_addr)
        elif color == Colors.GlobalCollector:
            return run_global_collector(args.node_num,
                                        args.num_contribs,
                                        collector_addr,
                                        downstream_addr,
                                        graph_addr,
                                        msg_addr)
        else:
            logger.critical("Invalid option collector color '%s' chosen!", color)
            return 1

    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


def node_main():
    return main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector)


def global_main():
    return main(Colors.GlobalCollector, Ports.FinalCollector, Ports.Results)


if __name__ == '__main__':
    sys.exit(main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector))
