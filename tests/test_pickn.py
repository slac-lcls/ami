import pytest
from ami.graphkit_wrapper import Graph, Var
from ami.graph_nodes import PickN


@pytest.fixture(scope='function')
def pickN_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='cspad_pickN', N=9,
                    inputs=[Var(name='cspad', type=int)],
                    outputs=[Var(name='ncspads', type=(list, type(None)))]))
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


@pytest.fixture(scope='function')
def pickMultiple_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='cspad', N=9,
                    inputs=[Var(name='cspad', type=int), Var(name='delta_t', type=int)],
                    outputs=[Var(name='ncspads', type=(type(None), list))]))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickMultiple(pickMultiple_graph):
    pickMultiple_graph({'cspad': 1, 'delta_t': 10}, color='worker')
    worker1 = pickMultiple_graph({'cspad': 2, 'delta_t': 20}, color='worker')
    pickMultiple_graph({'cspad': 3, 'delta_t': 30}, color='worker')
    worker2 = pickMultiple_graph({'cspad': 4, 'delta_t': 40}, color='worker')

    pickMultiple_graph(worker1, color='localCollector')
    localCollector1 = pickMultiple_graph(worker2, color='localCollector')

    pickMultiple_graph(localCollector1, color='globalCollector')
    globalCollector = pickMultiple_graph(localCollector1, color='globalCollector')

    assert worker1 == {'ncspads_worker': [(1, 10), (2, 20)]}
    assert worker2 == {'ncspads_worker': [(3, 30), (4, 40)]}

    assert localCollector1 == {'ncspads_localCollector': [(1, 10), (2, 20), (3, 30), (4, 40)]}
    assert globalCollector == {'ncspads': [(1, 10), (2, 20), (3, 30), (4, 40), (1, 10), (2, 20), (3, 30), (4, 40)]}
