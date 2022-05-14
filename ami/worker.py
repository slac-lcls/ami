#!/usr/bin/env python
import os
import re
import sys
import zmq
import json
import logging
import argparse
import time
import prometheus_client as pc
from ami import LogConfig, Defaults
from ami.comm import BasePort, Ports, Colors, ResultStore, Node, AutoExport
from ami.data import MsgTypes, Source, Message, Transition, Transitions
from ami.graphkit_wrapper import Graph


logger = logging.getLogger(__name__)


class Worker(Node):
    def __init__(self, node, src, collector_addr, graph_addr, msg_addr, export_addr, prometheus_dir,
                 prometheus_port, hutch):
        """
        node : int
            a unique integer identifying this worker
        src : object
            object with an events() method that is an iterable (like psana.DataSource)
        """
        super().__init__(node, graph_addr, msg_addr, export_addr, prometheus_dir=prometheus_dir,
                         prometheus_port=prometheus_port, hutch=hutch)

        self.src = src
        self.pending_src = False
        self.store = ResultStore(collector_addr, self.ctx)

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

    def init_graph(self, name):
        if name not in self.graphs or self.graphs[name] is None:
            self.graphs[name] = Graph(name)

    def clear_graph(self, name):
        if name in self.graphs:
            self.graphs[name] = None
        if name in self.store:
            self.store.clear(name)
        # if name in self.times:
        #     del self.times[name]
        self.update_requests()

    def update_requests(self):
        requests = set()
        for graph in self.graphs.values():
            if graph is not None:
                requests.update(graph.sources)
        if self.src is not None:
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
        # if name is self.times:
        #     del self.times[name]
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
        try:
            src_cls = Source.find_source(src_type)
            flags = {}
            if self.src is None:
                self.report("info", "Updated source configuration")
                self.src = src_cls(self.node, num_workers, hb_period, src_cfg, flags)
                self.pending_src = False
            else:
                self.pending_src = True
                self.report("info", "Pending source configuration")
                self.source_args = {'name': name, 'version': version, 'args': args, 'src_cfg': src_cfg}
        except Exception as e:
            self.report("error", e)
            logger.error("%s: Error configuring source", self.name)

    def collect(self, heartbeat):
        # send the data from the store to collector
        size = self.store.collect(self.node, heartbeat)

        # update the profiler data
        # if self.times:
        #     for name, exec_times in self.times.items():
        #         self.report("profile", {'graph': name,
        #                                 'heartbeat': heartbeat,
        #                                 'times': exec_times,
        #                                 'version': self.store.version(name)})
        #     self.times = {}

        if self.event_rate:
            self.event_rate['num_events'] = self.num_events
            self.report("event_rate", self.event_rate)
            self.event_rate = {}

        # clear the data from the store after collecting
        self.store.clear()
        return size

    def run(self):
        # self.times = {}
        self.event_rate = {}
        self.num_events = 1
        self.start_prometheus()

        while self.src is None:
            logger.info("%s: Waiting for source configuration", self.name)
            self.graph_comm.recv(True)

        event_counter = pc.Counter('ami_event_count', 'Event Counter', ['hutch', 'type', 'process'])
        event_time = pc.Gauge('ami_event_time_secs', 'Event Time', ['hutch', 'type', 'process'])
        event_size = pc.Gauge('ami_event_size_bytes', 'Event Size', ['hutch', 'process'])

        idle_start = time.time()
        idle_stop = time.time()
        heartbeat_time = 0

        while True:
            for msg in self.src.events():
                idle_stop = time.time()
                event_time.labels(self.hutch, 'Idle', self.name).set(idle_stop - idle_start)

                # check to see if the graph has been reconfigured after update
                if msg.mtype == MsgTypes.Heartbeat:
                    heartbeat_start = time.time()
                    size = self.collect(msg.payload)

                    for name, graph in self.graphs.items():
                        if graph:
                            graph.heartbeat_finished()

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

                    event_counter.labels(self.hutch, 'Heartbeat', self.name).inc()

                    if self.pending_src:
                        break

                    heartbeat_stop = time.time()
                    heartbeat_time += heartbeat_stop - heartbeat_start
                    event_time.labels(self.hutch, 'Heartbeat', self.name).set(heartbeat_time)
                    event_size.labels(self.hutch, self.name).set(size)
                    heartbeat_time = 0

                elif msg.mtype == MsgTypes.Datagram:
                    datagram_start = time.time()

                    if any(v is None for k, v in msg.payload.items()):
                        event_counter.labels(self.hutch, 'Partial', self.name).inc()

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

                                self.event_rate[name].append((start, stop))

                                # if name not in self.times:
                                #     self.times[name] = []
                                # self.times[name].append((start, stop, graph.times()))

                        except Exception as e:
                            e.graph_name = name
                            logger.exception("%s: Failure encountered while executing graph (%s, v%d):",
                                             self.name, name, self.store.version(name))
                            self.report("error", e)
                            logger.error("%s: Purging graph (%s v%d)", self.name, name, self.store.version(name))
                            self.clear_graph(name)
                            self.report("purge", name)

                    self.num_events += 1
                    event_counter.labels(self.hutch, 'Datagram', self.name).inc()
                    datagram_duration = time.time() - datagram_start
                    event_time.labels(self.hutch, 'Datagram', self.name).set(datagram_duration)
                    heartbeat_time += datagram_duration

                elif msg.mtype == MsgTypes.Transition:
                    if msg.payload.ttype == Transitions.Configure:
                        for name, graph in self.graphs.items():
                            if graph:
                                graph.reset()
                                graph.begin_run(color=Colors.Worker)
                    elif msg.payload.ttype == Transitions.Unconfigure:
                        if self.src.heartbeat is not None:
                            self.collect(self.src.heartbeat)
                        for name, graph in self.graphs.items():
                            if graph:
                                graph.end_run(color=Colors.Worker)
                    elif msg.payload.ttype == Transitions.BeginStep:
                        for name, graph in self.graphs.items():
                            if graph:
                                graph.begin_step(msg.payload.payload, color=Colors.Worker)
                    elif msg.payload.ttype == Transitions.EndStep:
                        for name, graph in self.graphs.items():
                            if graph:
                                graph.end_step(msg.payload.payload, color=Colors.Worker)

                    # forward the transition
                    self.store.send(msg)
                    event_counter.labels(self.hutch, 'Transition', self.name).inc()
                else:
                    self.store.send(msg)
                    event_counter.labels(self.hutch, 'Other', self.name).inc()

                idle_start = time.time()

            if self.pending_src:
                msg = self.src.unconfigure()
                self.store.send(msg)
                self.src = None
                self.update_sources(**self.source_args)


def run_worker(num, num_workers, hb_period, source, collector_addr, graph_addr, msg_addr, export_addr,
               flags=None, prometheus_dir=None, prometheus_port=None, hutch=None):

    logger.info('Starting worker # %d, sending to collector at %s PID: %d', num, collector_addr, os.getpid())

    src = None
    if source is not None:
        src_type = source[0]
        if isinstance(source[1], dict):
            src_cfg = source[1]
        elif source[1].endswith('.json'):
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
            src_cfg = {}
            cfg = source[1].split(',')
            for c in cfg:
                k, v = c.split('=')
                src_cfg[k] = v

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

    with Worker(num, src, collector_addr, graph_addr, msg_addr, export_addr, prometheus_dir, prometheus_port,
                hutch) as worker:
        return worker.run()


def parse_args(args):
    flags = {}
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

    return flags, src_cfg


def main():
    parser = argparse.ArgumentParser(description='AMII Worker App')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=BasePort,
        help='base port for ami (default: %d) reserves next 10 consecutive ports' % BasePort
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
        action='append',
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
        '--prometheus-port',
        type=int,
        default=Ports.Prometheus,
        help='port for prometheus'
    )

    parser.add_argument(
        '--prometheus-dir',
        help='directory for prometheus configuration',
        default=None
    )

    parser.add_argument(
        '--hutch',
        help='hutch for prometheus label',
        default=None
    )

    parser.add_argument(
        'source',
        nargs='?',
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, random://test.json, psana://exp=xcsdaq13:run=14)'
    )

    args = parser.parse_args()
    collector_addr = "tcp://localhost:%d" % args.port + Ports.NodeCollector
    graph_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Graph)
    msg_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Message)
    export_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Export)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        flags, src_cfg = parse_args(args)

        return run_worker(args.node_num,
                          args.num_workers,
                          args.heartbeat,
                          src_cfg,
                          collector_addr,
                          graph_addr,
                          msg_addr,
                          export_addr,
                          flags,
                          args.prometheus_dir,
                          args.prometheus_port,
                          args.hutch)
    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
