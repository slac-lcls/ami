#!/usr/bin/env python
import re
import sys
import zmq
import dill
import argparse
from ami.comm import Ports, Collector, Store
from ami.data import MsgTypes, Transitions
from ami.graphkit_wrapper import Graph


class Manager(Collector):
    """
    An AMI graph Manager is the control point for an
    active "tree" of workers. It is the final collection
    point for all results, broadcasts those results to
    clients (e.g. plots/GUIs), and handles requests for
    configuration changes to the graph.
    """

    def __init__(self, num_workers, num_nodes, results_addr, graph_addr, comm_addr):
        """
        protocol right now only tells you how to communicate with workers
        """
        super(__class__, self).__init__(results_addr)
        self.num_workers = num_workers
        self.num_nodes = num_nodes
        self.partition = []
        self.feature_store = Store()
        self.feature_req = re.compile("feature:(?P<name>.*)")
        self.graph = None

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
        elif (msg.mtype == MsgTypes.Transition) and (msg.payload.ttype == Transitions.Allocate):
            self.partition = msg.payload.payload
        return

    @property
    def features(self):
        feature_set = set(self.partition)
        if self.graph is not None:
            feature_set.update(self.graph.names)
        return feature_set

    @property
    def types(self):
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

    def cmd_get_features(self):
        self.comm.send_pyobj(self.features)

    def cmd_get_types(self):
        self.comm.send_pyobj(self.types)

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
        name = self.comm.recv_string()
        if self.graph is not None:
            self.graph.remove(name)
        # Check if the resulting graph is non-empty
        if self.graph:
            self.compile_graph()
        else:
            # if the graph is empty remove it
            self.graph = None

    def cmd_set_graph(self):
        raw_graph = self.comm.recv()
        self.graph = dill.loads(raw_graph)
        self.publish_graph("graph", raw_graph)
        self.compile_graph()

    def publish_graph(self, topic, graph):
        print("manager: sending requested graph...")
        try:
            self.graph_comm.send_string(topic, zmq.SNDMORE)
            self.graph_comm.send_pyobj((self.num_workers, self.num_nodes), zmq.SNDMORE)
            self.graph_comm.send(graph)
            print("manager: sending of graph completed")
            self.comm.send_string('ok')
        except Exception as exp:
            print("manager: failed to send graph -", exp)
            self.comm.send_string('error')

    def graph_request(self):
        request = self.graph_comm.recv_string()

        if request == "\x01graph":
            self.graph_comm.send_string("graph", zmq.SNDMORE)
            self.graph_comm.send_pyobj((self.num_workers, self.num_nodes), zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(self.graph))


def run_manager(num_workers, num_nodes, results_addr, graph_addr, comm_addr):
    manager = Manager(num_workers, num_nodes, results_addr, graph_addr, comm_addr)
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
        '-r',
        '--results',
        type=int,
        default=Ports.Results,
        help='port for receiving results (default: %d)' % Ports.Results
    )

    args = parser.parse_args()

    results_addr = "tcp://%s:%d" % (args.host, args.results)
    graph_addr = "tcp://%s:%d" % (args.host, args.graph)
    comm_addr = "tcp://%s:%d" % (args.host, args.port)

    try:
        return run_manager(args.num_workers, args.num_nodes, results_addr, graph_addr, comm_addr)
    except KeyboardInterrupt:
        print("Manager killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
