import pytest
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import PickN


@pytest.fixture(scope='function')
def pickN_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='cspad', N=9, inputs=['cspad'], outputs=['ncspads']))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickn(pickN_graph):
    pickN_graph({'cspad': 1}, color='worker')
    worker1 = pickN_graph({'cspad': 2}, color='worker')
    pickN_graph({'cspad': 3}, color='worker')
    worker2 = pickN_graph({'cspad': 4}, color='worker')

    pickN_graph(worker1, color='localCollector')
    localCollector1 = pickN_graph(worker2, color='localCollector')

    pickN_graph(localCollector1, color='globalCollector')
    globalCollector = pickN_graph(localCollector1, color='globalCollector')

    assert worker1 == {'ncspads_worker': [1, 2]}
    assert worker2 == {'ncspads_worker': [3, 4]}

    assert localCollector1 == {'ncspads_localCollector': [1, 2, 3, 4]}
    assert globalCollector == {'ncspads': [1, 2, 3, 4, 1, 2, 3, 4]}
