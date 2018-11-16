#!/usr/bin/env python
import re
import sys
import zmq
import dill
import argparse
from ami.comm import Ports, Collector, Store
from ami.data import MsgTypes
from ami.graphkit_wrapper import Graph


class Manager(Collector):
    """
    An AMI graph Manager is the control point for an
    active "tree" of workers. It is the final collection
    point for all results, broadcasts those results to
    clients (e.g. plots/GUIs), and handles requests for
    configuration changes to the graph.
    """

    def __init__(self, results_addr, graph_addr, comm_addr):
        """
        protocol right now only tells you how to communicate with workers
        """
        super(__class__, self).__init__(results_addr)
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
            print(msg.payload)
            self.feature_store.update(msg.payload)
        return

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
            if request == 'get_features':
                self.comm.send_pyobj(self.features)
            elif request == 'clear_graph':
                self.graph = None
                if self.apply_graph():
                    self.comm.send_string('ok')
                else:
                    self.comm.send_string('error')
            elif request == 'reset_features':
                self.feature_store.clear()
                self.comm.send_string('ok')
            elif request == 'get_graph':
                self.send_graph()
            elif request == 'set_graph':
                self.graph = self.recv_graph()
                if self.apply_graph():
                    self.comm.send_string('ok')
                else:
                    self.comm.send_string('error')
            else:
                self.comm.send_string('error')

    def send_graph(self):
        self.comm.send(dill.dumps(self.graph))

    def recv_graph(self):
        return dill.loads(self.comm.recv())  # zmq for now, could be EPICS in future?

    def apply_graph(self):
        print("manager: sending requested graph...")
        try:
            self.graph_comm.send_string("graph", zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(self.graph))
        except Exception as exp:
            print("manager: failed to send graph -", exp)
            return False
        print("manager: sending of graph completed")
        return True

    def graph_request(self):
        request = self.graph_comm.recv_string()

        if request == "\x01graph":
            self.graph_comm.send_string("graph", zmq.SNDMORE)
            self.graph_comm.send_pyobj(self.graph)


def run_manager(results_addr, graph_addr, comm_addr):
    manager = Manager(results_addr, graph_addr, comm_addr)
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
        return run_manager(results_addr, graph_addr, comm_addr)
    except KeyboardInterrupt:
        print("Manager killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
