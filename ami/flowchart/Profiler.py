import collections
import logging
import asyncio
import zmq
import zmq.asyncio
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtGui, QtCore
from ami import LogConfig
from ami.data import Deserializer
from ami.asyncqt import QEventLoop

logger = logging.getLogger(LogConfig.get_package_name(__name__))


class HeartbeatData(object):

    def __init__(self, heartbeat, metadata, parents, graph):
        self.heartbeat = heartbeat
        self.metadata = metadata
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

        for event in data[self.graph]:
            time_per_event = np.sum(list(event.values()))
            time_per_heartbeat += time_per_event
            for node, time in event.items():
                parent = self.metadata[node]['parent']
                node_time_per_heartbeat[parent] += time

        for node, time in node_time_per_heartbeat.items():
            self.worker_average[node].append(time)

        self.worker_time_per_heartbeat[worker] = node_time_per_heartbeat

    def add_local_collector_data(self, localCollector, data):
        node_time_per_heartbeat = collections.defaultdict(lambda: 0)

        for node, time in data[self.graph].items():
            parent = self.metadata[node]['parent']
            node_time_per_heartbeat[parent] += time

        for node, time in node_time_per_heartbeat.items():
            self.local_collector_average[node].append(time)

        self.local_collector_time_per_heartbeat[localCollector] = node_time_per_heartbeat

    def add_global_collector_data(self, data):
        for node, time in data[self.graph].items():
            parent = self.metadata[node]['parent']
            self.total_time_per_heartbeat[parent] += time

        for node, times in self.worker_average.items():
            self.total_time_per_heartbeat[node] += np.average(times)

        for node, times in self.local_collector_average.items():
            self.total_time_per_heartbeat[node] += np.average(times)


class Profiler(QtCore.QObject):

    def __init__(self, broker_addr="", profiler_addr="", loop=None):
        super().__init__()

        if loop is None:
            self.app = QtGui.QApplication([])
            loop = QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        self.ctx = zmq.asyncio.Context()

        if broker_addr:
            self.broker = self.ctx.socket(zmq.SUB)
            self.broker.connect(broker_addr)
        else:
            self.broker = None

        self.profile = self.ctx.socket(zmq.SUB)
        self.profile.setsockopt_string(zmq.SUBSCRIBE, '')
        self.profile.connect(profiler_addr)

        self.deserializer = Deserializer()
        self.metadata = None
        self.parents = set()

        self.heartbeat_data = {}
        self.graphicsLayoutWidget = pg.GraphicsLayoutWidget()
        self.plot_view = self.graphicsLayoutWidget.addPlot()
        self.plot = {}
        self.trace_data = collections.defaultdict(lambda: np.array([np.nan]*100))

        self.win = QtGui.QMainWindow()
        self.win.setWindowTitle('Profiler')
        self.win.setCentralWidget(self.graphicsLayoutWidget)
        self.win.show()

        with loop:
            loop.run_until_complete(asyncio.gather(self.process_broker_message(),
                                                   self.process_profile_data()))

    async def process_broker_message(self):
        if self.broker is None:
            return

        while True:
            await self.broker.recv_string()
            msg = await self.broker.recv_pyobj()

            if msg.command == "show":
                self.win.show()
            elif msg.command == "close":
                return

    async def process_profile_data(self):
        while True:
            topic = await self.profile.recv_string()
            name = await self.profile.recv_string()
            data = await self.profile.recv_serialized(self.deserializer, copy=False)

            if topic == "profile":
                if self.metadata is None:
                    continue

                heartbeat = data['heartbeat']

                if heartbeat not in self.heartbeat_data:
                    self.heartbeat_data[heartbeat] = HeartbeatData(data['heartbeat'],
                                                                   self.metadata,
                                                                   self.parents,
                                                                   'graph')
                heartbeat_data = self.heartbeat_data[heartbeat]

                if name.startswith('worker'):
                    heartbeat_data.add_worker_data(name, data)
                elif name.startswith('localCollector'):
                    heartbeat_data.add_local_collector_data(name, data)
                elif name.startswith('globalCollector'):
                    heartbeat_data.add_global_collector_data(data)

                    for node, time in heartbeat_data.total_time_per_heartbeat.items():
                        self.trace_data[node][heartbeat % 100] = time

                    for node, times in self.trace_data.items():
                        if node not in self.plot:
                            self.plot[node] = self.plot_view.plot(y=times, name=node)
                        else:
                            self.plot[node].setData(y=times)

                    del self.heartbeat_data[heartbeat]

            elif topic == "metadata":
                logger.info("Received metadata")
                self.metadata = data
                self.trace_data = collections.defaultdict(lambda: np.array([np.nan]*100))
                self.heartbeat_data = {}
                self.plot = {}
                self.parents = set()
                for k, v in data.items():
                    self.parents.add(v['parent'])

    async def run(self):
        await asyncio.gather(self.process_broker_message(),
                             self.process_profile_data())
