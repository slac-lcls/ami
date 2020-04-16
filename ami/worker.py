#!/usr/bin/env python
import re
import sys
import zmq
import json
import logging
import argparse
import time
from ami import LogConfig, Defaults
from ami.comm import Ports, Colors, ResultStore, Node, AutoExport
from ami.data import MsgTypes, Source, Message, Transition, Transitions
from ami.graphkit_wrapper import Graph


logger = logging.getLogger(__name__)


class Worker(Node):
    def __init__(self, node, src, collector_addr, graph_addr, msg_addr, export_addr):
        """
        node : int
            a unique integer identifying this worker
        src : object
            object with an events() method that is an iterable (like psana.DataSource)
        """
        super(__class__, self).__init__(node, graph_addr, msg_addr, export_addr)

        self.src = src

        self.store = ResultStore(collector_addr, self.ctx)

        self.graph_comm.add_command("config", self.send_configure)
        self.graph_comm.add_handler("update_sources", self.update_sources)

        self.exports = {}

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
        if self.src:
            self.store.send(self.src.configure())
        else:
            self.store.send(Message(MsgTypes.Transition, self.node,
                                    Transition(Transitions.Configure, {})))

    def init_graph(self, name):
        if name not in self.graphs or self.graphs[name] is None:
            self.graphs[name] = Graph(name)

    def clear_graph(self, name):
        if name in self.graphs:
            self.graphs[name] = None
        if name in self.store:
            self.store.clear(name)
        self.update_requests()

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

    def recv_graph_exception(self, name, version, exception):
        logger.exception("%s: Failure encountered updating graph (%s v%d):",
                         self.name, name, self.store.version(name))
        self.report("error", "Failure updating graph: %s" % exception)
        logger.error("%s: Purging graph (%s v%d)", self.name, name, self.store.version(name))
        self.clear_graph(name)
        self.report("purge", name)

    def update_sources(self, name, version, args, src_cfg):
        src_type = src_cfg['type']
        hb_period = src_cfg['hb_period']
        num_workers = args['num_workers']
        logger.info("%s: Received source configuration", self.name)
        self.report("info", "Received source configuration")
        try:
            src_cls = Source.find_source(src_type)
            flags = {}
            self.src = src_cls(self.node, num_workers, hb_period, src_cfg, flags)
        except Exception as e:
            self.report("error", e)
            logger.error("%s: Error configuring source", self.name)

    def collect(self, heartbeat):
        # send the data from the store to collector
        self.store.collect(self.node, heartbeat)

        # update the profiler data
        if self.times:
            for name, exec_times in self.times.items():
                self.report("profile", {'graph': name,
                                        'heartbeat': heartbeat,
                                        'times': exec_times,
                                        'version': self.store.version(name)})

        if self.event_rate:
            self.event_rate['num_events'] = self.num_events
            self.report("event_rate", self.event_rate)
            self.event_rate = {}

        # clear the data from the store after collecting
        self.store.clear()

    def run(self):
        self.times = {}
        self.event_rate = {}
        self.num_events = 0

        while self.src is None:
            logger.info("%s: Waiting for source configuration", self.name)
            self.graph_comm.recv(True)

        for msg in self.src.events():

            # check to see if the graph has been reconfigured after update
            if msg.mtype == MsgTypes.Heartbeat:
                self.collect(msg.payload)

                # check if there are graph updates
                while True:
                    try:
                        self.graph_comm.recv(False)
                    except zmq.Again:
                        break

                while True:
                    try:
                        name, data = self.export_comm.recv(False)
                        self.exports[name] = {AutoExport.unmangle(k): v
                                              for k, v in data.items() if k in self.src.requested_names}
                    except zmq.Again:
                        break
            elif msg.mtype == MsgTypes.Datagram:
                for name, graph in self.graphs.items():
                    try:
                        if graph:
                            if name in self.exports:
                                msg.payload.update(self.exports[name])

                            start = time.time()
                            graph_result = graph(msg.payload, color=Colors.Worker)
                            stop = time.time()

                            self.store.update(name, graph_result)

                            if name not in self.event_rate:
                                self.event_rate[name] = []

                            self.event_rate[name].append(stop - start)

                            if name not in self.times:
                                self.times[name] = []

                            self.times[name].append(graph.times())
                    except Exception as e:
                        logger.exception("%s: Failure encountered while executing graph (%s, v%d):",
                                         self.name, name, self.store.version(name))
                        self.report("error", e)
                        logger.error("%s: Purging graph (%s v%d)", self.name, name, self.store.version(name))
                        self.clear_graph(name)
                        self.report("purge", name)

                self.num_events += 1
            elif msg.mtype == MsgTypes.Transition:
                if msg.payload.ttype == Transitions.Unconfigure:
                    if self.src.heartbeat is not None:
                        self.collect(self.src.heartbeat)

                # forward the transition
                self.store.send(msg)
            else:
                self.store.send(msg)


def run_worker(num, num_workers, hb_period, source, collector_addr, graph_addr, msg_addr, export_addr, flags=None):

    logger.info('Starting worker # %d, sending to collector at %s', num, collector_addr)

    src = None
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

    with Worker(num, src, collector_addr, graph_addr, msg_addr, export_addr) as worker:
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
        '-e',
        '--export',
        type=int,
        default=Ports.Export,
        help='port for receiving exported graph results (default: %d)' % Ports.Export
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
    export_addr = "tcp://%s:%d" % (args.host, args.export)
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

        return run_worker(args.node_num,
                          args.num_workers,
                          args.heartbeat,
                          src_cfg,
                          collector_addr,
                          graph_addr,
                          msg_addr,
                          export_addr,
                          flags)
    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
