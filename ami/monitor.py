#!/usr/bin/env python
import sys
import argparse
import asyncio
import logging
import pickle
import zmq
import tornado.ioloop
import datetime as dt
import numpy as np
import panel as pn
import holoviews as hv
from networkfox import modifiers
from ami import LogConfig, Defaults
from ami.client import GraphMgrAddress
from ami.comm import BasePort, Ports, ZMQ_TOPIC_DELIM
from ami.data import Deserializer
from bokeh.models.ranges import DataRange1d

logger = logging.getLogger(__name__)
pn.extension()
hv.extension('bokeh')
pn.config.sizing_mode = 'scale_both'


def hook(plot, element):
    plot.state.x_range = DataRange1d(follow='end', follow_interval=60000, range_padding=0)
    plot.state.y_range = DataRange1d(follow='end', follow_interval=60000, range_padding=0)


options = {'axiswise': True, 'framewise': True, 'shared_axes': False, 'show_grid': True, 'tools': ['hover'],
           'responsive': True, 'min_height': 200, 'min_width': 200, 'hooks': [hook]}
hv.opts.defaults(hv.opts.Curve(**options),
                 hv.opts.Scatter(**options),
                 hv.opts.Image(**options),
                 hv.opts.Histogram(**options))
row_step = 3
col_step = 4


class AsyncFetcher(object):

    def __init__(self, topics, terms, addr, ctx):
        self.addr = addr
        self.ctx = ctx
        self.poller = zmq.asyncio.Poller()
        self.sockets = {}
        self.data = {}
        self.timestamps = {}
        self.heartbeats = set()
        self.last_updated = ""
        self.deserializer = Deserializer()
        self.update_topics(topics, terms)

    @property
    def reply(self):
        self.heartbeats = set(self.timestamps.values())
        res = {}

        if self.data.keys() == self.subs and len(self.heartbeats) == 1:
            for name, topic in self.topics.items():
                res[name] = self.data[topic]

        elif self.optional.issuperset(self.data.keys()):
            for name, topic in self.topics.items():
                if topic in self.data:
                    res[name] = self.data[topic]

        return res

    def update_topics(self, topics, terms):
        self.topics = topics
        self.terms = terms
        self.names = list(topics.keys())
        self.subs = set(topics.values())
        self.optional = set([value for key, value in topics.items() if type(key) is modifiers.optional])

        for name, sock_count in self.sockets.items():
            sock, count = sock_count
            self.poller.unregister(sock)
            sock.close()

        self.sockets = {}
        self.view_subs = {}

        for term, name in terms.items():
            if name not in self.sockets:
                topic = topics[name]
                sub_topic = "view:%s:%s" % (self.addr.name, topic)
                self.view_subs[sub_topic] = topic
                sock = self.ctx.socket(zmq.SUB)
                sock.setsockopt_string(zmq.SUBSCRIBE, sub_topic + ZMQ_TOPIC_DELIM)
                sock.connect(self.addr.view)
                self.poller.register(sock, zmq.POLLIN)
                self.sockets[name] = (sock, 1)  # reference count
            else:
                sock, count = self.sockets[name]
                self.sockets[name] = (sock, count+1)

    async def fetch(self):
        for sock, flag in await self.poller.poll():
            if flag != zmq.POLLIN:
                continue
            topic = await sock.recv_string()
            topic = topic.rstrip('\0')
            heartbeat = await sock.recv_pyobj()
            reply = await sock.recv_serialized(self.deserializer, copy=False)
            self.data[self.view_subs[topic]] = reply
            self.timestamps[self.view_subs[topic]] = heartbeat

    def close(self):
        for name, sock_count in self.sockets.items():
            sock, count = sock_count
            self.poller.unregister(sock)
            sock.close()


class PlotWidget():

    def __init__(self, topics=None, terms=None, addr=None, ctx=None, **kwargs):
        self.fetcher = AsyncFetcher(topics, terms, addr, ctx)
        self.terms = terms

        self.name = kwargs.get('name', '')
        self.idx = kwargs.get('idx', (0, 0))
        self.pipes = {}
        self._plot = None
        self._latency_lbl = pn.widgets.StaticText()

        if kwargs.get('pipes', True):
            for term, name in terms.items():
                self.pipes[name] = hv.streams.Pipe(data=[])

    async def update(self):
        while True:
            await self.fetcher.fetch()
            if self.fetcher.reply:
                self.data_updated(self.fetcher.reply)
                heartbeat = self.fetcher.heartbeats.pop()
                now = dt.datetime.now()
                now = now.strftime("%T")
                latency = (dt.datetime.now() - dt.datetime.fromtimestamp(heartbeat.timestamp))
                last_updated = f"<b>{self.name}<br/>Last Updated: {now}<br/>Latency: {latency}</b>"
                self._latency_lbl.value = last_updated

    def close(self):
        self.fetcher.close()

    @property
    def plot(self):
        return self._plot

    @property
    def latency(self):
        return self._latency_lbl


class ScalarWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, **kwargs)
        self._plot = pn.Row(pn.widgets.StaticText(value=f"<b>{self.name}:</b>"), pn.widgets.StaticText())

    def data_updated(self, data):
        for term, name in self.terms.items():
            self._plot[-1].value = str(data[name])


class ObjectWidget(ScalarWidget):

    def data_updated(self, data):
        for k, v in data.items():
            txt = f"variable: {k}<br/>type: {type(v)}<br/>value: {v}"
            if type(v) is np.ndarray:
                txt += f"<br/>shape: {v.shape}<br/>dtype: {v.dtype}"
            self._plot[-1].value = txt


class ImageWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, **kwargs)
        self._plot = hv.DynamicMap(self.trace(),
                                   streams=list(self.pipes.values())).hist().opts(toolbar='right')

    def data_updated(self, data):
        for term, name in self.terms.items():
            self.pipes[name].send(data[name])

    def trace(self):
        def func(data):
            x1, y1 = getattr(data, 'shape', (0, 0))
            img = hv.Image(data, bounds=(0, 0, x1, y1)).opts(colorbar=True)
            return img

        return func


class HistogramWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, pipes=False, **kwargs)
        self.num_terms = int(len(terms)/2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            y = self.terms[f"Counts.{i}" if i > 0 else "Counts"]
            self.pipes[y] = hv.streams.Pipe(data=[])
            plots.append(hv.DynamicMap(lambda data: hv.Histogram(data),
                                       streams=[self.pipes[y]]))

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"Bins.{i}" if i > 0 else "Bins"]
            y = self.terms[f"Counts.{i}" if i > 0 else "Counts"]
            name = y

            x = data[x]
            y = data[y]

            self.pipes[name].send((x, y))


class Histogram2DWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, pipes=False, **kwargs)
        self.pipes['Counts'] = hv.streams.Pipe(data=[])
        self._plot = hv.DynamicMap(lambda data: hv.Image(data).opts(colorbar=True),
                                   streams=list(self.pipes.values())).hist().opts(toolbar='right')

    def data_updated(self, data):
        xbins = data[self.terms['XBins']]
        ybins = data[self.terms['YBins']]
        counts = data[self.terms['Counts']]
        self.pipes['Counts'].send((xbins, ybins, counts.transpose()))


class ScatterWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, pipes=False, **kwargs)
        self.num_terms = int(len(terms)/2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))
            self.pipes[name] = hv.streams.Pipe(data=[])
            plots.append(hv.DynamicMap(lambda data: hv.Scatter(data, label=name).opts(framewise=True),
                                       streams=[self.pipes[name]]))

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            x = data[x]
            y = data[y]

            self.pipes[name].send((x, y))


class WaveformWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, **kwargs)
        plots = []

        for term, name in terms.items():
            plots.append(hv.DynamicMap(lambda data: hv.Curve(data, label=name).opts(framewise=True),
                                       streams=[self.pipes[name]]))

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for term, name in self.terms.items():
            self.pipes[name].send((np.arange(0, len(data[name])), data[name]))


class LineWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, pipes=False, **kwargs)
        self.num_terms = int(len(terms)/2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))
            self.pipes[name] = hv.streams.Pipe(data=[])
            plots.append(hv.DynamicMap(lambda data: hv.Curve(data, label=name).opts(framewise=True),
                                       streams=[self.pipes[name]]))

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))

            if x not in data or y not in data:
                continue

            x = data[x]
            y = data[y]
            # sort the data using the x-axis, otherwise the drawn line is messed up
            x, y = zip(*sorted(zip(x, y)))
            self.pipes[name].send((x, y))


class TimeWidget(LineWidget):

    def __init__(self, topics=None, terms=None, addr=None, **kwargs):
        super().__init__(topics, terms, addr, **kwargs)


class Monitor():

    def __init__(self, graphmgr_addr):
        self.graphmgr_addr = graphmgr_addr
        self.ctx = zmq.asyncio.Context()

        self.export = self.ctx.socket(zmq.SUB)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "")
        self.export.connect(self.graphmgr_addr.comm)

        self.lock = asyncio.Lock()
        self.plot_metadata = {}
        self.plots = {}
        self.tasks = {}

        logo = 'https://www6.slac.stanford.edu/sites/www6.slac.stanford.edu/files/SLAC_LogoSD_W.png'
        self.template = pn.template.ReactTemplate(title='AMI', header_background='#8c1515',
                                                  logo=logo)

        self.enabled_plots = pn.widgets.CheckBoxGroup(name='Plots', options=[])
        self.enabled_plots.param.watch(self.plot_checked, 'value')
        self.latency_lbls = pn.Column()
        self.tab = pn.Tabs(('Plots', self.enabled_plots),
                           ('Latency', self.latency_lbls),
                           dynamic=True)
        self.sidebar_col = pn.Column(self.tab)
        self.template.sidebar.append(self.sidebar_col)

        self.layout_widgets = {}
        self.layout = self.template.main
        for r in range(0, 12, row_step):
            for c in range(0, 12, col_step):
                col = pn.Column()
                self.layout_widgets[(r, c)] = col
                self.layout[r:r+row_step, c:c+col_step] = col

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        for name, plot in self.plots.items():
            plot.close()

        self.export.close()
        self.ctx.destroy()

    async def run(self, loop, address, http_port):
        asyncio.create_task(self.process_msg())
        asyncio.create_task(self.start_server(loop, address, http_port))
        asyncio.create_task(self.monitor_tasks())

    async def start_server(self, loop, address, http_port):
        self.server = pn.serve(self.template, address=address, port=http_port,
                               loop=loop, title="AMI", show=False)

    async def monitor_tasks(self):
        while True:
            async with self.lock:
                cancelled_tasks = set()
                for name, task in self.tasks.items():
                    try:
                        raise task.exception()
                    except asyncio.CancelledError:
                        cancelled_tasks.add(name)
                    except pickle.UnpicklingError:
                        continue
                    except asyncio.InvalidStateError:
                        continue

                for name in cancelled_tasks:
                    self.tasks.pop(name, None)

            await asyncio.sleep(1)

    async def plot_checked(self, event):
        async with self.lock:
            names = self.enabled_plots.value

            for name in names:
                metadata = self.plot_metadata[name]

                if name in self.plots:
                    continue

                if metadata['type'] not in globals():
                    print("UNSUPPORTED PLOT TYPE:", metadata['type'])
                    continue

                row, col = (0, 0)
                for key, column in self.layout_widgets.items():
                    if len(column) != 0:
                        continue

                    row, col = key
                    widget = globals()[metadata['type']]
                    widget = widget(topics=metadata['topics'], terms=metadata['terms'],
                                    addr=self.graphmgr_addr, name=name, idx=(row, col), ctx=self.ctx)
                    self.plots[name] = widget
                    column.append(pn.Card(widget.plot, title=name, min_height=300, min_width=300))
                    self.latency_lbls.append(widget.latency)
                    self.tasks[name] = asyncio.create_task(widget.update())
                    break

            removed_plots = set(self.plots.keys()).difference(names)
            for name in removed_plots:
                self.remove_plot(name)

    def remove_plot(self, name):
        task = self.tasks.get(name, None)
        if task and not task.cancelled():
            task.cancel()
        widget = self.plots.pop(name, None)
        if widget:
            row, col = widget.idx
            self.latency_lbls.remove(widget.latency)
            self.layout_widgets[(row, col)].clear()
            widget.close()

    async def process_msg(self):
        while True:
            topic = await self.export.recv_string()
            graph = await self.export.recv_string()
            exports = await self.export.recv_pyobj()

            if self.graphmgr_addr.name != graph:
                continue

            if topic == 'store':
                async with self.lock:
                    plots = exports['plots']
                    new_plots = set(plots.keys()).difference(self.plot_metadata.keys())
                    for name in new_plots:
                        self.plot_metadata[name] = plots[name]

                    removed_plots = set(self.plot_metadata.keys()).difference(plots.keys())
                    for name in removed_plots:
                        self.plot_metadata.pop(name, None)
                        self.remove_plot(name)

                    logger.debug('Received plots: %s', self.plot_metadata.keys())
                    self.enabled_plots.options = list(self.plot_metadata.keys())


def run_monitor(graph_name, export_addr, view_addr, address, http_port):
    logger.info('Starting monitor')

    graphmgr_addr = GraphMgrAddress(graph_name, export_addr, view_addr, None)

    loop = tornado.ioloop.IOLoop.current()
    with Monitor(graphmgr_addr) as mon:
        asyncio.ensure_future(mon.run(loop, address, http_port))
        loop.start()


def main():
    parser = argparse.ArgumentParser(description='AMII GUI Client')

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=BasePort,
        help='base port for AMI'
    )

    parser.add_argument(
        '-l',
        '--listen-port',
        type=int,
        default=0,
        help='http port for panel'
    )

    parser.add_argument(
        '-a',
        '--address',
        type=str,
        default=None,
        help='address name for panel'
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
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
    graph = args.graph_name
    export_addr = "tcp://%s:%d" % (args.host, args.port + Ports.Export)
    view_addr = "tcp://%s:%d" % (args.host, args.port + Ports.View)
    http_port = args.listen_port
    address = args.address

    log_handlers = [logging.StreamHandler()]
    if args.log_file is not None:
        log_handlers.append(logging.FileHandler(args.log_file))
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig(format=LogConfig.Format, level=log_level, handlers=log_handlers)

    try:
        return run_monitor(graph, export_addr, view_addr, address, http_port)
    except KeyboardInterrupt:
        logger.info("Monitor killed by user...")
        return 0


if __name__ == '__main__':
    sys.exit(main())
