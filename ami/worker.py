#!/usr/bin/env python
import re
import sys
import zmq
import json
import dill
import logging
import argparse
import functools
from ami import LogConfig
from ami.comm import Ports, Colors, ResultStore, GraphReceiver
from ami.data import MsgTypes, Source


logger = logging.getLogger(__name__)


class Worker:
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
        self.graph = None

        self.graph_comm = GraphReceiver(graph_addr)
        for topic in ["graph", "add", "del"]:
            self.graph_comm.add_handler(topic, functools.partial(self.handle_graph, topic))
        self.graph_comm.add_command("config", self.send_configure)
        self.last_timestamp = 0
        self.heartbeat_period = heartbeat_period

    def send_configure(self):
        self.store.send(self.src.configure())

    def handle_graph(self, topic, num_work, num_col, version, payload):
        if topic == "graph":
            self.graph = dill.loads(payload)
            if self.graph is not None:
                self.graph.compile(num_workers=num_work, num_local_collectors=num_col)
                self.src.request(self.graph.sources)
                logger.info(self.src.requested_names)
                self.store.version = version
        elif topic == "add":
            add_update = dill.loads(payload)
            if self.graph is not None:
                self.graph.add(add_update)
                self.graph.compile(num_workers=num_work, num_local_collectors=num_col)
                self.src.request(self.graph.sources)
                self.store.version = version
            else:
                logger.error("worker%d: Add requested on empty graph", self.idnum)
        elif topic == "del":
            name = dill.loads(payload)
            if self.graph is not None:
                self.graph.remove(name)
                # check if the resulting graph is empty or not
                if self.graph:
                    self.graph.compile(num_workers=num_work, num_local_collectors=num_col)
                    self.src.request(self.graph.sources)
                else:
                    self.graph = None
                    self.src.request([])
                self.store.version = version
            else:
                logger.error("worker%d: Del requested on empty graph", self.idnum)
        else:
            logger.warn("worker%d: No handler for received topic: %s", self.idnum, topic)

    def check_heartbeat_boundary(self, timestamp):
        ret = (timestamp // self.heartbeat_period) > (self.last_timestamp // self.heartbeat_period)
        self.last_timestamp = timestamp
        return ret

    def run(self):
        for msg in self.src.events():
            # check to see if the graph has been reconfigured after update
            if msg.mtype == MsgTypes.Datagram:
                if self.check_heartbeat_boundary(msg.timestamp):
                    self.store.collect(self.idnum, msg.timestamp//self.heartbeat_period)
                    # clear the data from the store after collecting
                    self.store.clear()
                    # check if there are graph updates
                    graph_updated = False
                    while True:
                        try:
                            self.graph_comm.recv(False)
                            graph_updated = True
                        except zmq.Again:
                            break
                    if graph_updated:
                        logger.warn("worker%s: discarding event where graph changed", self.idnum)
                        continue
                try:
                    if self.graph is not None:
                        self.store.update(self.graph(msg.payload, color=Colors.Worker))
                except Exception:
                    logger.exception("worker%s: Failure encountered executing graph:", self.idnum)
                    return 1
            else:
                self.store.send(msg)


def run_worker(num, num_workers, hb_period, source, collector_addr, graph_addr, flags=None):

    logger.info('Starting worker # %d, sending to collector at %s', num, collector_addr)

    try:
        with open(source[1], 'r') as cnf:
            src_cfg = json.load(cnf)
    except OSError:
        logger.exception("worker%03d: problem opening json file:", num)
        return 1
    except json.decoder.JSONDecodeError:
        logger.exception("worker%03d: problem parsing json file (%s):", num, source[1])
        return 1

    src_cls = Source.find_source(source[0])
    if src_cls is not None:
        src = src_cls(num,
                      num_workers,
                      src_cfg,
                      flags)
    else:
        logger.critical("worker%03d: unknown data source type: %s", num, source[0])
        return 1
    worker = Worker(num, hb_period, src, collector_addr, graph_addr)
    return worker.run()


def main():
    parser = argparse.ArgumentParser(description='AMII Worker App')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
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
        metavar='SOURCE',
        help='data source configuration (exampes: static://test.json, random://test.json, psana://exp=xcsdaq13:run=14)'
    )

    args = parser.parse_args()
    collector_addr = "tcp://localhost:%d" % args.collector
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)
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

        src_url_match = re.match('(?P<prot>.*)://(?P<body>.*)', args.source)
        if src_url_match:
            src_cfg = src_url_match.groups()
        else:
            logger.critical("Invalid data source config string: %s", args.source)
            return 1

        run_worker(args.node_num, args.num_workers, args.heartbeat, src_cfg, collector_addr, graph_addr, flags)

        return 0
    except KeyboardInterrupt:
        logger.info("Worker killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
