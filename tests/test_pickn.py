from ami.graphkit_wrapper import Graph, PickN


class TestPickN:

    def setup(self):
        self.graph = Graph(name='graph')
        self.graph.add(PickN(name='cspad', N=9, inputs=['cspad'], outputs=['ncspads']))

        self.graph.compile(num_workers=4, num_local_collectors=2)

    def teardown(self):
        pass

    def test_pickn(self):
        self.graph({'cspad': 1}, color='worker')
        worker1 = self.graph({'cspad': 2}, color='worker')
        self.graph({'cspad': 3}, color='worker')
        worker2 = self.graph({'cspad': 4}, color='worker')

        self.graph(worker1, color='localCollector')
        localCollector1 = self.graph(worker2, color='localCollector')

        self.graph(localCollector1, color='globalCollector')
        globalCollector = self.graph(localCollector1, color='globalCollector')

        assert worker1 == {'ncspads_worker': [1, 2]}
        assert worker2 == {'ncspads_worker': [3, 4]}

        assert localCollector1 == {'ncspads_localCollector': [1, 2, 3, 4]}
        assert globalCollector == {'ncspads': [1, 2, 3, 4, 1, 2, 3, 4]}
