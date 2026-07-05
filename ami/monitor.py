#!/usr/bin/env python
import argparse
import asyncio
import datetime as dt
import logging
import sys

import holoviews as hv
import numpy as np
import panel as pn
import zmq
import zmq.asyncio
from bokeh.models.ranges import DataRange1d

from ami import Defaults, LogConfig
from ami.client import GraphMgrAddress
from ami.comm import PlatformAction, Ports
from ami.data import Deserializer

logger = logging.getLogger(__name__)
pn.extension()
hv.extension("bokeh")
pn.config.sizing_mode = "scale_both"
logo = "data:image/webp;base64,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"  # noqa: E501


def hook(plot, element):
    # work around for this issue: https://github.com/holoviz/holoviews/issues/2441
    plot.state.x_range = DataRange1d(follow="end", follow_interval=60000, range_padding=0)
    plot.state.y_range = DataRange1d(follow="end", follow_interval=60000, range_padding=0)


options = {
    "axiswise": True,
    "framewise": True,
    "shared_axes": False,
    "show_grid": True,
    "tools": ["hover"],
    "responsive": True,
    "min_height": 200,
    "min_width": 200,
    "hooks": [hook],
}
hv.opts.defaults(
    hv.opts.Curve(**options), hv.opts.Scatter(**options), hv.opts.Image(**options), hv.opts.Histogram(**options)
)
row_step = 3
col_step = 4


class AsyncFetcher:
    """Single shared data fetcher for all plot widgets.

    Subscribes to heartbeat notifications on the export XPUB socket, then
    issues a single batched REQ/REP call for all features needed by registered
    widgets. This avoids N separate ZMQ round-trips.
    """

    def __init__(self, addr, ctx):
        self.addr = addr
        self.ctx = ctx
        self.deserializer = Deserializer()
        self.heartbeat_timestamp = 0
        self.widgets = {}  # name -> PlotWidget

        # Subscribe to heartbeat notifications on the export socket
        self.export = ctx.socket(zmq.SUB)
        self.export.connect(addr.export)
        self.export.setsockopt_string(zmq.SUBSCRIBE, "heartbeat")

        # REQ socket for batch view data requests
        self.view = ctx.socket(zmq.REQ)
        self.view.connect(addr.view)

    def register(self, name, widget):
        self.widgets[name] = widget

    def unregister(self, name):
        self.widgets.pop(name, None)

    async def run(self):
        while True:
            # Wait for heartbeat notification from manager
            await self.export.recv_string()  # topic, unused
            graph = await self.export.recv_string()
            heartbeat = await self.export.recv_pyobj()

            if graph != self.addr.name:
                continue
            if heartbeat.timestamp <= self.heartbeat_timestamp:
                continue
            self.heartbeat_timestamp = heartbeat.timestamp

            if not self.widgets:
                continue

            # Collect all unique features needed by all active widgets
            all_features = set()
            for widget in self.widgets.values():
                all_features.update(widget.topics.values())

            if not all_features:
                continue

            # Single batch request for all features
            requests = [f"view:{self.addr.name}:{f}" for f in all_features]
            await self.view.send_pyobj(requests)
            response = await self.view.recv_serialized(self.deserializer, copy=False)

            batch_data = response.get("data", {})
            resp_heartbeat = response.get("heartbeat", heartbeat)

            # Distribute data to each registered widget
            for widget in self.widgets.values():
                widget_data = {}
                for input_name, feature in widget.topics.items():
                    val = batch_data.get(feature)
                    if val is None:
                        continue
                    # Skip 0-dimensional numpy arrays
                    if isinstance(val, np.ndarray) and val.ndim == 0:
                        continue
                    widget_data[input_name] = val
                if widget_data:
                    widget.data_updated(widget_data)
                    widget.update_latency(resp_heartbeat)

    def close(self):
        self.export.close()
        self.view.close()


class PlotWidget:

    def __init__(self, topics=None, terms=None, name="", idx=(0, 0), **kwargs):
        self.topics = topics  # {input_name: feature_name}
        self.terms = terms
        self.name = name
        self.idx = idx
        self.pipes = {}
        self._plot = None
        self._latency_lbl = pn.widgets.StaticText()

        if kwargs.get("pipes", True):
            for term, input_name in terms.items():
                self.pipes[input_name] = hv.streams.Pipe(data=[])

    def data_updated(self, data):
        pass  # Overridden by subclasses

    def update_latency(self, heartbeat):
        now = dt.datetime.now()
        latency = now - dt.datetime.fromtimestamp(heartbeat.timestamp)
        self._latency_lbl.value = f"<b>{self.name}<br/>Last Updated: {now:%T}<br/>Latency: {latency}</b>"

    @property
    def plot(self):
        return self._plot

    @property
    def latency(self):
        return self._latency_lbl


class ScalarWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, **kwargs)
        self._plot = pn.Row(pn.widgets.StaticText(value=f"<b>{self.name}:</b>"), pn.widgets.StaticText())

    def data_updated(self, data):
        for term, name in self.terms.items():
            if name in data:
                self._plot[-1].value = str(data[name])


class ObjectWidget(ScalarWidget):

    def data_updated(self, data):
        for k, v in data.items():
            txt = f"variable: {k}<br/>type: {type(v)}<br/>value: {v}"
            if type(v) is np.ndarray:
                txt += f"<br/>shape: {v.shape}<br/>dtype: {v.dtype}"
            self._plot[-1].value = txt


class ImageWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, **kwargs)
        self._plot = hv.DynamicMap(self.trace(), streams=list(self.pipes.values())).hist().opts(toolbar="right")

    def data_updated(self, data):
        for term, name in self.terms.items():
            if name in data:
                self.pipes[name].send(data[name])

    def trace(self):
        def func(data):
            x1, y1 = getattr(data, "shape", (0, 0))
            img = hv.Image(data, bounds=(0, 0, x1, y1)).opts(colorbar=True)
            return img

        return func


class HistogramWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, pipes=False, **kwargs)
        self.num_terms = int(len(terms) / 2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            y = self.terms[f"Counts.{i}" if i > 0 else "Counts"]
            self.pipes[y] = hv.streams.Pipe(data=[])
            plots.append(hv.DynamicMap(lambda data: hv.Histogram(data), streams=[self.pipes[y]]))

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for i in range(0, self.num_terms):
            x = self.terms[f"Bins.{i}" if i > 0 else "Bins"]
            y = self.terms[f"Counts.{i}" if i > 0 else "Counts"]
            name = y

            if x not in data or y not in data:
                continue

            x = data[x]
            y = data[y]

            self.pipes[name].send((x, y))


class Histogram2DWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, pipes=False, **kwargs)
        self.pipes["Counts"] = hv.streams.Pipe(data=[])
        self._plot = (
            hv.DynamicMap(lambda data: hv.Image(data).opts(colorbar=True), streams=list(self.pipes.values()))
            .hist()
            .opts(toolbar="right")
        )

    def data_updated(self, data):
        xbins_key = self.terms["XBins"]
        ybins_key = self.terms["YBins"]
        counts_key = self.terms["Counts"]

        if xbins_key not in data or ybins_key not in data or counts_key not in data:
            return

        xbins = data[xbins_key]
        ybins = data[ybins_key]
        counts = data[counts_key]
        self.pipes["Counts"].send((xbins, ybins, counts.transpose()))


class ScatterWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, pipes=False, **kwargs)
        self.num_terms = int(len(terms) / 2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))
            self.pipes[name] = hv.streams.Pipe(data=[])
            plots.append(
                hv.DynamicMap(
                    lambda data: hv.Scatter(data, label=name).opts(framewise=True), streams=[self.pipes[name]]
                )
            )

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

            self.pipes[name].send((x, y))


class WaveformWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, **kwargs)
        plots = []

        for term, name in terms.items():
            plots.append(
                hv.DynamicMap(lambda data: hv.Curve(data, label=name).opts(framewise=True), streams=[self.pipes[name]])
            )

        self._plot = hv.Overlay(plots).collate() if len(plots) > 1 else plots[0]

    def data_updated(self, data):
        for term, name in self.terms.items():
            if name in data:
                self.pipes[name].send((np.arange(0, len(data[name])), data[name]))


class LineWidget(PlotWidget):

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, pipes=False, **kwargs)
        self.num_terms = int(len(terms) / 2) if terms else 0
        plots = []

        for i in range(0, self.num_terms):
            x = self.terms[f"X.{i}" if i > 0 else "X"]
            y = self.terms[f"Y.{i}" if i > 0 else "Y"]
            name = " vs ".join((y, x))
            self.pipes[name] = hv.streams.Pipe(data=[])
            plots.append(
                hv.DynamicMap(lambda data: hv.Curve(data, label=name).opts(framewise=True), streams=[self.pipes[name]])
            )

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

    def __init__(self, topics=None, terms=None, **kwargs):
        super().__init__(topics, terms, **kwargs)


class Monitor:

    def __init__(self, graphmgr_addr):
        self.graphmgr_addr = graphmgr_addr
        self.ctx = zmq.asyncio.Context()

        # Subscribe to store messages (plot metadata) on the export socket
        self.store_sub = self.ctx.socket(zmq.SUB)
        self.store_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self.store_sub.connect(self.graphmgr_addr.export)

        # Shared data fetcher (heartbeat + view REQ/REP)
        self.fetcher = AsyncFetcher(self.graphmgr_addr, self.ctx)

        self.lock = asyncio.Lock()
        self.plot_metadata = {}
        self.plots = {}

        # logo = "https://www6.slac.stanford.edu/sites/www6.slac.stanford.edu/files/SLAC_LogoSD_W.png"
        self.template = pn.template.ReactTemplate(title="AMI", header_background="#8c1515", logo=logo)

        self.enabled_plots = pn.widgets.CheckBoxGroup(name="Plots", options=[])
        self.enabled_plots.param.watch(self.plot_checked, "value")
        self.latency_lbls = pn.Column()
        self.tab = pn.Tabs(("Plots", self.enabled_plots), ("Latency", self.latency_lbls), dynamic=True)
        self.sidebar_col = pn.Column(self.tab)
        self.template.sidebar.append(self.sidebar_col)

        self.layout_widgets = {}
        self.layout = self.template.main
        for r in range(0, 12, row_step):
            for c in range(0, 12, col_step):
                col = pn.Column()
                self.layout_widgets[(r, c)] = col
                self.layout[r : r + row_step, c : c + col_step] = col

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        for name, plot in self.plots.items():
            plot.close()
            self.fetcher.unregister(name)

        self.fetcher.close()
        self.store_sub.close()
        self.ctx.destroy()

    async def run(self, address, http_port):
        asyncio.create_task(self.process_store_msgs())
        asyncio.create_task(self.fetcher.run())
        await self.start_server(address, http_port)

    async def start_server(self, address, http_port):
        self.server = pn.serve(
            self.template,
            address=address or "0.0.0.0",
            port=http_port,
            title="AMI",
            show=False,
            start=False,
        )
        self.server.start()
        logger.info("Monitor server started at http://%s:%d", address or "localhost", self.server.port)

    async def plot_checked(self, event):
        async with self.lock:
            names = self.enabled_plots.value

            for name in names:
                metadata = self.plot_metadata[name]

                if name in self.plots:
                    continue

                widget_cls_name = metadata["type"]
                if widget_cls_name not in globals():
                    logger.warning("Unsupported plot type: %s", widget_cls_name)
                    continue

                row, col = (0, 0)
                for key, column in self.layout_widgets.items():
                    if len(column) != 0:
                        continue

                    row, col = key
                    widget_cls = globals()[widget_cls_name]
                    widget = widget_cls(
                        topics=metadata["topics"],
                        terms=metadata["terms"],
                        name=name,
                        idx=(row, col),
                    )
                    self.plots[name] = widget
                    self.fetcher.register(name, widget)
                    column.append(pn.Card(widget.plot, title=name, min_height=300, min_width=300))
                    self.latency_lbls.append(widget.latency)
                    break

            removed_plots = set(self.plots.keys()).difference(names)
            for name in removed_plots:
                self.remove_plot(name)

    def remove_plot(self, name):
        self.fetcher.unregister(name)
        widget = self.plots.pop(name, None)
        if widget:
            row, col = widget.idx
            self.latency_lbls.remove(widget.latency)
            self.layout_widgets[(row, col)].clear()
            widget.close()

    async def process_store_msgs(self):
        while True:
            topic = await self.store_sub.recv_string()
            graph = await self.store_sub.recv_string()
            exports = await self.store_sub.recv_pyobj()

            if self.graphmgr_addr.name != graph:
                continue

            if topic == "store":
                async with self.lock:
                    plots = exports["plots"]
                    logger.info("Store message has %d plots: %s", len(plots), list(plots.keys()))
                    new_plots = set(plots.keys()).difference(self.plot_metadata.keys())
                    for name in new_plots:
                        self.plot_metadata[name] = plots[name]

                    removed_plots = set(self.plot_metadata.keys()).difference(plots.keys())
                    for name in removed_plots:
                        self.plot_metadata.pop(name, None)
                        self.remove_plot(name)

                    self.enabled_plots.options = list(self.plot_metadata.keys())


def run_monitor(graph_name, export_addr, view_addr, address, http_port):
    logger.info("Starting monitor")

    # GraphMgrAddress fields: name, comm, view, info, export
    # Monitor only needs export (heartbeats + store) and view (REQ/REP for data)
    graphmgr_addr = GraphMgrAddress(name=graph_name, comm=None, view=view_addr, info=None, export=export_addr)

    async def _run():
        with Monitor(graphmgr_addr) as mon:
            await mon.run(address, http_port)
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)

    asyncio.run(_run())


def main():
    parser = argparse.ArgumentParser(description="AMII GUI Client")

    parser.add_argument(
        "-H", "--host", default=Defaults.Host, help="hostname of the AMII Manager (default: %s)" % Defaults.Host
    )

    parser.add_argument(
        "-p", "--port", type=int, default=Ports.BasePort, action=PlatformAction, help="base port for AMI"
    )

    parser.add_argument("-l", "--listen-port", type=int, default=8787, help="http port for panel (default: 8787)")

    parser.add_argument("-a", "--address", type=str, default=None, help="address name for panel")

    parser.add_argument(
        "-g",
        "--graph-name",
        default=Defaults.GraphName,
        help="the name of the graph used (default: %s)" % Defaults.GraphName,
    )

    parser.add_argument(
        "--log-level",
        default=LogConfig.Level,
        help="the logging level of the application (default %s)" % LogConfig.Level,
    )

    parser.add_argument("--log-file", help="an optional file to write the log output to")

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


if __name__ == "__main__":
    sys.exit(main())
