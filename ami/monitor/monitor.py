import asyncio
import logging
import zmq
import numpy as np
import panel as pn
import holoviews as hv
from ami import LogConfig
from ami.comm import ZMQ_TOPIC_DELIM
from ami.data import Deserializer


logger = logging.getLogger(LogConfig.get_package_name(__name__))
pn.extension()
hv.extension('bokeh')


class Monitor():

    def __init__(self, graph, export_addr, view_addr):
        self.graph = graph
        self.export_addr = export_addr
        self.view_addr = view_addr

        self.tasks = []
        self.ctx = zmq.asyncio.Context()
        self.poller = zmq.asyncio.Poller()

        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(self.export_addr)

        self.sockets = {}
        self.pipes = {}
        self.plots = {}

        self.deserializer = Deserializer()

        self.source_select = pn.widgets.Select(name='Source', options=[])
        self.source_select.param.watch(self.source_selected, 'value')
        self.row = pn.Row(self.source_select)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        for name, sock in self.sockets.items():
            self.poller.unregister(sock)
            sock.close()

        self.export.close()
        self.ctx.destroy()

    async def run(self, loop):
        asyncio.create_task(self.process_msg())
        asyncio.create_task(self.fetch())
        asyncio.create_task(self.start_server(loop))

    async def start_server(self, loop):
        self.server = pn.serve(self.row, loop=loop)

    def source_selected(self, event):
        if event.new not in self.sockets:
            topic = event.new
            pipe = hv.streams.Pipe(data=[])
            plot = hv.DynamicMap(hv.Curve, streams=[pipe])
            self.row.append(plot)
            self.pipes[topic] = pipe
            self.plots[topic] = plot

            sub_topic = "view:%s:%s" % (self.graph, topic)
            sock = self.ctx.socket(zmq.SUB)
            sock.setsockopt_string(zmq.SUBSCRIBE, sub_topic + ZMQ_TOPIC_DELIM)
            sock.connect(self.view_addr)
            self.poller.register(sock, zmq.POLLIN)
            self.sockets[topic] = sock

    async def fetch(self):
        while True:
            for sock, flag in await self.poller.poll(timeout=1):
                if flag != zmq.POLLIN:
                    continue
                topic = await sock.recv_string()
                topic = topic.rstrip('\0')
                _ = await sock.recv_pyobj()
                reply = await sock.recv_serialized(self.deserializer, copy=False)

                pipe = topic.split(':')[-1]
                pipe = self.pipes[pipe]
                pipe.send((np.arange(0, len(reply)), reply))

    async def process_msg(self):
        while True:
            topic = await self.export.recv_string()
            graph = await self.export.recv_string()
            exports = await self.export.recv_pyobj()

            if self.graph != graph:
                continue

            if topic == 'store':
                self.features = exports['features']

                if not self.features:
                    continue

                self.source_select.options = {k[6:]: k for k in self.features.keys() if k.startswith('_auto_')}
