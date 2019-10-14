#!/usr/bin/env python
import re
import sys
import zmq
import json
import logging
import argparse
from ami import LogConfig, Defaults
from ami.comm import Ports, Colors, ResultStore, Node
from ami.data import MsgTypes, Source
from ami.graphkit_wrapper import Graph


logger = logging.getLogger(__name__)


class Worker(Node):
    def __init__(self, node, src, collector_addr, graph_addr, msg_addr):
        """
        node : int
            a unique integer identifying this worker
        src : object
            object with an events() method that is an iterable (like psana.DataSource)
        """
        super(__class__, self).__init__(node, graph_addr, msg_addr)

        self.src = src

        self.store = ResultStore(collector_addr, self.ctx)

        self.graph_comm.add_command("config", self.send_configure)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @property
    def name(self):
        return "worker%03d" % self.node

    def close(self):
        self.ctx.destroy()

    def send_configure(self):
        self.store.send(self.src.configure())

    def init_graph(self, name):
        if name not in self.graphs or self.graphs[name] is None:
            self.graphs[name] = Graph(name)

    def update_requests(self):
        requests = set()
        for graph in self.graphs.values():
            if graph is not None:
                requests.update(graph.sources)
        self.src.request(requests)

    def update_graph(self, name, version, args):
        if self.graphs[name]:
            self.graphs[name].compile(**args)
        self.update_requests()
        self.store.configure(name, version)

    def recv_graph(self, name, version, args, graph):
        self.graphs[name] = graph
        self.update_graph(name, version, args)

    def recv_graph_add(self, name, version, args, nodes):
        self.init_graph(name)
        self.graphs[name].add(nodes)
        self.update_graph(name, version, args)

    def recv_graph_del(self, name, version, args, nodes):
        self.init_graph(name)
        for node in nodes:
            self.graphs[name].remove(node)
        self.update_graph(name, version, args)

    def recv_graph_purge(self, name, version, args, nodes):
        if name in self.graphs:
            del self.graphs[name]
        if name in self.store:
            self.store.remove(name)
        self.update_requests()

    def run(self):
        for msg in self.src.events():
            # check to see if the graph has been reconfigured after update
            if msg.mtype == MsgTypes.Heartbeat:
                self.store.collect(self.node, msg.payload)
                # clear the data from the store after collecting
                self.store.clear()
                # check if there are graph updates
                while True:
                    try:
                        self.graph_comm.recv(False)
                    except zmq.Again:
                        break
                    except (AssertionError, TypeError) as e:
                        logger.exception("Failure encountered updating graph:")
                        self.report("error", e)
                        return 1
            elif msg.mtype == MsgTypes.Datagram:
                try:
                    for name, graph in self.graphs.items():
                        if graph:
                            graph_result = graph(msg.payload, color=Colors.Worker)
                            self.store.update(name, graph_result)
                except Exception as e:
                    logger.exception("%s: Failure encountered executing graph:", self.name)
                    self.report("error", e)
                    return 1
            else:
                self.store.send(msg)


def run_worker(num, num_workers, hb_period, source, collector_addr, graph_addr, msg_addr, flags=None):

    logger.info('Starting worker # %d, sending to collector at %s', num, collector_addr)

    if source is not None:
        src_type = source[0]
        if isinstance(source[1], dict):
            src_cfg = source[1]
        else:
            try:
                with open(source[1], 'r') as cnf:
                    src_cfg = json.load(cnf)
            except OSError:
                logger.exception("worker%03d: problem opening json file:", num)
                return 1
            except json.decoder.JSONDecodeError:
                logger.exception("worker%03d: problem parsing json file (%s):", num, source[1])
                return 1
    else:
        src_type = Defaults.SourceType
        src_cfg = Defaults.SourceConfig

    src_cls = Source.find_source(src_type)
    if src_cls is not None:
        src = src_cls(num,
                      num_workers,
                      hb_period,
                      src_cfg,
                      flags)
    else:
        logger.critical("worker%03d: unknown data source type: %s", num, source[0])
        return 1
    with Worker(num, src, collector_addr, graph_addr, msg_addr) as worker:
        return worker.run()


def main():
    parser = argparse.ArgumentParser(description='AMII Worker App')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
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
        default=Ports.NodeCollector,
        help='port for node collector (default: %d)' % Ports.NodeCollector
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
        '-f',
        '--flags',
        nargs='*',
        default=[],
        help='extra flags as key=value pairs that are passed to the data source'
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

    parser.add_argument(
        'source',
        nargs='?',
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, random://test.json, psana://exp=xcsdaq13:run=14)'
    )

    args = parser.parse_args()
    collector_addr = "tcp://localhost:%d" % args.collector
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)
    msg_addr = "tcp://%s:%d" % (args.host, args.message)
    flags = {}

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        for flag in args.flags:
            try:
                key, value = flag.split('=')
                flags[key] = value
            except ValueError:
                logger.exception("Problem parsing data source flag %s", flag)

        if args.source is not None:
            src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
            if src_url_match:
                src_cfg = src_url_match.groups()
            else:
                logger.critical("Invalid data source config string: %s", args.source)
                return 1
        else:
            src_cfg = None

        run_worker(args.node_num,
                   args.num_workers,
                   args.heartbeat,
                   src_cfg,
                   collector_addr,
                   graph_addr,
                   msg_addr,
                   flags)

        return 0
    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
