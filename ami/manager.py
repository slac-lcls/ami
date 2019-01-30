#!/usr/bin/env python
import re
import sys
import zmq
import dill
import logging
import argparse
from ami import LogConfig
from ami.comm import Ports, Collector, Store
from ami.data import MsgTypes, Transitions
from ami.graphkit_wrapper import Graph


logger = logging.getLogger(__name__)


class Manager(Collector):
    """
    An AMI graph Manager is the control point for an
    active "tree" of workers. It is the final collection
    point for all results, broadcasts those results to
    clients (e.g. plots/GUIs), and handles requests for
    configuration changes to the graph.
    """

    def __init__(self, num_workers, num_nodes, results_addr, graph_addr, comm_addr, export_addr=None):
        """
        protocol right now only tells you how to communicate with workers
        """
        super(__class__, self).__init__(results_addr)
        self.num_workers = num_workers
        self.num_nodes = num_nodes
        self.partition = []
        self.feature_store = Store()
        self.feature_req = re.compile("fetch:(?P<name>.*)")
        self.graph = None
        self.version = 0

        if export_addr is None:
            self.export = None
        else:
            self.export = self.ctx.socket(zmq.PUB)
            self.export.bind(export_addr)

        self.comm = self.ctx.socket(zmq.REP)
        self.comm.bind(comm_addr)
        self.register(self.comm, self.client_request)
        self.graph_comm = self.ctx.socket(zmq.XPUB)
        self.graph_comm.setsockopt(zmq.XPUB_VERBOSE, True)
        self.graph_comm.bind(graph_addr)
        self.register(self.graph_comm, self.graph_request)

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Datagram:
            self.feature_store.update(msg.payload)
            self.feature_store.version = msg.version
            # export the collector data to epics
            self.export_data(msg.payload)
            if self.export is not None:
                self.export.send_string('data', zmq.SNDMORE)
                self.export.send_pyobj(msg.payload)
        elif (msg.mtype == MsgTypes.Transition) and (msg.payload.ttype == Transitions.Configure):
            self.partition = msg.payload.payload
            # export the partition info to epics
            self.export_graph()

    @property
    def names(self):
        name_set = set(self.partition)
        if self.graph is not None:
            name_set.update(self.graph.names)
        return name_set

    @property
    def features(self):
        return self.feature_store.types

    def feature_request(self, request):
        matched = self.feature_req.match(request)
        if matched:
            if matched.group('name') in self.feature_store.namespace:
                self.comm.send_string('ok', zmq.SNDMORE)
                self.comm.send_pyobj(self.feature_store.get(matched.group('name')))
            else:
                self.comm.send_string('error')
            return True
        else:
            return False

    def client_request(self):
        request = self.comm.recv_string()
        # check if it is a feature request
        if not self.feature_request(request):
            getattr(self, "cmd_%s" % request, self.cmd_unknown)()

    def compile_graph(self):
        self.graph.compile(num_workers=self.num_workers, num_local_collectors=self.num_nodes)

    def cmd_unknown(self):
        self.comm.send_string('error')

    def cmd_get_versions(self):
        self.comm.send_pyobj((self.version, self.feature_store.version))

    def cmd_get_graph_version(self):
        self.comm.send_pyobj(self.version)

    def cmd_get_features_version(self):
        self.comm.send_pyobj(self.feature_store.version)

    def cmd_get_features(self):
        self.comm.send_pyobj(self.features)

    def cmd_get_names(self):
        self.comm.send_pyobj(self.names)

    def cmd_clear_graph(self):
        self.graph = None
        self.publish_graph("graph", dill.dumps(self.graph))

    def cmd_reset_features(self):
        self.feature_store.clear()
        self.comm.send_string('ok')

    def cmd_get_graph(self):
        self.comm.send(dill.dumps(self.graph))

    def cmd_add_graph(self):
        raw_add = self.comm.recv()
        if self.graph is None:
            self.graph = Graph("manager_graph")
            self.graph.add(dill.loads(raw_add))
            self.publish_graph("graph", dill.dumps(self.graph))
        else:
            self.graph.add(dill.loads(raw_add))
            self.publish_graph("add", raw_add)
        self.compile_graph()

    def cmd_del_graph(self):
        name = self.comm.recv()
        if self.graph is not None:
            self.graph.remove(dill.loads(name))
            # Check if the resulting graph is non-empty
            if self.graph:
                self.compile_graph()
            else:
                # if the graph is empty remove it
                self.graph = None
        self.publish_graph("del", name)

    def cmd_set_graph(self):
        raw_graph = self.comm.recv()
        self.graph = dill.loads(raw_graph)
        # Check if the graph is non-empty
        if self.graph:
            self.compile_graph()
        else:
            self.graph = None
            raw_graph = dill.dumps(self.graph)
        self.publish_graph("graph", raw_graph)

    def publish_graph(self, topic, graph):
        logger.info("manager: sending requested graph...")
        try:
            self.version += 1
            self.graph_comm.send_string(topic, zmq.SNDMORE)
            self.graph_comm.send_pyobj((self.num_workers, self.num_nodes, self.version), zmq.SNDMORE)
            self.graph_comm.send(graph)
            self.export_graph()
            logger.info("manager: sending of graph (v%d) completed", self.version)
            self.comm.send_string('ok')
        except Exception:
            logger.exception("manager: failed to send graph (v%d) -", self.version)
            self.comm.send_string('error')

    def graph_request(self):
        request = self.graph_comm.recv_string()

        if request == "\x01":
            self.graph_comm.send_string("graph", zmq.SNDMORE)
            self.graph_comm.send_pyobj((self.num_workers, self.num_nodes, self.version), zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(self.graph))

    def export_graph(self):
        if self.export is not None:
            data = {
                'names': self.names,
                'version': self.version,
                'store': self.feature_store.version,
                'dill': dill.dumps(self.graph)
            }
            self.export.send_string('graph', zmq.SNDMORE)
            self.export.send_pyobj(data)

    def export_data(self, data):
        if self.export is not None:
            self.export.send_string('data', zmq.SNDMORE)
            self.export.send_pyobj(data)


def run_manager(num_workers, num_nodes, results_addr, graph_addr, comm_addr, export_addr=None):
    manager = Manager(num_workers, num_nodes, results_addr, graph_addr, comm_addr, export_addr)
    return manager.run()


def main():
    parser = argparse.ArgumentParser(description='AMII Manager App')

    parser.add_argument(
        '-H',
        '--host',
        default='*',
        help='interface the AMII manager listens on (default: all)'
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=Ports.Comm,
        help='port for GUI-Manager communication (default: %d)' % Ports.Comm
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
        '--num-nodes',
        type=int,
        default=1,
        help='number of nodes (a.k.a local collector processes) (default: 1)'
    )

    parser.add_argument(
        '-g',
        '--graph',
        type=int,
        default=Ports.Graph,
        help='port for graph communication (default: %d)' % Ports.Graph
    )

    parser.add_argument(
        '-e',
        '--export',
        type=int,
        default=Ports.Export,
        help='port for sending data to the export service (default: %d)' % Ports.Export
    )

    parser.add_argument(
        '-r',
        '--results',
        type=int,
        default=Ports.Results,
        help='port for receiving results (default: %d)' % Ports.Results
    )

    parser.add_argument(
        '-E',
        '--enable-export',
        action='store_true',
        help='enable the data export service'
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

    results_addr = "tcp://%s:%d" % (args.host, args.results)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)
    comm_addr = "tcp://%s:%d" % (args.host, args.port)
    if args.enable_export:
        export_addr = "tcp://%s:%d" % (args.host, args.export)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_manager(args.num_workers, args.num_nodes, results_addr, graph_addr, comm_addr, export_addr)
    except KeyboardInterrupt:
        logger.info("Manager killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
