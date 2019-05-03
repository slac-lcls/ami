import numpy as np
from ami.graph_nodes import Map


def test_replace(complex_graph):
    def roi(cspad):
        return cspad[:10, :10]

    complex_graph.replace(Map(name='Roi',
                              inputs=['cspad'],
                              outputs=['roi'],
                              func=roi))
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'reference_reduce_worker': {4: (100.0, 1), 5: (100.0, 1)}}
    assert localCollector == {'reference_reduce_localCollector': {4: (200.0, 2), 5: (200.0, 2)}}
    assert globalCollector == {'reference': {4: 100.0, 5: 100.0}}
