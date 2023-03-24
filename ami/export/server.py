#!/usr/bin/env python
import zmq
import time
import dill
import logging
import threading
import functools
import numpy as np
import ami.comm
from ami import LogConfig
from ami.export.nt import NTBytes, NTObject, NTGraph, NTStore
from p4p.nt import NTScalar, NTNDArray
from p4p.server import Server, StaticProvider
from p4p.server.thread import SharedPV
from p4p.rpc import rpc, NTURIDispatcher
from p4p.util import ThreadedWorkQueue


logger = logging.getLogger(LogConfig.get_package_name(__name__))


def tsrpc(rtype=None):
    """patches the rpc to give a valid timestamp"""
    if hasattr(rtype, "wrap"):
        def wrapper(func):
            @rpc(rtype)
            @functools.wraps(func)
            def tswrap(*args, **kwargs):
                return rtype.wrap(func(*args, **kwargs), timestamp=time.time())
            return tswrap
        return wrapper
    else:
        return rpc(rtype)



class PvaExportPutHandler:

    def __init__(self, put=None, rpc=None):
        self._put = put
        self._rpc = rpc

    def put(self, pv, op):
        if self._put is not None:
            self._put(pv, op)

    def rpc(self, pv, op):
        if self._rpc is not None:
            self._rpc(pv, op)


class PvaExportRpcHandler:
    def __init__(self, ctx, addr):
        self.ctx = ctx
        self.addr = addr
        self.comms = {}

    def _get_comm(self, graph):
        if graph not in self.comms:
            self.comms[graph] = ami.comm.GraphCommHandler(graph, self.addr, ctx=self.ctx)
        return self.comms[graph]

    @tsrpc(NTScalar('?'))
    def create(self, graph):
        return self._get_comm(graph).create()

    @tsrpc(NTScalar('?'))
    def destroy(self, graph):
        return self._get_comm(graph).destroy()

    @tsrpc(NTScalar('?'))
    def clear(self, graph):
        return self._get_comm(graph).clear()

    @tsrpc(NTScalar('?'))
    def reset(self, graph):
        return self._get_comm(graph).reset()

    @tsrpc(NTScalar('?'))
    def post(self, graph, topic, payload):
        return self._get_comm(graph)._post_dill(topic, dill.loads(payload.tobytes()))

    @tsrpc(NTScalar('as'))
    def names(self, graph):
        return self._get_comm(graph).names

    @tsrpc(NTScalar('?'))
    def view(self, graph, name):
        return self._get_comm(graph).view(name)

    @tsrpc(NTScalar('?'))
    def export(self, graph, name, alias):
        return self._get_comm(graph).export(name, alias)


class PvaExportServer:
    def __init__(self, name, comm_addr, export_addr, aggregate=False):
        self.base = name
        self.ctx = zmq.Context()
        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(export_addr)
        self.comm = self.ctx.socket(zmq.REQ)
        self.comm.connect(comm_addr)
        self.queue = ThreadedWorkQueue(maxsize=20, workers=1)
        # pva server provider
        self.provider = StaticProvider(name)
        self.rpc_provider = NTURIDispatcher(self.queue,
                                            target=PvaExportRpcHandler(self.ctx, comm_addr),
                                            name="%s:cmd" % self.base,
                                            prefix="%s:cmd:" % self.base)
        self.server_thread = threading.Thread(target=self.server, name='pvaserv')
        self.server_thread.daemon = True
        self.aggregate = aggregate
        self.pvs = {}
        self.ignored = set()
        self.graph_pvbase = "ana"
        self.data_pvbase = "data"
        self.info_pvbase = "info"
        self.cmd_pvs = {'command'}
        self.payload_cmd_pvs = {'add', 'set', 'del'}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        self.ctx.destroy()

    @staticmethod
    def join_pv(*args):
        return ":".join(args)

    def graph_pvname(self, graph, name=None):
        if name is not None:
            return ":".join([self.graph_pvbase, graph, name])
        else:
            return ":".join([self.graph_pvbase, graph])

    def data_pvname(self, graph, name):
        return ":".join([self.graph_pvbase, graph, self.data_pvbase, name])

    def info_pvname(self, name):
        return ":".join([self.info_pvbase, name])

    def find_graph_pvnames(self, graph, names):
        return [name for name in names if name.startswith(self.graph_pvname(graph))]

    def create_pv(self, name, nt, initial, timestamp, func=None):
        if func is not None:
            pv = SharedPV(nt=nt, initial=initial, handler=PvaExportPutHandler(put=func), timestamp=timestamp)
        else:
            pv = SharedPV(nt=nt, initial=initial, timestamp=timestamp)
        self.provider.add('%s:%s' % (self.base, name), pv)
        self.pvs[name] = pv

    def create_bytes_pv(self, name, initial, timestamp, func=None):
        self.create_pv(name, NTBytes(), initial, timestamp, func=func)

    def valid(self, name, group=None):
        return not name.startswith('_')

    def get_pv_type(self, data):
        if isinstance(data, np.ndarray):
            return NTNDArray()
        elif isinstance(data, bool):
            return NTScalar('?')
        elif isinstance(data, int):
            return NTScalar('l')
        elif isinstance(data, float):
            return NTScalar('d')
        else:
            return NTObject()

    @staticmethod
    def converted_data(data):
        for key, value in data.items():
            # convert any sets to tuples since p4p doesn't like sets...
            if isinstance(value, set):
                value = tuple(value)
            yield key, value

    def update_graph(self, graph, data, timestamp):
        # add the unaggregated version of the pvs
        for key, value in self.converted_data(data):
            if key in NTGraph.flat_schema:
                name, nttype = NTGraph.flat_schema[key]
                pvname = self.graph_pvname(graph, name)
                if pvname not in self.pvs:
                    self.create_pv(pvname, nttype, value, timestamp)
                else:
                    self.pvs[pvname].post(value, timestamp=timestamp)
        # add the aggregated graph pv if requested
        if self.aggregate:
            pvname = self.graph_pvname(graph)
            if pvname not in self.pvs:
                logger.debug("Creating pv for info on the graph")
                self.create_pv(pvname, NTGraph(), data, timestamp)
            else:
                self.pvs[pvname].post(data, timestamp=timestamp)

    def update_store(self, graph, data, timestamp):
        # add the unaggregated version of the pvs
        for key, value in data.items():
            if key in NTStore.flat_schema:
                name, nttype = NTStore.flat_schema[key]
                pvname = self.graph_pvname(graph, name)
                if pvname not in self.pvs:
                    self.create_pv(pvname, nttype, value, timestamp)
                else:
                    self.pvs[pvname].post(value, timestamp=timestamp)
        # add the aggregated graph pv if requested
        if self.aggregate:
            pvname = self.graph_pvname(graph, 'store')
            if pvname not in self.pvs:
                logger.debug("Creating pv for info on the store")
                self.create_pv(pvname, NTStore(), data, timestamp)
            else:
                self.pvs[pvname].post(data, timestamp=timestamp)

    def update_heartbeat(self, graph, heartbeat, timestamp):
        pvname = self.graph_pvname(graph, 'heartbeat')
        if pvname not in self.pvs:
            self.create_pv(pvname, NTScalar('d'), heartbeat.identity, timestamp)
        else:
            self.pvs[pvname].post(heartbeat.identity, timestamp=timestamp)

    def update_info(self, data, timestamp):
        # add the unaggregated version of the pvs
        for key, value in self.converted_data(data):
            pvname = self.info_pvname(key)
            if pvname not in self.pvs:
                self.create_pv(pvname, NTScalar('as'), value, timestamp)
            else:
                self.pvs[pvname].post(value, timestamp=timestamp)

    def update_data(self, graph, name, data, timestamp):
        pvname = self.data_pvname(graph, name)
        if pvname not in self.ignored:
            if pvname not in self.pvs:
                pv_type = self.get_pv_type(data)
                if pv_type is not None:
                    logger.debug("Creating new pv named %s for graph %s", name, graph)
                    self.create_pv(pvname, pv_type, data, timestamp)
                else:
                    logger.warn("Cannot map type of '%s' from graph '%s' to PV: %s", name, graph, type(data))
                    self.ignored.add(pvname)
            else:
                self.pvs[pvname].post(data, timestamp=timestamp)

    def update_destroy(self, graph):
        # close all the pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.pvs):
            logger.debug("Removing pv named %s for graph %s", name, graph)
            self.provider.remove('%s:%s' % (self.base, name))
            del self.pvs[name]
        # remove any ignored pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.ignored):
            self.ignored.remove(name)

    def server(self):
        server = Server(providers=[self.provider, self.rpc_provider])
        with server, self.queue:
            try:
                while True:
                    time.sleep(100)
            except KeyboardInterrupt:
                pass

    def run(self):
        # start the pva server thread
        self.server_thread.start()
        logger.info("Starting PVA data export server")
        while True:
            topic = self.export.recv_string()
            graph = self.export.recv_string()
            exports = self.export.recv_pyobj()
            timestamp = time.time()
            if topic == 'data':
                for name, data in exports.items():
                    # ignore names starting with '_' - these are private
                    if self.valid(name):
                        self.update_data(graph, name, data, timestamp)
            elif topic == 'graph':
                self.update_graph(graph, exports, timestamp)
            elif topic == 'store':
                self.update_store(graph, exports, timestamp)
            elif topic == 'heartbeat':
                self.update_heartbeat(graph, exports, timestamp)
            elif topic == 'info':
                self.update_info(exports, timestamp)
            elif topic == 'destroy':
                self.update_destroy(graph)
            else:
                logger.warn("No handler for topic: %s", topic)
