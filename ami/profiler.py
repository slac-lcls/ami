import argparse
import collections
import logging
import asyncio
import datetime as dt
import sys
import zmq
import zmq.asyncio
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
from ami import Defaults
from ami.data import Deserializer
from ami.comm import Ports
from ami.asyncqt import QEventLoop
from ami.flowchart.library.DisplayWidgets import symbols_colors

logger = logging.getLogger(__name__)


class HeartbeatData(object):

    def __init__(self, heartbeat, metadata, parents, graph):
        self.heartbeat = heartbeat
        self.metadata = dict(metadata)
        self.graph = graph
        self.parent = parents

        self.num_events = {}  # {worker : events}

        self.worker_time_per_heartbeat = {}  # {worker : {node : time}}
        self.worker_average = collections.defaultdict(list)  # {node : times}

        self.local_collector_time_per_heartbeat = {}  # {localCollector : {node : time}}
        self.local_collector_average = collections.defaultdict(list)  # {node : times}

        self.total_time_per_heartbeat = collections.defaultdict(lambda: 0)

    def add_worker_data(self, worker, data):
        self.num_events[worker] = len(data[self.graph])
        time_per_heartbeat = 0
        node_time_per_heartbeat = collections.defaultdict(lambda: 0)

        if self.graph not in data:
            return

        for event in data[self.graph]:
            time_per_event = np.sum(list(event.values()))
            time_per_heartbeat += time_per_event
            for node, time in event.items():
                try:
                    parent = self.metadata[node]['parent']
                    node_time_per_heartbeat[parent] += time
                except KeyError as e:
                    print(e, self.heartbeat, self.metadata['heartbeat'])

        for node, time in node_time_per_heartbeat.items():
            self.worker_average[node].append(time)

        self.worker_time_per_heartbeat[worker] = node_time_per_heartbeat

    def add_local_collector_data(self, localCollector, data):
        node_time_per_heartbeat = collections.defaultdict(lambda: 0)

        if self.graph not in data:
            return

        for node, time in data[self.graph].items():
            try:
                parent = self.metadata[node]['parent']
            except KeyError as e:
                print(e, self.heartbeat, self.metadata['heartbeat'])

            node_time_per_heartbeat[parent] += time

        for node, time in node_time_per_heartbeat.items():
            self.local_collector_average[node].append(time)

        self.local_collector_time_per_heartbeat[localCollector] = node_time_per_heartbeat

    def add_global_collector_data(self, data):
        if self.graph not in data:
            return

        for node, time in data[self.graph].items():
            parent = self.metadata[node]['parent']
            self.total_time_per_heartbeat[parent] += time

        for node, times in self.worker_average.items():
            self.total_time_per_heartbeat[node] += np.average(times)

        for node, times in self.local_collector_average.items():
            self.total_time_per_heartbeat[node] += np.average(times)

        self.total_heartbeat_time = np.sum(list(self.total_time_per_heartbeat.values()))


class ProfilerWindow(QtGui.QMainWindow):

    def __init__(self, proc):
        super().__init__()
        self.proc = proc

    def closeEvent(self, event):
        self.proc.cancel()
        self.destroy()
        event.ignore()


class Profiler(QtCore.QObject):

    def __init__(self, broker_addr="", profile_addr="", graph_name="graph", loop=None):
        super().__init__()

        if loop is None:
            self.app = QtGui.QApplication([])
            loop = QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        self.ctx = zmq.asyncio.Context()

        if broker_addr:
            self.broker = self.ctx.socket(zmq.SUB)
            self.broker.setsockopt_string(zmq.SUBSCRIBE, 'profiler')
            self.broker.connect(broker_addr)
        else:
            self.broker = None

        self.profile_addr = profile_addr
        self.profile = self.ctx.socket(zmq.SUB)
        self.profile.setsockopt_string(zmq.SUBSCRIBE, '')
        self.task = None

        self.graph_name = graph_name
        self.deserializer = Deserializer()
        self.metadata = None
        self.parents = set()

        self.heartbeat_data = {}

        self.widget = QtWidgets.QWidget()
        self.layout = QtGui.QGridLayout(self.widget)
        self.widget.setLayout(self.layout)

        self.enabled_nodes = {}
        self.trace_layout = QtGui.QFormLayout(self.widget)
        hbox = QtWidgets.QHBoxLayout(self.widget)
        selectAll = QtWidgets.QPushButton("Select All", self.widget)
        unselectAll = QtWidgets.QPushButton("Unselect All", self.widget)
        hbox.addWidget(selectAll)
        hbox.addWidget(unselectAll)
        self.trace_layout.addRow(hbox)
        self.layout.addLayout(self.trace_layout, 0, 0, -1, 1)

        self.graphicsLayoutWidget = pg.GraphicsLayoutWidget()
        self.layout.addWidget(self.graphicsLayoutWidget, 0, 1, -1, -1)

        self.time_per_heartbeat = self.graphicsLayoutWidget.addPlot(row=0, col=0)
        self.time_per_heartbeat.showGrid(True, True)
        self.time_per_heartbeat.setLabel('bottom', "Heartbeat")
        self.time_per_heartbeat.setLabel('left', "Time (Sec)")
        self.time_per_heartbeat_traces = {}  # {name : PlotDataItem}
        self.time_per_heartbeat_data = collections.defaultdict(lambda: np.array([np.nan]*100))
        self.time_per_heartbeat_legend = self.time_per_heartbeat.addLegend()

        self.heartbeats_per_second = self.graphicsLayoutWidget.addPlot(row=0, col=1)
        self.heartbeats_per_second.showGrid(True, True)
        self.heartbeats_per_second.setLabel('bottom', "Heartbeat")
        self.heartbeats_per_second.setLabel('left', "Heartbeats/Second")
        self.heartbeats_per_second_data = np.array([np.nan]*100)
        self.heartbeats_per_second_trace = None

        self.percent_per_heartbeat = self.graphicsLayoutWidget.addPlot(row=1, col=0, rowspan=1, colspan=2)
        self.percent_per_heartbeat.showGrid(True, True)
        self.percent_per_heartbeat_trace = None
        self.percent_per_heartbeat_data = collections.defaultdict(lambda: 0)

        self.last_updated = pg.LabelItem(parent=self.time_per_heartbeat.getViewBox())
        self.total_heartbeat_time = pg.LabelItem(parent=self.percent_per_heartbeat.getViewBox())
        self.heartbeat_per_second = pg.LabelItem(parent=self.heartbeats_per_second.getViewBox())

        self.win = ProfilerWindow(self)
        self.win.setWindowTitle('Profiler')
        self.win.setCentralWidget(self.widget)
        self.win.show()

        with loop:
            loop.run_until_complete(asyncio.gather(self.process_broker_message(), self.monitor()))

    async def monitor(self):

        while self.task is None:
            await asyncio.sleep(0.1)

        try:
            await self.task
        except asyncio.CancelledError:
            pass

    async def process_broker_message(self):
        if self.broker is None:
            self.connect()
            return

        while True:
            await self.broker.recv_string()
            msg = await self.broker.recv_pyobj()
            self.graph_name = msg.name
            self.connect()
            self.win.show()

    def connect(self):
        if self.task is None:
            self.profile.connect(self.profile_addr)
            self.task = asyncio.ensure_future(self.process_profile_data())
            self.connected = True

    def cancel(self):
        self.task.cancel()
        self.task = None
        self.profile.disconnect(self.profile_addr)

    async def process_profile_data(self):
        while True:
            topic = await self.profile.recv_string()
            name = await self.profile.recv_string()
            data = await self.profile.recv_serialized(self.deserializer, copy=False)

            if topic == "profile":
                heartbeat = data['heartbeat']

                if heartbeat not in self.heartbeat_data:
                    self.heartbeat_data[heartbeat] = HeartbeatData(data['heartbeat'],
                                                                   self.metadata,
                                                                   self.parents,
                                                                   self.graph_name)
                heartbeat_data = self.heartbeat_data[heartbeat]

                if name.startswith('worker'):
                    print(name, heartbeat_data.heartbeat, heartbeat_data.metadata['heartbeat'])
                    heartbeat_data.add_worker_data(name, data)
                elif name.startswith('localCollector'):
                    print(name, heartbeat_data.heartbeat, heartbeat_data.metadata['heartbeat'])
                    heartbeat_data.add_local_collector_data(name, data)
                elif name.startswith('globalCollector'):
                    print(name, heartbeat_data.heartbeat, heartbeat_data.metadata['heartbeat'])
                    heartbeat_data.add_global_collector_data(data)

                    self.time_per_heartbeat_data["heartbeat"][-1] = heartbeat
                    self.time_per_heartbeat_data["heartbeat"] = np.roll(self.time_per_heartbeat_data["heartbeat"], -1)

                    for node, time in heartbeat_data.total_time_per_heartbeat.items():
                        self.time_per_heartbeat_data[node][-1] = time
                        self.time_per_heartbeat_data[node] = np.roll(self.time_per_heartbeat_data[node], -1)
                        self.percent_per_heartbeat_data[node] = time/heartbeat_data.total_heartbeat_time

                    i = 0
                    for node, times in self.time_per_heartbeat_data.items():
                        if node == "heartbeat":
                            continue

                        if node not in self.time_per_heartbeat_traces:
                            symbol, color = symbols_colors[i]
                            self.time_per_heartbeat_traces[node] = self.time_per_heartbeat.plot(
                                x=self.time_per_heartbeat_data["heartbeat"], y=times, name=node,
                                symbol=symbol, symbolBrush=color)
                            i += 1
                        else:
                            self.time_per_heartbeat_traces[node].setData(
                                x=self.time_per_heartbeat_data["heartbeat"],
                                y=times)

                    nodes, times = zip(*self.percent_per_heartbeat_data.items())

                    if self.percent_per_heartbeat_trace is None:
                        x = np.arange(len(nodes))
                        self.percent_per_heartbeat_trace = pg.BarGraphItem(x=x,
                                                                           height=times,
                                                                           width=1, brush='b')
                        self.percent_per_heartbeat.addItem(self.percent_per_heartbeat_trace)
                        xticks = dict(zip(x, nodes))
                        ax = self.percent_per_heartbeat.getAxis('bottom')
                        ax.setTicks([xticks.items()])
                    else:
                        self.percent_per_heartbeat_trace.setOpts(height=times)

                    self.heartbeats_per_second_data[-1] = 1/heartbeat_data.total_heartbeat_time
                    self.heartbeats_per_second_data = np.roll(self.heartbeats_per_second_data, -1)
                    if self.heartbeats_per_second_trace is None:
                        symbol, color = symbols_colors[0]
                        self.heartbeats_per_second_trace = self.heartbeats_per_second.plot(
                            x=self.time_per_heartbeat_data["heartbeat"],
                            y=self.heartbeats_per_second_data,
                            symbol=symbol, symbolBrush=color)
                    else:
                        self.heartbeats_per_second_trace.setData(
                            x=self.time_per_heartbeat_data["heartbeat"],
                            y=self.heartbeats_per_second_data)

                    now = dt.datetime.now()
                    now = now.strftime("%H:%M:%S")
                    last_updated = f"Last Updated: {now}"
                    self.last_updated.setText(last_updated)
                    text = f"Seconds/Heartbeat: {heartbeat_data.total_heartbeat_time:.6f}<br/>Heartbeat: {heartbeat}"
                    self.total_heartbeat_time.setText(text)
                    text = f"Heartbeats/Second: {1/heartbeat_data.total_heartbeat_time:.0f}<br/>Heartbeat: {heartbeat}"
                    self.heartbeat_per_second.setText(text)

                    del self.heartbeat_data[heartbeat]

            elif topic == "metadata":
                if name != self.graph_name:
                    continue

                heartbeat = data['heartbeat']
                logger.info("Received %s metadata for heartbeat %d", self.graph_name, heartbeat)

                self.metadata = data

                self.time_per_heartbeat_data = collections.defaultdict(lambda: np.array([np.nan]*100))
                self.time_per_heartbeat_traces = {}
                self.time_per_heartbeat_legend.clear()

                if self.percent_per_heartbeat_trace:
                    self.percent_per_heartbeat.removeItem(self.percent_per_heartbeat_trace)
                    self.percent_per_heartbeat_trace = None

                self.heartbeats_per_second_data = np.array([np.nan]*100)

                old_parents = set(self.parents)
                self.parents = set()
                for k, v in data.items():
                    if k == 'heartbeat':
                        continue

                    parent = v['parent']
                    self.parents.add(parent)
                    if parent not in self.enabled_nodes:
                        widget = QtWidgets.QCheckBox(self.widget)
                        widget.setCheckState(QtCore.Qt.Checked)
                        self.enabled_nodes[parent] = widget
                        self.trace_layout.addRow(parent, widget)

                deleted_nodes = old_parents.difference(self.parents)
                for node in deleted_nodes:
                    self.trace_layout.removeRow(self.enabled_nodes[node])


def main():
    parser = argparse.ArgumentParser(description="AMII Profiler")

    parser.add_argument(
        '-H',
        '--host',
        default=Defaults.Host,
        help='hostname of the AMII Manager (default: %s)' % Defaults.Host
    )

    parser.add_argument(
        '-g',
        '--graph-name',
        default=Defaults.GraphName,
        help='the name of the graph used (default: %s)' % Defaults.GraphName
    )

    addr_group = parser.add_mutually_exclusive_group()

    addr_group.add_argument(
        '-p',
        '--port',
        default=Ports.Profile,
        help='port for profile info (default: %d)' % Ports.Profile
    )

    addr_group.add_argument(
        '-i',
        '--ipc-dir',
        help='directory containing the ipc file descriptor for manager/client (GUI) communication'
    )

    args = parser.parse_args()

    if args.ipc_dir is not None:
        profile_addr = f"ipc://{args.ipc_dir}/profile"
    else:
        profile_addr = f"tcp://{args.host}:{args.port}"

    Profiler("", profile_addr, args.graph_name)


if __name__ == '__main__':
    sys.exit(main())
