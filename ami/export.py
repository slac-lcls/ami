#!/usr/bin/env python
import re
import abc
import sys
import zmq
import time
import dill
import asyncio
import logging
import argparse
import threading
import functools
import numpy as np
import collections
from ami import LogConfig
from ami.comm import Ports, CommHandler
from p4p import Type, Value
from p4p.nt import alarm, timeStamp, NTScalar, NTNDArray
from p4p.server import Server, StaticProvider
from p4p.server.thread import SharedPV
import p4p.client.thread as pct
import p4p.client.asyncio as pca


logger = logging.getLogger(__name__)


def _generate_schema(graph=True):
    if graph:
        fields = collections.OrderedDict([
            ('names', 'as'),
            ('types', 'aB'),
            ('sources', 'aB'),
            ('version', 'l'),
            ('dill', 'aB'),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = {'dill'}
        object_fields = {'sources', 'types'}
        flat_names = {
            'names':    'graph:names',
            'types':    'graph:types',
            'sources':  'graph:sources',
            'version':  'graph:version',
            'dill':     'graph:dill',
        }
    else:
        fields = collections.OrderedDict([
            ('version', 'l'),
            ('features', 'aB'),
        ])
        schema = [(k, v) for k, v in fields.items()]
        byte_fields = set()
        object_fields = {'features'}
        flat_names = {
            'version':  'store:version',
            'features': 'store:features',
        }

    def get_type(key, value):
        if key in byte_fields:
            return NTBytes()
        elif key in object_fields:
            return NTObject()
        else:
            return NTScalar(value)

    flat_schema = {
        k: (flat_names[k], get_type(k, v)) for k, v in fields.items()
    }
    return schema, flat_schema, byte_fields, object_fields


class NTBytes:

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', 'aB'),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTBytes:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        return Value(self.type, {
            'value': np.frombuffer(value, dtype=np.ubyte),
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        V = value.value
        return V.tobytes()

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTObject:

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', 'aB'),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTObject:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        return Value(self.type, {
            'value': np.frombuffer(dill.dumps(value), dtype=np.ubyte),
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        V = value.value
        return dill.loads(V.tobytes())

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTGraph:
    schema, flat_schema, byte_fields, object_fields = _generate_schema()

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', ('S', None, klass.schema)),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTGraph:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        for field in self.byte_fields:
            value[field] = np.frombuffer(value[field], np.ubyte)
        for field in self.object_fields:
            value[field] = np.frombuffer(dill.dumps(value[field]), np.ubyte)
        return Value(self.type, {
            'value': value,
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        result = {}
        V = value.value
        for k in V:
            if k in klass.byte_fields:
                result[k] = V[k].tobytes()
            elif k in klass.object_fields:
                result[k] = dill.loads(V[k].tobytes())
            else:
                result[k] = V[k]
        return result

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


class NTStore:
    schema, flat_schema, byte_fields, object_fields = _generate_schema(False)

    @classmethod
    def buildType(klass, extra=[]):
        """Build type
        """
        return Type([
            ('value', ('S', None, klass.schema)),
            ('alarm', alarm),
            ('timeStamp', timeStamp),
        ], id='ami:export/NTStore:1.0')

    def __init__(self, **kws):
        self.type = self.buildType(**kws)

    def wrap(self, value):
        """Wrap dictionary as Value
        """
        S, NS = divmod(time.time(), 1.0)
        for field in self.byte_fields:
            value[field] = np.frombuffer(value[field], np.ubyte)
        for field in self.object_fields:
            value[field] = np.frombuffer(dill.dumps(value[field]), np.ubyte)
        return Value(self.type, {
            'value': value,
            'timeStamp': {
                'secondsPastEpoch': S,
                'nanoseconds': NS * 1e9,
            },
        })

    @classmethod
    def unwrap(klass, value):
        result = {}
        V = value.value
        for k in V:
            if k in klass.byte_fields:
                result[k] = V[k].tobytes()
            elif k in klass.object_fields:
                result[k] = dill.loads(V[k].tobytes())
            else:
                result[k] = V[k]
        return result

    def assign(self, V, py):
        """Store python value in Value
        """
        V.value = py


CUSTOM_TYPE_WRAPPERS = {
    'ami:export/NTBytes:1.0': NTBytes,
    'ami:export/NTObject:1.0': NTObject,
    'ami:export/NTGraph:1.0': NTGraph,
    'ami:export/NTStore:1.0': NTStore,
}


class PvaCommHandler(CommHandler):

    def __init__(self, name, async_mode=False, timeout=1.0):
        super().__init__()
        self._name = name
        self._timeout = timeout
        if async_mode:
            self._ctx = pca.Context('pva', nt=CUSTOM_TYPE_WRAPPERS)
            self._errors = (asyncio.TimeoutError, pca.RemoteError)
        else:
            self._ctx = pct.Context('pva', nt=CUSTOM_TYPE_WRAPPERS)
            self._errors = (TimeoutError, pct.RemoteError)
        self._feature_req = re.compile("(?P<type>fetch|lookup):(?P<name>.*)")
        self._pvmap = {
            'get_names': '%s:graph:names',
            'get_types': '%s:graph:types',
            'get_sources': '%s:graph:sources',
            'get_versions': ['%s:graph:version', '%s:store:version'],
            'get_graph_version': '%s:graph:version',
            'get_features_version': '%s:store:version',
            'get_features': '%s:store:features',
            'add_graph': '%s:graph:add',
            'get_graph': '%s:graph:dill',
            'set_graph': '%s:graph:set',
            'del_graph': '%s:graph:del',
        }

    @staticmethod
    def _serialize(payload):
        return np.frombuffer(dill.dumps(payload), np.ubyte)

    @staticmethod
    def _deserialize(payload):
        return dill.loads(payload)

    @abc.abstractmethod
    def _checked_put(self, pvname, value):
        pass

    @abc.abstractmethod
    def _unchecked_get(self, pvname):
        pass

    @abc.abstractmethod
    def _checked_get(self, pvname):
        pass

    def _get_pvname(self, cmd):
        if cmd in self._pvmap:
            if isinstance(self._pvmap[cmd], list):
                return [n % self._name for n in self._pvmap[cmd]]
            else:
                return self._pvmap[cmd] % self._name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._ctx.close()


class GraphCommHandler(PvaCommHandler):

    def __init__(self, name, timeout=1.0):
        super().__init__(name, False, timeout)

    def _checked_put(self, pvname, value):
        try:
            self._ctx.put(pvname, value, timeout=self._timeout)
            return True
        except self._errors:
            return False

    def _unchecked_get(self, pvname):
        return self._ctx.get(pvname, timeout=self._timeout)

    def _checked_get(self, pvname):
        try:
            reply = self._ctx.get(pvname, timeout=self._timeout)
        except self._errors:
            reply = None
        return reply

    def _command(self, cmd):
        return self._checked_put("%s:graph:command" % self._name, cmd)

    def _try_request(self, cmd):
        try:
            matched = self._feature_req.match(cmd)
            if matched:
                if matched.group('type') == 'fetch':
                    return True, self._unchecked_get('%s:%s' % (self._name, matched.group('name')))
                elif matched.group('type') == 'lookup':
                    reply = self._unchecked_get(self._get_pvname('get_types'))
                    if matched.group('name') in reply:
                        return True, reply[matched.group('name')]
            else:
                pvname = self._get_pvname(cmd)
                if pvname is not None:
                    return True, self._unchecked_get(pvname)

            # if we fell through to here it is a failure
            return False, None
        except self._errors:
            return False, None

    def _request(self, cmd, check=False, retry=None):
        if check:
            status, reply = self._try_request(cmd)
            if status:
                return reply
            elif retry is not None:
                status, reply = self._try_request(retry)
                if status:
                    return reply
        else:
            pvname = self._get_pvname(cmd)
            if pvname is not None:
                return self._checked_get(pvname)

    def _request_batch(self, cmds, check=False, retries=None):
        results = []
        if retries is None:
            for cmd in cmds:
                results.append(self._request(cmd, check))
        else:
            for cmd, retry in zip(cmds, retries):
                results.append(self._request(cmd, check, retry))
        if all(entry is None for entry in results):
            return None
        else:
            return results

    def _request_dill(self, cmd):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            reply = self._checked_get(pvname)
            if reply is not None:
                return self._deserialize(reply)

    def _post_dill(self, cmd, payload):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            return self._checked_put(pvname, self._serialize(payload))
        else:
            return False

    def _view(self, names):
        nodes = []
        for name in names:
            view_name = self.auto(name)
            var_type = self.get_type(name)
            nodes.append(self._make_view_node(name, view_name, var_type))

        return self.add(nodes)

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)


class AsyncGraphCommHandler(PvaCommHandler):

    def __init__(self, name, timeout=1.0):
        super().__init__(name, True, timeout)

    async def _checked_put(self, pvname, value):
        try:
            await asyncio.wait_for(self._ctx.put(pvname, value), timeout=self._timeout)
            return True
        except self._errors:
            return False

    async def _unchecked_get(self, pvname):
        return await asyncio.wait_for(self._ctx.get(pvname), timeout=self._timeout)

    async def _checked_get(self, pvname):
        try:
            reply = await asyncio.wait_for(self._ctx.get(pvname), timeout=self._timeout)
        except self._errors:
            reply = None
        return reply

    async def _command(self, cmd):
        return await self._checked_put("%s:graph:command" % self._name, cmd)

    async def _try_request(self, cmd):
        try:
            matched = self._feature_req.match(cmd)
            if matched:
                if matched.group('type') == 'fetch':
                    return True, await self._unchecked_get('%s:%s' % (self._name, matched.group('name')))
                elif matched.group('type') == 'lookup':
                    reply = await self._unchecked_get(self._get_pvname('get_types'))
                    if matched.group('name') in reply:
                        return True, reply[matched.group('name')]
            else:
                pvname = self._get_pvname(cmd)
                if pvname is not None:
                    return True, await self._unchecked_get(pvname)

            # if we fell through to here it is a failure
            return False, None
        except self._errors:
            return False, None

    async def _request(self, cmd, check=False, retry=None):
        if check:
            status, reply = await self._try_request(cmd)
            if status:
                return reply
            elif retry is not None:
                status, reply = await self._try_request(retry)
                if status:
                    return reply
        else:
            pvname = self._get_pvname(cmd)
            if pvname is not None:
                return await self._checked_get(pvname)

    async def _request_batch(self, cmds, check=False, retries=None):
        results = []
        if retries is None:
            for cmd in cmds:
                results.append(await self._request(cmd, check))
        else:
            for cmd, retry in zip(cmds, retries):
                results.append(await self._request(cmd, check, retry))
        if all(entry is None for entry in results):
            return None
        else:
            return results

    async def _request_dill(self, cmd):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            reply = await self._checked_get(pvname)
            if reply is not None:
                return self._deserialize(reply)

    async def _post_dill(self, cmd, payload):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            return await self._checked_put(pvname, self._serialize(payload))
        else:
            return False

    async def _view(self, names):
        nodes = []
        for name in names:
            view_name = self.auto(name)
            var_type = await self.get_type(name)
            nodes.append(self._make_view_node(name, view_name, var_type))

        return await self.add(nodes)

    async def _load(self, filename):
        with open(filename, 'rb') as cnf:
            graph = dill.load(cnf)
        return await self.update(graph)

    async def _save(self, filename):
        graph = await self.graph
        with open(filename, 'wb') as cnf:
            return dill.dump(graph, cnf)


class PutHandler:

    def __init__(self, put=None, rpc=None):
        self._put = put
        self._rpc = rpc

    def put(self, pv, op):
        if self._put is not None:
            self._put(pv, op)

    def rpc(self, pv, op):
        if self._rpc is not None:
            self._rpc(pv, op)


class PvaExportHandler:
    def __init__(self, name, comm_addr, export_addr, aggregate=False):
        self.name = name
        self.ctx = zmq.Context()
        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(export_addr)
        self.comm = self.ctx.socket(zmq.REQ)
        self.comm.connect(comm_addr)
        # pva server provider
        self.provider = StaticProvider(name)
        self.server_thread = threading.Thread(target=self.server, name='pvaserv')
        self.server_thread.daemon = True
        self.aggregate = aggregate
        self.pvs = {}
        self.ignored = set()
        self.create_pv('graph:command', NTScalar('s'), "", func=self.command_pv)
        self.create_bytes_pv('graph:add', b"", func=functools.partial(self.payload_pv, 'add_graph'))
        self.create_bytes_pv('graph:set', b"", func=functools.partial(self.payload_pv, 'set_graph'))
        self.create_bytes_pv('graph:del', b"", func=functools.partial(self.payload_pv, 'del_graph'))

    def command_pv(self, pv, op):
        cmd = op.value()
        self.comm.send_string(cmd)
        if self.comm.recv_string() == 'ok':
            pv.post(cmd)
            op.done()
        else:
            op.done(error='command failed')

    def payload_pv(self, topic, pv, op):
        payload = op.value()
        self.comm.send_string(topic, zmq.SNDMORE)
        self.comm.send(payload)
        if self.comm.recv_string() == 'ok':
            pv.post(payload)
            op.done()
        else:
            op.done(error='post payload failed')

    def create_pv(self, name, nt, initial, func=None):
        if func is not None:
            pv = SharedPV(nt=nt, initial=initial, handler=PutHandler(put=func))
        else:
            pv = SharedPV(nt=nt, initial=initial)
        self.provider.add('%s:%s' % (self.name, name), pv)
        self.pvs[name] = pv

    def create_bytes_pv(self, name, initial, func=None):
        self.create_pv(name, NTBytes(), initial, func=func)

    def valid(self, name):
        return (name not in self.ignored) and (not name.startswith('_'))

    def unmangle(self, name):
        prefix = '_auto_'
        if name.startswith(prefix):
            return name[len(prefix):]
        else:
            return name

    def get_pv_type(self, data):
        if isinstance(data, np.ndarray):
            return NTNDArray()
        elif isinstance(data, int):
            return NTScalar('l')
        elif isinstance(data, float):
            return NTScalar('d')
        else:
            return NTObject()

    def update_graph(self, data):
        # add the unaggregated version of the pvs
        for key, value in data.items():
            if key in NTGraph.flat_schema:
                name, nttype = NTGraph.flat_schema[key]
                if name not in self.pvs:
                    self.create_pv(name, nttype, value)
                else:
                    self.pvs[name].post(value)
        # add the aggregated graph pv if requested
        if self.aggregate:
            if 'graph' not in self.pvs:
                logger.debug("Creating pv for info on the graph")
                self.create_pv('graph', NTGraph(), data)
            else:
                self.pvs['graph'].post(data)

    def update_store(self, data):
        # add the unaggregated version of the pvs
        for key, value in data.items():
            if key in NTStore.flat_schema:
                name, nttype = NTStore.flat_schema[key]
                if name not in self.pvs:
                    self.create_pv(name, nttype, value)
                else:
                    self.pvs[name].post(value)
        # add the aggregated graph pv if requested
        if self.aggregate:
            if 'store' not in self.pvs:
                logger.debug("Creating pv for info on the store")
                self.create_pv('store', NTStore(), data)
            else:
                self.pvs['store'].post(data)

    def server(self):
        Server.forever(providers=[self.provider])

    def run(self):
        # start the pva server thread
        self.server_thread.start()
        logger.info("Starting PVA data export server")
        while True:
            topic = self.export.recv_string()
            exports = self.export.recv_pyobj()
            if topic == 'data':
                for raw, data in exports.items():
                    name = self.unmangle(raw)
                    # ignore names starting with '_' after unmangling - these are private
                    if self.valid(name):
                        if name not in self.pvs:
                            pv_type = self.get_pv_type(data)
                            if pv_type is not None:
                                logger.debug("Creating new pv named %s", name)
                                self.create_pv(name, pv_type, data)
                            else:
                                logger.warn("Cannot map type of '%s' to PV: %s", name, type(data))
                                self.ignored.add(name)
                        else:
                            self.pvs[name].post(data)
            elif topic == 'graph':
                self.update_graph(exports)
            elif topic == 'store':
                self.update_store(exports)
            else:
                logger.warn("No handler for topic: %s", topic)


def run_export(name, comm_addr, export_addr, aggregate=False):
    export = PvaExportHandler(name, comm_addr, export_addr, aggregate)
    return export.run()


def main():
    parser = argparse.ArgumentParser(description='AMII DataExport App')

    parser.add_argument(
        '-H',
        '--host',
        default='localhost',
        help='hostname of the AMII Manager (default: localhost)'
    )

    parser.add_argument(
        '-e',
        '--export',
        type=int,
        default=Ports.Export,
        help='port for receiving data to export (default: %d)' % Ports.Export
    )

    parser.add_argument(
        '-c',
        '--comm',
        type=int,
        default=Ports.Comm,
        help='port for DataExport-Manager communication (default: %d)' % Ports.Comm
    )

    parser.add_argument(
        '-a',
        '--aggregate',
        action='store_true',
        help='aggregates graph and store related variables into structured data (not all clients support this)'
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
        'name',
        help='the base name to use for data export (e.g. the base of all the PV names)'
    )

    args = parser.parse_args()

    export_addr = "tcp://%s:%d" % (args.host, args.export)
    comm_addr = "tcp://%s:%d" % (args.host, args.comm)

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_export(args.name, comm_addr, export_addr, args.aggregate)
    except KeyboardInterrupt:
        logger.info("DataExport killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
