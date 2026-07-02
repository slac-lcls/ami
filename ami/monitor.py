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
            try:
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
            except Exception:
                logger.exception("Error in AsyncFetcher.run")
                await asyncio.sleep(1)

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

    def close(self):
        pass

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

        logo = "https://www6.slac.stanford.edu/sites/www6.slac.stanford.edu/files/SLAC_LogoSD_W.png"
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
            try:
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
            except Exception:
                logger.exception("Error in process_store_msgs")
                await asyncio.sleep(1)


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
