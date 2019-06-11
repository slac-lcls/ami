#!/usr/bin/env python
import re
import abc
import dill
import asyncio
import logging
import numpy as np
from ami import LogConfig
from ami.comm import CommHandler
from ami.export.nt import CUSTOM_TYPE_WRAPPERS
from p4p.nt import NTURI
from p4p.rpc import rpccall, rpcproxy
import p4p.client.thread as pct
import p4p.client.asyncio as pca


logger = logging.getLogger(LogConfig.get_package_name(__name__))


@rpcproxy
class RpcProxyThreads:

    def __init__(self, name, errors, timeout):
        self.name = name
        self.errors = errors
        self.timeout = timeout
        self.command_map = {
            'create_graph': self.create,
            'clear_graph': self.clear,
            'reset_features': self.reset,
            'destroy_graph': self.destroy,
        }

    def payload(self, cmd, payload):
        try:
            return self.post(self.name, cmd, payload)
        except self.errors:
            return False

    def command(self, cmd):
        if cmd in self.command_map:
            try:
                return self.command_map[cmd](self.name)
            except self.errors:
                return False
        else:
            return False

    @rpccall('%s:create')
    def create(graph='s'):
        pass

    @rpccall('%s:destroy')
    def destroy(graph='s'):
        pass

    @rpccall('%s:clear')
    def clear(graph='s'):
        pass

    @rpccall('%s:reset')
    def reset(graph='s'):
        pass

    @rpccall('%s:post')
    def post(graph='s', topic='s', payload='aB'):
        pass


class RpcProxyAsyncio:

    def __init__(self, context=None, format=None, name=None, errors=None, timeout=None):
        assert context is not None, context
        self.ctx = context
        self.basepv = format
        self.name = name
        self.errors = errors
        self.timeout = timeout
        self.scheme = context.name
        self.authority = ''
        self.cmd_nturi = NTURI([('graph', 's')])
        self.payload_nturi = NTURI([('graph', 's'), ('topic', 's'), ('payload', 'aB')])
        self.command_map = {
            # cmd name: ('pv', 'request', 'NTURI')
            'create_graph': ('%s:create', None, self.cmd_nturi),
            'clear_graph': ('%s:clear', None, self.cmd_nturi),
            'reset_features': ('%s:reset', None, self.cmd_nturi),
            'destroy_graph': ('%s:destroy', None, self.cmd_nturi),
        }

    def wrap(self, nturi, path, *args, **kwargs):
        return nturi.wrap(path, args, kwargs, scheme=self.scheme, authority=self.authority)

    def parse_cmd(self, cmd):
        pvfmt, req, nturi = self.command_map[cmd]
        pvname = pvfmt % self.basepv
        return pvname, req, self.wrap(nturi, pvname, graph=self.name)

    async def payload(self, cmd, payload):
        try:
            pvname = '%s:post' % self.basepv
            uri = self.wrap(self.payload_nturi, pvname, graph=self.name, topic=cmd, payload=payload)
            return await asyncio.wait_for(self.ctx.rpc(pvname, uri, request=None), timeout=self.timeout)
        except self.errors:
            return False

    async def command(self, cmd):
        if cmd in self.command_map:
            try:
                pvname, req, uri = self.parse_cmd(cmd)
                return await asyncio.wait_for(self.ctx.rpc(pvname, uri, request=req), timeout=self.timeout)
            except self.errors:
                return False
        else:
            return False


def PvaCommRpcProxy(ctx, **kwargs):
    if isinstance(ctx, pct.Context):
        return RpcProxyThreads(context=ctx, **kwargs)
    elif isinstance(ctx, pca.Context):
        return RpcProxyAsyncio(context=ctx, **kwargs)
    else:
        raise TypeError("Shared context of type %s not supported!")


class PvaCommHandler(CommHandler):

    def __init__(self, name, addr, ctx, errors, owner, timeout=1.0):
        super().__init__(name)
        self._ctx = ctx
        self._errors = errors
        self._addr = addr
        self._owner = owner
        self._timeout = timeout
        self._proxy = PvaCommRpcProxy(ctx, format="%s:cmd" % addr, name=name, errors=errors, timeout=timeout)
        self._feature_req = re.compile("(?P<type>fetch|lookup):(?P<name>.*)")
        self._pvinfomap = {
            'list_graphs': '%s:info:graphs',
        }
        self._pvmap = {
            'get_names': '%s:ana:%s:names',
            'get_sources': '%s:ana:%s:sources',
            'get_versions': ['%s:ana:%s:version', '%s:ana:%s:store:version'],
            'get_graph_version': '%s:ana:%s:version',
            'get_heartbeat': '%s:ana:%s:heartbeat',
            'get_features_version': '%s:ana:%s:store:version',
            'get_features': '%s:ana:%s:store:features',
            'get_graph': '%s:ana:%s:dill',
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

    def _set_name(self, name):
        self._name = name
        self._proxy.name = name

    def _get_pvname(self, cmd):
        if not self._name:
            raise ValueError("graph name must be a non-emtpy string")
        elif cmd in self._pvmap:
            if isinstance(self._pvmap[cmd], list):
                return [n % (self._addr, self._name) for n in self._pvmap[cmd]]
            else:
                return self._pvmap[cmd] % (self._addr, self._name)
        elif cmd in self._pvinfomap:
            if isinstance(self._pvinfomap[cmd], list):
                return [n % self._addr for n in self._pvinfomap[cmd]]
            else:
                return self._pvinfomap[cmd] % self._addr

    def _get_data_pvname(self, data):
        if not self._name:
            raise ValueError("graph name must be a non-emtpy string")
        else:
            return '%s:ana:%s:data:%s' % (self._addr, self._name, data)

    def close(self):
        if self._owner:
            self._ctx.close()


class GraphCommHandler(PvaCommHandler):

    def __init__(self, name, addr, ctx=None, timeout=1.0):
        errors = (TimeoutError, pct.RemoteError)
        if ctx is None:
            ctx = pct.Context('pva', nt=CUSTOM_TYPE_WRAPPERS)
            owner = True
        elif not isinstance(ctx, pct.Context):
            raise TypeError("%s only supports shared contexts of type %s not %s"
                            % (__class__, pct.Context, type(ctx)))
        else:
            owner = False
        super().__init__(name, addr, ctx, errors, owner, timeout=timeout)

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
        return self._proxy.command(cmd)

    def _query(self, cmd):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            return self._checked_get(pvname)

    def _try_request(self, cmd):
        try:
            matched = self._feature_req.match(cmd)
            if matched:
                if matched.group('type') == 'fetch':
                    return True, self._unchecked_get(self._get_data_pvname(matched.group('name')))
            else:
                pvname = self._get_pvname(cmd)
                if pvname is not None:
                    return True, self._unchecked_get(pvname)

            # if we fell through to here it is a failure
            return False, None
        except self._errors:
            return False, None

    def _request(self, cmd, check=False, retry=None, processing=None):
        if check:
            status, reply = self._try_request(cmd)
            if status:
                return self._process(processing, reply)
            elif retry is not None:
                status, reply = self._try_request(retry)
                if status:
                    return self._process(processing, reply)
        else:
            pvname = self._get_pvname(cmd)
            if pvname is not None:
                return self._process(processing, self._checked_get(pvname))

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
        return self._proxy.payload(cmd, self._serialize(payload))

    def _view(self, names):
        nodes = []
        for name in names:
            nodes.append(self._make_view_node(name, self.auto(name)))

        return self.add(nodes)

    def _get_current(self):
        return self._name

    def _set_current(self, name):
        self._set_name(name)
        if name in self.active:
            return True
        else:
            return self.create()

    def _load(self, filename):
        with open(filename, 'rb') as cnf:
            self.update(dill.load(cnf))

    def _save(self, filename):
        with open(filename, 'wb') as cnf:
            dill.dump(self.graph, cnf)


class AsyncGraphCommHandler(PvaCommHandler):

    def __init__(self, name, addr, ctx=None, timeout=1.0):
        errors = (asyncio.TimeoutError, pca.RemoteError)
        if ctx is None:
            ctx = pca.Context('pva', nt=CUSTOM_TYPE_WRAPPERS)
            owner = True
        elif not isinstance(ctx, pca.Context):
            raise TypeError("%s only supports shared contexts of type %s not %s"
                            % (__class__, pca.Context, type(ctx)))
        else:
            owner = False
        super().__init__(name, addr, ctx, errors, owner, timeout=timeout)

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
        return await self._proxy.command(cmd)

    async def _query(self, cmd):
        pvname = self._get_pvname(cmd)
        if pvname is not None:
            return await self._checked_get(pvname)

    async def _try_request(self, cmd):
        try:
            matched = self._feature_req.match(cmd)
            if matched:
                if matched.group('type') == 'fetch':
                    return True, await self._unchecked_get(self._get_data_pvname(matched.group('name')))
            else:
                pvname = self._get_pvname(cmd)
                if pvname is not None:
                    return True, await self._unchecked_get(pvname)

            # if we fell through to here it is a failure
            return False, None
        except self._errors:
            return False, None

    async def _request(self, cmd, check=False, retry=None, processing=None):
        if check:
            status, reply = await self._try_request(cmd)
            if status:
                return self._process(processing, reply)
            elif retry is not None:
                status, reply = await self._try_request(retry)
                if status:
                    return self._process(processing, reply)
        else:
            pvname = self._get_pvname(cmd)
            if pvname is not None:
                return self._process(processing, await self._checked_get(pvname))

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
        return await self._proxy.payload(cmd, self._serialize(payload))

    async def _view(self, names):
        nodes = []
        for name in names:
            nodes.append(self._make_view_node(name, self.auto(name)))

        return await self.add(nodes)

    async def _get_current(self):
        return self._name

    async def _set_current(self, name):
        self._set_name(name)
        if name in await self.active:
            return True
        else:
            return await self.create()

    async def _load(self, filename):
        with open(filename, 'rb') as cnf:
            graph = dill.load(cnf)
        return await self.update(graph)

    async def _save(self, filename):
        graph = await self.graph
        with open(filename, 'wb') as cnf:
            return dill.dump(graph, cnf)
