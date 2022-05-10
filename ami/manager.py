#!/usr/bin/env python
import re
import os
import sys
import zmq
import dill
import logging
import collections
import argparse
import json
import socket
import time
import datetime as dt
import prometheus_client as pc
from ami import LogConfig
from ami.comm import BasePort, Ports, AutoExport, Collector, Store, ZMQ_TOPIC_DELIM
from ami.data import MsgTypes, Transitions, Serializer, Deserializer
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

    def __init__(self,
                 num_workers,
                 num_nodes,
                 results_addr,
                 graph_addr,
                 comm_addr,
                 msg_addr,
                 info_addr,
                 export_addr,
                 view_addr,
                 prometheus_dir,
                 hutch):
        """
        protocol right now only tells you how to communicate with workers
        """
        super().__init__(results_addr, hutch=hutch)
        self.name = "manager"
        self.num_workers = num_workers
        self.num_nodes = num_nodes
        self.heartbeats = {}
        self.partition = {}
        self.feature_stores = {}
        self.feature_req = re.compile(r"(?P<type>fetch):(?P<name>.*)")
        self.view_req = re.compile(r"view:(?P<graph>.*):(?P<name>.*)")
        self.graphs = {}
        self.paths = collections.defaultdict(set)
        self.versions = {}  # { graph_name : version_number}
        self.purged = set()
        self.purged_graphs = {}  # { graph_name : dill.dumps(graph) }
        self.global_cmds = {"list_graphs"}
        self.no_auto_create_cmds = {"create_graph", "destroy_graph"}

        self.export = self.ctx.socket(zmq.XPUB)
        self.export.setsockopt(zmq.XPUB_VERBOSE, True)
        self.export.bind(export_addr)
        self.register(self.export, self.export_request)

        self.serializer = Serializer()
        self.deserializer = Deserializer()
        self.comm = self.ctx.socket(zmq.REP)  # receives commands from client
        self.comm.bind(comm_addr)
        self.register(self.comm, self.client_request)

        self.graph_comm = self.ctx.socket(zmq.XPUB)  # pushes graph to workers/collectors
        self.graph_comm.setsockopt(zmq.XPUB_VERBOSE, True)
        self.graph_comm.bind(graph_addr)
        self.register(self.graph_comm, self.graph_request)

        self.info_comm = self.ctx.socket(zmq.XPUB)  # status messages from manager to client
        self.info_comm.setsockopt(zmq.XPUB_VERBOSE, True)
        self.info_comm.bind(info_addr)
        self.register(self.info_comm, self.info_request)

        self.node_msg_comm = self.ctx.socket(zmq.PULL)  # receives status from workers/collectors to push to info
        self.node_msg_comm.bind(msg_addr)
        self.register(self.node_msg_comm, self.node_request)

        self.view_comm = self.ctx.socket(zmq.XPUB)  # exports plot data to clients
        self.view_comm.setsockopt(zmq.XPUB_VERBOSE, True)
        self.view_comm.bind(view_addr)
        self.register(self.view_comm, self.view_request)

        self.prometheus_dir = prometheus_dir

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.ctx.destroy()

    def process_msg(self, msg):
        if msg.mtype == MsgTypes.Datagram:
            latency = dt.datetime.now() - dt.datetime.fromtimestamp(msg.heartbeat.timestamp)
            self.event_latency.labels(self.hutch, 'globalCollector%03d' % msg.identity,
                                      self.name).set(latency.total_seconds())
            datagram_start = time.time()
            if msg.name not in self.feature_stores:
                if msg.name in self.purged:
                    logger.debug("Received data from deleted graph '%s'!", msg.name)
                else:
                    logger.warning("Received data from unknown graph '%s'!", msg.name)
            elif msg.version > self.versions[msg.name]:
                logger.debug("Received data from version %d of the graph '%s' which is newer the actual version %d",
                             msg.version,
                             msg.name,
                             self.versions[msg.name])
            elif msg.version < self.feature_stores[msg.name].version:
                logger.warning("Received data from version %d of the graph '%s' when version %d or newer was expected!",
                               msg.version,
                               msg.name,
                               self.feature_stores[msg.name].version)
            else:
                old_names = self.feature_stores[msg.name].names
                self.feature_stores[msg.name].update(msg.payload)
                if msg.version > self.feature_stores[msg.name].version:
                    self.feature_stores[msg.name].version = msg.version
                    self.export_store(msg.name)
                elif old_names != self.feature_stores[msg.name].names:
                    # if there are new entries in the store notify the export layer
                    self.export_store(msg.name)
                # export the collector data to epics
                self.export_data(msg.name, msg.payload)
                # update the latest heartbeat indicator
                self.heartbeats[msg.name] = msg.heartbeat
                # export the heartbeat to epics
                self.export_heartbeat(msg.name)
                # export data for viewing in the AMI GUI
                self.export_view(msg.name, keys=msg.payload.keys())

            self.event_counter.labels(self.hutch, 'Heartbeat', self.name).inc()
            self.event_time.labels(self.hutch, 'Heartbeat', self.name).set(time.time() - datagram_start)
        elif (msg.mtype == MsgTypes.Transition) and (msg.payload.ttype == Transitions.Configure):
            changed = (msg.payload.payload != self.partition)
            self.partition = msg.payload.payload
            # if the partition has changed then publish a message about this
            if changed:
                # publish the updated partition over the info socket
                self.publish_message("sources", "manager", dill.dumps(self.partition))
            # export the partition info to epics
            self.export_config()

    @property
    def compiler_args(self):
        return {'num_workers': self.num_workers, 'num_local_collectors': self.num_nodes}

    def exists(self, name):
        return all(name in val for val in [self.feature_stores, self.graphs, self.versions, self.heartbeats])

    def create(self, name):
        if self.exists(name):
            raise ValueError("Graph with the name '%s' already exists" % name)
        else:
            self.feature_stores[name] = Store()
            self.graphs[name] = None
            self.versions[name] = 0
            self.heartbeats[name] = None
            # notify export of the new graph
            self.export_create(name)
            # remove the graph name from the purged list if there
            if name in self.purged:
                self.purged.remove(name)

    def delete(self, name):
        if self.exists(name):
            del self.feature_stores[name]
            del self.graphs[name]
            del self.versions[name]
            del self.heartbeats[name]
            # notify export of the removed graph
            self.export_destroy(name)
            # add the graph name to the purged list
            self.purged.add(name)
        else:
            raise ValueError("Graph with the name '%s' does not exist" % name)

    def names(self, name):
        name_set = set(self.partition)
        if self.graphs[name] is not None:
            name_set.update(self.graphs[name].names)
        return name_set

    def exports(self, name):
        if self.graphs[name] is not None:
            return AutoExport.select(self.graphs[name].names)
        else:
            return set()

    def features(self, name):
        return self.feature_stores[name].types

    def plots(self, name):
        return self.feature_stores[name].plots

    def feature_request(self, name, request):
        matched = self.feature_req.match(request)
        if matched:
            if matched.group('type') == 'fetch':
                if matched.group('name') in self.feature_stores[name]:
                    self.comm.send_string('ok', zmq.SNDMORE)
                    self.comm.send_pyobj(self.feature_stores[name].get(matched.group('name')))
                else:
                    self.comm.send_string('error')
            else:
                self.comm.send_string('error')
            return True
        else:
            return False

    def client_request(self):
        request = self.comm.recv_string()
        if request in self.global_cmds:
            getattr(self, "cmd_%s" % request, self.cmd_unknown)()
        elif self.comm.getsockopt(zmq.RCVMORE):
            name = self.comm.recv_string()
            if not self.exists(name) and request not in self.no_auto_create_cmds:
                self.create(name)
            # check if it is a feature request
            if not self.feature_request(name, request):
                getattr(self, "cmd_%s" % request, self.cmd_unknown)(name)
        else:
            self.comm.send_string('error')

    def compile_graph(self, name):
        """
        Tries to compile the named graph. A copy of the original graph is made,
        so the original graph is uneffected by the compilation.

        Args:
            name (str): the name of the graph to compile.
        """
        graph = dill.loads(dill.dumps(self.graphs[name]))
        graph.compile(**self.compiler_args)
        return graph

    def cmd_unknown(self, name=None):
        self.comm.send_string('error')

    def cmd_get_heartbeat(self, name):
        self.comm.send_pyobj(self.heartbeats[name])

    def cmd_get_versions(self, name):
        self.comm.send_pyobj((self.versions[name], self.feature_stores[name].version))

    def cmd_get_graph_version(self, name):
        self.comm.send_pyobj(self.versions[name])

    def cmd_get_features_version(self, name):
        self.comm.send_pyobj(self.feature_stores[name].version)

    def cmd_get_features(self, name):
        self.comm.send_pyobj(self.features(name))

    def cmd_get_plots(self, name):
        self.comm.send_pyobj(self.feature_stores[name].plots)

    def cmd_get_compiler_args(self, name):
        self.comm.send_pyobj(self.compiler_args)

    def cmd_get_names(self, name):
        self.comm.send_pyobj(self.names(name))

    def cmd_get_exports(self, name):
        self.comm.send_pyobj(self.exports(name))

    def cmd_get_sources(self, name):
        self.comm.send_pyobj(self.partition)

    def cmd_get_paths(self, name):
        self.comm.send_pyobj(list(self.paths[name]))

    def cmd_create_graph(self, name):
        if not self.exists(name):
            self.create(name)
        self.comm.send_string('ok')

    def cmd_destroy_graph(self, name):
        if self.exists(name):
            # send a null graph to workers
            self.publish_purge(name)
            # delete the local graph information
            self.delete(name)
        else:
            self.comm.send_string('ok')

    def cmd_clear_graph(self, name):
        self.graphs[name] = None
        self.publish_graph(name)

    def cmd_reset_features(self, name):
        self.feature_stores[name].clear()
        self.feature_stores[name].version = 0
        self.export_store(name)
        self.comm.send_string('ok')

    def cmd_list_graphs(self):
        self.comm.send_pyobj(set(self.graphs))

    def cmd_get_graph(self, name):
        self.comm.send(dill.dumps(self.graphs[name]))

    def cmd_get_purged_graph(self, name):
        if name in self.purged_graphs:
            self.comm.send(self.purged_graphs[name])
        else:
            self.comm.send(dill.dumps(None))

    def cmd_add_graph(self, name):
        nodes = dill.loads(self.comm.recv())
        backup = dill.dumps(self.graphs[name])
        try:
            if self.graphs[name] is None:
                self.graphs[name] = Graph(name)
            self.graphs[name].add(nodes)
            self.compile_graph(name)
            self.publish_delta(name, "add", nodes)
        except Exception:
            if isinstance(nodes, list):
                logger.exception("Failure encountered adding nodes \"%s\" to the graph:",
                                 ", ".join(n.name for n in nodes))
            else:
                logger.exception("Failure encountered adding node \"%s\" to the graph:", nodes.name)
            self.graphs[name] = dill.loads(backup)
            logger.info("Restored previous version of the graph (%s v%d)", name, self.versions[name])
            self.comm.send_string('error')

    def cmd_del_graph(self, name):
        nodes = dill.loads(self.comm.recv())
        if self.graphs[name] is not None:
            backup = dill.dumps(self.graphs[name])
            try:
                for node in nodes:
                    self.graphs[name].remove(node)
                # Check if the resulting graph is non-empty
                if self.graphs[name]:
                    self.compile_graph(name)
                else:
                    # if the graph is empty remove it
                    self.graphs[name] = None
                self.publish_delta(name, "del", nodes)
            except (AssertionError, TypeError):
                logger.exception("Failure encountered removing nodes \"%s\" from the graph:", nodes)
                self.graphs[name] = dill.loads(backup)
                logger.info("Restored previous version of the graph (%s v%d)", name, self.versions[name])
                self.comm.send_string('error')
        else:
            # Removing nodes that don't exist returns 'ok', so this case should too...
            self.comm.send_string('ok')

    def cmd_set_graph(self, name):
        backup = dill.dumps(self.graphs[name])
        try:
            self.graphs[name] = dill.loads(self.comm.recv())
            # Check if the graph can be compiled
            if self.graphs[name]:
                self.compile_graph(name)
            self.publish_graph(name)
        except (AssertionError, TypeError):
            logger.exception("Failure encountered compiling the requested graph:")
            self.graphs[name] = dill.loads(backup)
            logger.info("Restored previous version of the graph (%s v%d)", name, self.versions[name])
            self.comm.send_string('error')

    def cmd_get_metadata(self, name):
        if name in self.graphs and self.graphs[name]:
            graph = self.compile_graph(name)
            metadata = graph.metadata()
            self.comm.send(dill.dumps(metadata))
        else:
            self.comm.send(dill.dumps({}))

    def cmd_update_sources(self, name):
        src_cfg = self.comm.recv_pyobj()
        self.graph_comm.send_string("update_sources", zmq.SNDMORE)
        self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
        self.graph_comm.send(dill.dumps(src_cfg))
        self.comm.send_string('ok')

    def cmd_update_path(self, name):
        paths = self.comm.recv_pyobj()
        exists = True
        for pth in paths:
            if not os.path.exists(pth):
                logger.error("Path: %s not accessible from manager!", pth)
                exists = False

        if not exists:
            self.comm.send_string('error')
            return

        self.paths[name].update(paths)
        sys.path.extend(paths)
        self.graph_comm.send_string("update_path", zmq.SNDMORE)
        self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
        self.graph_comm.send(dill.dumps(paths))
        self.comm.send_string('ok')

    def cmd_update_plots(self, name):
        plots = self.comm.recv_pyobj()
        self.feature_stores[name].update_plots(plots)
        self.comm.send_string('ok')

    def publish_info(self, name):
        return name, self.versions[name], self.compiler_args

    def publish_purge(self, name, reply=True):
        logger.info("Purging requested graph...")
        try:
            self.purged_graphs[name] = dill.dumps(self.graphs[name])
            self.graphs[name] = None
            self.versions[name] += 1
            self.graph_comm.send_string("purge", zmq.SNDMORE)
            self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(self.graphs[name]))
            self.export_graph(name)
            logger.info("Purging of graph (%s v%d) completed", name, self.versions[name])
            if reply:
                self.comm.send_string('ok')
        except Exception:
            logger.exception("Failed to purge graph (%s v%d) -", name, self.versions[name])
            if reply:
                self.comm.send_string('error')

    def publish_delta(self, name, cmd, delta, reply=True):
        logger.info("Sending requested delta of graph...")
        try:
            self.versions[name] += 1
            self.graph_comm.send_string(cmd, zmq.SNDMORE)
            self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(delta))
            self.export_graph(name)
            logger.info("Sending delta of graph (%s v%d) completed", name, self.versions[name])
            if reply:
                self.comm.send_string('ok')
        except Exception:
            logger.exception("Failed to send delta of graph (%s v%d) -", name, self.versions[name])
            if reply:
                self.comm.send_string('error')

    def publish_graph(self, name, reply=True):
        logger.info("Sending requested graph...")
        try:
            self.versions[name] += 1
            self.graph_comm.send_string("graph", zmq.SNDMORE)
            self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
            self.graph_comm.send(dill.dumps(self.graphs[name]))
            self.export_graph(name)
            logger.info("Sending of graph (%s v%d) completed", name, self.versions[name])
            if reply:
                self.comm.send_string('ok')
        except Exception:
            logger.exception("Failed to send graph (%s v%d) -", name, self.versions[name])
            if reply:
                self.comm.send_string('error')

    def publish_message(self, topic, node, payload):
        self.info_comm.send_string(topic, zmq.SNDMORE)
        self.info_comm.send_string(node, zmq.SNDMORE)
        self.info_comm.send(payload)

    def publish_view(self, topic, timestamp, data):
        self.view_comm.send_string(topic + ZMQ_TOPIC_DELIM, zmq.SNDMORE)
        self.view_comm.send_pyobj(timestamp, zmq.SNDMORE)
        data = self.serializer(data)
        self.view_comm.send_multipart(data, copy=False, flags=zmq.NOBLOCK)
        return self.serializer.sizeof(data)

    def graph_request(self):
        request = self.graph_comm.recv_string()

        if request == "\x01":
            for name, graph in self.graphs.items():
                if name in self.paths:
                    self.graph_comm.send_string("update_path", zmq.SNDMORE)
                    self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
                    self.graph_comm.send(dill.dumps(self.paths[name]))
                self.graph_comm.send_string("init", zmq.SNDMORE)
                self.graph_comm.send_pyobj(self.publish_info(name), zmq.SNDMORE)
                self.graph_comm.send(dill.dumps(graph))
            # re-ask for config information on connect

            # we believe, but are not certain, that these lines
            # requesting an updated "config" from the workers (list of
            # variables that ami can use for data inputs) are no
            # longer necessary.  we think these lines created a
            # problem where the graph manager sends out several of
            # these (zmq pub-sub broadcasts) at the beginning of time
            # but the workers only look for those broadcasts when they
            # see a new heartbeat.  What happened is that these
            # messages get sent to the same zmq sockets as the daq
            # configure transitions.  Indeed, they are sent with the
            # same Transition.Configure message type as daq configure
            # transitions.  Depending on the timing, different workers
            # would see different numbers of these and then the ami
            # event-builder would intermittently have stale incomplete
            # transitions, so that when the next daq configure
            # transition was sent one could get intermittent
            # "transition mismatch" errors from comm.py, if the
            # configure transition payload (list of ami data sources)
            # changed (e.g. if starting a scan, which would add scan
            # variables).  ddamiani and cpo, may 10, 2022

            # self.graph_comm.send_string("cmd", zmq.SNDMORE)
            # self.graph_comm.send_string("config")

    def node_request(self):
        topic = self.node_msg_comm.recv_string()
        node = self.node_msg_comm.recv_string()

        if topic == "profile":
            # graph = self.node_msg_comm.recv_string()
            # payload = self.node_msg_comm.recv_multipart(copy=False)
            self.node_msg_comm.recv_string()
            self.node_msg_comm.recv_multipart(copy=False)
        elif topic == "purge":
            name = dill.loads(self.node_msg_comm.recv(copy=False))
            if self.exists(name):
                logger.info("Received purge request for graph (%s v%d) from %s", name, self.versions[name], node)
                # send a null graph to workers
                self.publish_purge(name, reply=False)
                # delete the local graph information
                self.delete(name)
        else:
            payload = self.node_msg_comm.recv(copy=False)
            self.publish_message(topic, node, payload)

    def info_request(self):
        request = self.info_comm.recv_string()

        if request == "\x01" or request == "\x01sources":
            self.publish_message("sources", "manager", dill.dumps(self.partition))

    def view_request(self):
        request = self.view_comm.recv_string()

        if request.startswith("\x01"):
            request = request.strip('\x01')
            matched = self.view_req.match(request)
            if matched:
                graph = matched.group('graph')
                name = matched.group('name')
                if self.exists(graph) and name in self.feature_stores[graph]:
                    self.publish_view("view:%s:%s" % (graph, name),
                                      self.heartbeats[graph],
                                      self.feature_stores[graph].get(name))
                else:
                    logger.debug("Received view request for unknown graph/feature: %s", request)
            else:
                logger.warn("Received invalid view request: %s", request)

    def export_view(self, name, keys=[]):
        size = 0

        for key, value in self.feature_stores[name].namespace.items():
            if key in keys:
                size += self.publish_view("view:%s:%s" % (name, key),
                                          self.heartbeats[name],
                                          value)
        self.event_size.labels(self.hutch, self.name).set(size)

    def export_request(self):
        request = self.export.recv_string()

        if request == "\x01" or request == "\x01info":
            self.export_config()

    def export_graph(self, name):
        data = {
            'names': self.names(name),
            'sources': self.partition,
            'version': self.versions[name],
            'dill': dill.dumps(self.graphs[name])
        }
        self.export.send_string('graph', zmq.SNDMORE)
        self.export.send_string(name, zmq.SNDMORE)
        self.export.send_pyobj(data)

    def export_store(self, name):
        data = {
            'version': self.feature_stores[name].version,
            'features': self.features(name),
            'plots': self.feature_stores[name].plots
        }
        self.export.send_string('store', zmq.SNDMORE)
        self.export.send_string(name, zmq.SNDMORE)
        self.export.send_pyobj(data)

    def export_info(self):
        data = {
            'graphs': set(self.graphs),
        }
        self.export.send_string('info', zmq.SNDMORE)
        self.export.send_string("", zmq.SNDMORE)
        self.export.send_pyobj(data)

    def export_config(self):
        self.export_info()
        for name in self.feature_stores:
            self.export_store(name)
        for name in self.graphs:
            self.export_graph(name)

    def export_create(self, name):
        self.export_info()
        self.export_store(name)
        self.export_graph(name)

    def export_destroy(self, name):
        self.export_info()
        self.export.send_string('destroy', zmq.SNDMORE)
        self.export.send_string(name, zmq.SNDMORE)
        self.export.send_pyobj(None)

    def export_data(self, name, data):
        export_data = {}
        for key, val in data.items():
            if AutoExport.is_auto(key):
                export_data[AutoExport.unmangle(key)] = val
        # Only export the dictionary if it is non-empty
        if export_data:
            self.export.send_string('data', zmq.SNDMORE)
            self.export.send_string(name, zmq.SNDMORE)
            self.export.send_pyobj(export_data)

    def export_heartbeat(self, name):
        self.export.send_string('heartbeat', zmq.SNDMORE)
        self.export.send_string(name, zmq.SNDMORE)
        self.export.send_pyobj(self.heartbeats[name])

    def start_prometheus(self, port):
        while True:
            try:
                pc.start_http_server(port)
                break
            except OSError:
                port += 1

        if self.prometheus_dir:
            if not os.path.exists(self.prometheus_dir):
                os.makedirs(self.prometheus_dir)
            pth = f"drpami_{socket.gethostname()}_{self.hutch}_{self.name}.json"
            pth = os.path.join(self.prometheus_dir, pth)
            conf = [{"targets": [f"{socket.gethostname()}:{port}"]}]
            try:
                with open(pth, 'w') as f:
                    json.dump(conf, f)
            except PermissionError:
                pass

        logger.info("%s: Started Prometheus client on port: %d", self.name, port)
        return port


def run_manager(num_workers,
                num_nodes,
                results_addr,
                graph_addr,
                comm_addr,
                msg_addr,
                info_addr,
                export_addr,
                view_addr,
                prometheus_dir,
                prometheus_port,
                hutch):
    logger.info('Starting manager, controlling %d workers on %d nodes PID: %d',
                num_workers, num_nodes, os.getpid())
    with Manager(
            num_workers,
            num_nodes,
            results_addr,
            graph_addr,
            comm_addr,
            msg_addr,
            info_addr,
            export_addr,
            view_addr,
            prometheus_dir,
            hutch) as manager:
        if prometheus_port:
            manager.start_prometheus(prometheus_port)
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
        '--num-nodes',
        type=int,
        default=1,
        help='number of nodes (a.k.a local collector processes) (default: 1)'
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

    args = parser.parse_args()

    results_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Results)
    graph_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Graph)
    comm_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Comm)
    msg_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Message)
    info_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Info)
    export_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Export)
    view_addr = "tcp://%s:%d" % (args.host, args.port + Ports.View)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        if args.port != BasePort:
            logger.info('Manager comm port: %d view port: %d', args.port + Ports.Comm, args.port + Ports.View)
        return run_manager(args.num_workers,
                           args.num_nodes,
                           results_addr,
                           graph_addr,
                           comm_addr,
                           msg_addr,
                           info_addr,
                           export_addr,
                           view_addr,
                           args.prometheus_dir,
                           args.prometheus_port,
                           args.hutch)
    except KeyboardInterrupt:
        logger.info("Manager killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
