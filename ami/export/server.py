#!/usr/bin/env python
import abc
import asyncio
import zmq
import time
import dill
import logging
import functools
import numpy as np
import ami.comm
from ami import LogConfig, p4pConfig
from ami.export.nt import NTBytes, NTObject, NTGraph, NTStore, CAGraph, CAStore
from p4p.nt import NTScalar, NTNDArray
from p4p.server import Server, StaticProvider
from p4p.server.asyncio import SharedPV
from p4p.rpc import rpc, NTURIDispatcher
# from p4p.util import ThreadedWorkQueue
from caproto.asyncio.server import Context as CAPContext
from caproto.server import PVSpec
from caproto import ChannelType

logger = logging.getLogger(LogConfig.get_package_name(__name__))


class EpicsExportServer(abc.ABC):
    def __init__(self, name, msg_addr, export_addr, *args, **kwargs):
        self.base = name
        self.ctx = zmq.asyncio.Context()
        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(export_addr)

        self.node_msg_comm = self.ctx.socket(zmq.PUSH)
        self.node_msg_comm.connect(msg_addr)

        self.pvs = {}
        self.ignored = set()
        self.graph_pvbase = "ana"
        self.data_pvbase = "data"
        self.info_pvbase = "info"

        self.node_msg_comm.send_string("epics", zmq.SNDMORE)
        self.node_msg_comm.send_string("export", zmq.SNDMORE)
        self.node_msg_comm.send_string(f"{name}:{self.graph_pvbase}")

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

    @abc.abstractmethod
    def create_pv(self, name, nt, initial, timestamp, func=None):
        pass

    @abc.abstractmethod
    async def post_pv(self, pvname, value, timestamp):
        pass

    def valid(self, name, group=None):
        return not name.startswith('_')

    @abc.abstractmethod
    def get_pv_type(self, data):
        pass

    @staticmethod
    def converted_data(data):
        for key, value in data.items():
            # convert any sets to tuples since p4p doesn't like sets...
            if isinstance(value, set):
                value = tuple(value)
            yield key, value

    @abc.abstractmethod
    async def update_graph(self, graph, data, timestamp, schema=None):
        # add the unaggregated version of the pvs
        for key, value in self.converted_data(data):
            if key in schema:
                name, nttype = schema[key]
                pvname = self.graph_pvname(graph, name)
                if pvname not in self.pvs:
                    self.create_pv(pvname, nttype, value, timestamp)
                else:
                    await self.post_pv(pvname, value, timestamp)

    @abc.abstractmethod
    async def update_store(self, graph, data, timestamp, schema=None):
        # add the unaggregated version of the pvs
        for key, value in data.items():
            if key in schema:
                name, nttype = schema[key]
                pvname = self.graph_pvname(graph, name)
                if pvname not in self.pvs:
                    self.create_pv(pvname, nttype, value, timestamp)
                else:
                    await self.post_pv(pvname, value, timestamp)

    @abc.abstractmethod
    async def update_heartbeat(self, graph, heartbeat, timestamp, nt=None):
        pvname = self.graph_pvname(graph, 'heartbeat')
        if pvname not in self.pvs:
            self.create_pv(pvname, nt, heartbeat.identity, timestamp)
        else:
            await self.post_pv(pvname, heartbeat.identity, timestamp)

    @abc.abstractmethod
    async def update_info(self, data, timestamp, nt=None):
        # add the unaggregated version of the pvs
        for key, value in self.converted_data(data):
            pvname = self.info_pvname(key)
            if pvname not in self.pvs:
                self.create_pv(pvname, nt, value, timestamp)
            else:
                await self.post_pv(pvname, value, timestamp)

    async def update_data(self, graph, name, data, timestamp):
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
                await self.post_pv(pvname, data, timestamp)

    @abc.abstractmethod
    def update_destroy(self, graph):
        pass

    @abc.abstractmethod
    async def start_server(self):
        pass

    async def run(self):
        # start the pva server thread
        # self.server_thread.start()
        logger.info("Starting export server")
        while True:
            topic = await self.export.recv_string()
            graph = await self.export.recv_string()
            exports = await self.export.recv_pyobj()
            timestamp = time.time()
            logger.debug("received: %s graph: %s", topic, graph)
            if topic == 'data':
                timestamp = exports.pop("_timestamp")
                if type(timestamp) is list:
                    for name, data in exports.items():
                        if self.valid(name):
                            for data_timestamp, data in sorted(zip(timestamp, data), key=lambda v: v[0]):
                                await self.update_data(graph, name, data, data_timestamp)
                else:
                    for name, data in exports.items():
                        # ignore names starting with '_' - these are private
                        if self.valid(name):
                            await self.update_data(graph, name, data, timestamp)
            elif topic == 'graph':
                await self.update_graph(graph, exports, timestamp)
            elif topic == 'store':
                await self.update_store(graph, exports, timestamp)
            elif topic == 'heartbeat':
                await self.update_heartbeat(graph, exports, timestamp)
            elif topic == 'info':
                await self.update_info(exports, timestamp)
            elif topic == 'destroy':
                self.update_destroy(graph)
            else:
                logger.warn("No handler for topic: %s", topic)


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


class PvaExportServer(EpicsExportServer):
    def __init__(self, name, msg_addr, export_addr, aggregate=False):
        super().__init__(name, msg_addr, export_addr)
        # self.queue = ThreadedWorkQueue(maxsize=20, workers=1)
        # pva server provider
        self.provider = StaticProvider(name)
        # self.rpc_provider = NTURIDispatcher(self.queue,
        #                                     target=PvaExportRpcHandler(self.ctx, comm_addr),
        #                                     name="%s:cmd" % self.base,
        #                                     prefix="%s:cmd:" % self.base)
        # self.server_thread = threading.Thread(target=self.server, name='pvaserv')
        # self.server_thread.daemon = True
        self.aggregate = aggregate
        self.server = Server(providers=[self.provider,
                                        # self.rpc_provider
                                        ])

    def create_pv(self, name, nt, initial, timestamp, func=None):
        extras = {}
        if func is not None:
            extras['handler'] = PvaExportPutHandler(put=func)
        if p4pConfig.SupportsTimestamps:
            extras['timestamp'] = timestamp
        pv = SharedPV(nt=nt, initial=initial, **extras)
        self.provider.add('%s:%s' % (self.base, name), pv)
        self.pvs[name] = pv

    def create_bytes_pv(self, name, initial, timestamp, func=None):
        self.create_pv(name, NTBytes(), initial, timestamp, func=func)

    async def post_pv(self, pvname, value, timestamp):
        extras = {}
        if p4pConfig.SupportsTimestamps:
            extras['timestamp'] = timestamp
        self.pvs[pvname].post(value, **extras)

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

    async def update_graph(self, graph, data, timestamp, schema=NTGraph.flat_schema):
        await super().update_graph(graph, data, timestamp, schema)
        # add the aggregated graph pv if requested
        if self.aggregate:
            pvname = self.graph_pvname(graph)
            if pvname not in self.pvs:
                logger.debug("Creating pv for info on the graph")
                self.create_pv(pvname, NTGraph(), data, timestamp)
            else:
                await self.post_pv(pvname, data, timestamp)

    async def update_store(self, graph, data, timestamp, schema=NTStore.flat_schema):
        await super().update_store(graph, data, timestamp, schema)
        # add the aggregated graph pv if requested
        if self.aggregate:
            pvname = self.graph_pvname(graph, 'store')
            if pvname not in self.pvs:
                logger.debug("Creating pv for info on the store")
                self.create_pv(pvname, NTStore(), data, timestamp)
            else:
                await self.post_pv(pvname, data, timestamp)

    async def update_heartbeat(self, graph, heartbeat, timestamp, nt=NTScalar('d')):
        await super().update_heartbeat(graph, heartbeat, timestamp, nt)

    async def update_info(self, data, timestamp):
        await super().update_info(data, timestamp, nt=NTScalar('as'))

    def update_destroy(self, graph):
        # close all the pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.pvs):
            logger.debug("Removing pv named %s for graph %s", name, graph)
            self.provider.remove('%s:%s' % (self.base, name))
            del self.pvs[name]
        # remove any ignored pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.ignored):
            self.ignored.remove(name)

    async def start_server(self):
        with self.server: #, self.queue:
            try:
                while True:
                    await asyncio.sleep(100)
            except KeyboardInterrupt:
                pass

class CaExportServer(EpicsExportServer):
    def __init__(self, name, msg_addr, export_addr, aggregate=False):
        super().__init__(name, msg_addr, export_addr)
        self.pvdb = {}
        self.server = CAPContext(self.pvdb)

    def create_pv(self, name, nt, initial, timestamp, func=None):
        kwargs = {}
        if nt == ChannelType.STRING:
            kwargs['max_length'] = 128

        pv = PVSpec(name=f"{self.base}:{name}", value=initial, dtype=nt, read_only=True, **kwargs)
        self.pvs[name] = pv.name
        self.pvdb[pv.name] = pv.create()
        self.server.pvdb = self.pvdb

    def get_pv_type(self, data):
        if isinstance(data, np.ndarray):
            return ChannelType.FLOAT
        elif isinstance(data, bool):
            return ChannelType.INT
        elif isinstance(data, int):
            return ChannelType.INT
        elif isinstance(data, float):
            return ChannelType.FLOAT
        else:
            return None

    async def post_pv(self, pvname, value, timestamp):
        pvdb_name = self.pvs[pvname]
        await self.pvdb[pvdb_name].write(value, timestamp=timestamp)

    async def update_graph(self, graph, data, timestamp, schema=CAGraph.flat_schema):
        await super().update_graph(graph, data, timestamp, schema)

    async def update_store(self, graph, data, timestamp, schema=CAStore.flat_schema):
        await super().update_store(graph, data, timestamp, schema)

    async def update_heartbeat(self, graph, heartbeat, timestamp, nt=ChannelType.INT):
        await super().update_heartbeat(graph, heartbeat, timestamp, nt)

    async def update_info(self, data, timestamp):
        if not all(data.values()):
            return
        await super().update_info(data, timestamp, nt=ChannelType.STRING)

    def update_destroy(self, graph):
        # close all the pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.pvs):
            logger.debug("Removing pv named %s for graph %s", name, graph)
            pvname = self.pvs[name]
            del self.pvdb[pvname]
            del self.pvs[name]
        # remove any ignored pvs associated with the purged graph
        for name in self.find_graph_pvnames(graph, self.ignored):
            self.ignored.remove(name)

        self.server.pvdb = self.pvs

    async def start_server(self):
        await self.server.run()
