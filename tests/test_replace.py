from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning
import numpy as np


class TestGraph:
    def setup(self):
        self.graph = Graph(name='graph')

        def roi(cspad):
            return cspad[:100, :100]

        self.graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
        self.graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=np.sum))

        self.graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
        self.graph.add(Binning(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'],
                               outputs=['signal']))

        self.graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
        self.graph.add(Binning(name='BinningOff', condition_needs=['laseroff'],
                               inputs=['delta_t', 'sum'], outputs=['reference']))
        self.graph.compile(num_workers=4, num_local_collectors=2)

    def test_replace(self):
        def roi(cspad):
            return cspad[:10, :10]

        self.graph.replace(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
        self.graph.compile(num_workers=4, num_local_collectors=2)
        self.graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
        worker = self.graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
        self.graph(worker, color='localCollector')
        localCollector = self.graph(worker, color='localCollector')
        globalCollector = self.graph(localCollector, color='globalCollector')

        assert worker == {'reference_reduce_worker': {4: (100.0, 1), 5: (100.0, 1)}}
        assert localCollector == {'reference_reduce_localCollector': {4: (200.0, 2), 5: (200.0, 2)}}
        assert globalCollector == {'reference': {4: 100.0, 5: 100.0}}
