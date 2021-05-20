#!/usr/bin/env python
import os
import sys
import logging
import argparse
import time
import collections
import datetime as dt
import ami.multiproc as mp
from ami.worker import run_worker, parse_args
from ami import LogConfig, Defaults
from ami.comm import Ports, Colors, Node, Collector, TransitionBuilder, EventBuilder
from ami.data import MsgTypes, Transitions


logger = logging.getLogger(__name__)


class GraphCollector(Node, Collector):
    def __init__(self, node, base_name, num_workers, color, collector_addr, downstream_addr, graph_addr,
                 msg_addr, prometheus_dir, hutch):
        Node.__init__(self, node, graph_addr, msg_addr, prometheus_dir=prometheus_dir, hutch=hutch)
        Collector.__init__(self, collector_addr, ctx=self.ctx, hutch=hutch)
        self.base_name = base_name
        self.num_workers = num_workers
        self.transitions = TransitionBuilder(self.num_workers, downstream_addr, self.ctx)
        self.store = EventBuilder(self.num_workers, 10, color, downstream_addr, self.ctx)
        self.sender = 'worker%03d' if color == 'localCollector' else 'localCollector%03d'
        self.pickers = {}
        self.strategies = {}
        self.heartbeat_time = collections.defaultdict(lambda: 0)

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

    def flush(self, configure):
        try:
            if configure:
                self.store.flush(self.node, drop=True)
        except Exception as e:
            logger.exception("%s: Failure encountered while flushing store", self.name)
            self.report("error", e)

    def begin_run(self):
        try:
            self.store.begin_run()
        except Exception as e:
            logger.exception("%s: Failure encountered while beginning run", self.name)
            self.report("error", e)

    def end_run(self):
        try:
            self.store.end_run()
        except Exception as e:
            logger.exception("%s: Failure encountered while ending run %d", self.name)
            self.report("error", e)

    def begin_step(self, step):
        try:
            self.store.begin_step(step)
        except Exception as e:
            logger.exception("%s: Failure encountered while beginning step %d", self.name, step)
            self.report("error", e)

    def end_step(self, step):
        try:
            self.store.end_step(step)
        except Exception as e:
            logger.exception("%s: Failure encountered while ending step %d", self.name, step)
            self.report("error", e)

    def eb_id(self, identity):
        return identity - (self.node * self.num_workers)

    def report_times(self, times, name, heartbeat):
        if times:
            self.report("profile", {'graph': name,
                                    'heartbeat': heartbeat,
                                    'times': times,
                                    'version': self.store.version(name)})

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
            self.transitions.update(msg.payload.ttype, self.eb_id(msg.identity), msg.payload.payload)
            if self.transitions.ready(msg.payload.ttype):
                self.transitions.complete(msg.payload.ttype, self.node)
                if msg.payload.ttype == Transitions.Configure:
                    self.flush(True)
                    self.begin_run()
                elif msg.payload.ttype == Transitions.Unconfigure:
                    self.flush(False)
                    self.end_run()
                elif msg.payload.ttype == Transitions.BeginStep:
                    self.begin_step(msg.payload.payload)
                elif msg.payload.ttype == Transitions.EndStep:
                    self.end_step(msg.payload.payload)

            self.event_counter.labels(self.hutch, 'Transition', self.name).inc()
        elif msg.mtype == MsgTypes.Datagram:
            latency = dt.datetime.now() - dt.datetime.fromtimestamp(msg.heartbeat.timestamp)
            self.event_latency.labels(self.hutch, self.sender % msg.identity,
                                      self.name).set(latency.total_seconds())
            datagram_start = time.time()
            self.store.update(msg.name, msg.heartbeat, self.eb_id(msg.identity), msg.version, msg.payload)
            if self.store.ready(msg.name, msg.heartbeat):
                try:
                    # prune entries older than the current heartbeat
                    pruned_times, pruned_size = self.store.prune(msg.name, self.node, msg.heartbeat)
                    if pruned_size:
                        self.event_counter.labels(self.hutch, 'Pruned Heartbeat', self.name).inc()
                        self.event_size.labels(self.hutch, self.name).set(pruned_size)
                    # complete the current heartbeat
                    times, size = self.store.complete(msg.name, msg.heartbeat, self.node)

                    # times = self.store.complete(msg.name, msg.heartbeat, self.node)
                    # self.report_times(times, msg.name, msg.heartbeat)

                    self.event_counter.labels(self.hutch, 'Heartbeat', self.name).inc()
                    self.heartbeat_time[msg.heartbeat.identity] += time.time() - datagram_start
                    heartbeat_time = self.heartbeat_time.pop(msg.heartbeat.identity, 0)
                    self.event_time.labels(self.hutch, 'Heartbeat', self.name).set(heartbeat_time)
                    self.event_size.labels(self.hutch, self.name).set(size)
                except Exception as e:
                    e.graph_name = msg.name
                    logger.exception("%s: Failure encountered while executing graph %s:", self.name, msg.name)
                    self.report("error", e)
                    logger.error("%s: Purging graph (%s v%d)", self.name, msg.name, self.store.version(msg.name))
                    self.store.destroy(msg.name)
                    self.report("purge", msg.name)
            else:
                # prune older entries from the event builder
                pruned_times, pruned_size = self.store.prune(msg.name, self.node)
                if pruned_size:
                    self.event_counter.labels(self.hutch, 'Pruned Heartbeat', self.name).inc()
                    self.event_size.labels(self.hutch, self.name).set(pruned_size)
                    self.heartbeat_time.pop(msg.heartbeat.identity, 0)

            self.heartbeat_time[msg.heartbeat.identity] += time.time() - datagram_start


def run_collector(node_num, base_name, num_contribs, color,
                  collector_addr, upstream_addr, graph_addr, msg_addr,
                  prometheus_dir, hutch):
    logger.info('Starting collector on node # %d PID: %d', node_num, os.getpid())
    with GraphCollector(
            node_num,
            base_name,
            num_contribs,
            color,
            collector_addr,
            upstream_addr,
            graph_addr,
            msg_addr,
            prometheus_dir, hutch) as collector:
        collector.start_prometheus()
        return collector.run()


def run_node_collector(node_num, num_contribs,
                       collector_addr, upstream_addr, graph_addr, msg_addr,
                       prometheus_dir, hutch):
    return run_collector(node_num,
                         "localCollector%03d",
                         num_contribs,
                         Colors.LocalCollector,
                         collector_addr,
                         upstream_addr,
                         graph_addr,
                         msg_addr,
                         prometheus_dir,
                         hutch)


def run_global_collector(node_num, num_contribs,
                         collector_addr, upstream_addr, graph_addr, msg_addr,
                         prometheus_dir, hutch):
    return run_collector(node_num,
                         "globalCollector%03d",
                         num_contribs,
                         Colors.GlobalCollector,
                         collector_addr,
                         upstream_addr,
                         graph_addr,
                         msg_addr,
                         prometheus_dir,
                         hutch)


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

    subparsers = parser.add_subparsers(help='spawn workers', dest='worker')
    worker_subparser = subparsers.add_parser('worker', help='worker arguments')

    worker_subparser.add_argument(
        'source',
        nargs='?',
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, random://test.json, psana://exp=xcsdaq13:run=14)'
    )

    worker_subparser.add_argument(
        '-e',
        '--export',
        type=int,
        default=Ports.Export,
        help='port for receiving exported graph results (default: %d)' % Ports.Export
    )

    worker_subparser.add_argument(
        '-b',
        '--heartbeat',
        type=int,
        default=10,
        help='the heartbeat period (default: 10)'
    )

    worker_subparser.add_argument(
        '-f',
        '--flags',
        action='append',
        default=[],
        help='extra flags as key=value pairs that are passed to the data source'
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
    if args.worker:
        logging.basicConfig(format=LogConfig.FullFormat, level=log_level, handlers=log_handlers)
    else:
        logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        if color == Colors.LocalCollector:
            if args.worker:
                local_collector_addr = "tcp://localhost:%d" % args.collector
                export_addr = "tcp://%s:%d" % (args.host, args.export)
                flags, src_cfg = parse_args(args)
                for n in range(0, args.num_contribs):
                    worker = mp.Process(name='worker', target=run_worker,
                                        args=(args.node_num*args.num_contribs+n,
                                              args.num_contribs,
                                              args.heartbeat,
                                              src_cfg,
                                              local_collector_addr,
                                              graph_addr,
                                              msg_addr,
                                              export_addr,
                                              flags,
                                              args.prometheus_dir,
                                              args.hutch),
                                        daemon=True)
                    worker.start()

            return run_node_collector(args.node_num,
                                      args.num_contribs,
                                      collector_addr,
                                      downstream_addr,
                                      graph_addr,
                                      msg_addr,
                                      args.prometheus_dir,
                                      args.hutch)
        elif color == Colors.GlobalCollector:
            return run_global_collector(args.node_num,
                                        args.num_contribs,
                                        collector_addr,
                                        downstream_addr,
                                        graph_addr,
                                        msg_addr,
                                        args.prometheus_dir,
                                        args.hutch)
        else:
            logger.critical("Invalid option collector color '%s' chosen!", color)
            return 1

    except KeyboardInterrupt:
        logger.info("collector killed by user...")
        return 0


def node_main():
    return main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector)


def global_main():
    return main(Colors.GlobalCollector, Ports.FinalCollector, Ports.Results)


if __name__ == '__main__':
    sys.exit(main(Colors.LocalCollector, Ports.NodeCollector, Ports.FinalCollector))
