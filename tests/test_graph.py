import dill
import numpy as np
from ami.graph_nodes import PickN


def test_filter_on(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 8}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 3}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'_signal_reduce_worker': {8: (10000.0, 1), 3: (10000.0, 1)}}
    assert localCollector == {'_signal_reduce_localCollector': {8: (20000.0, 2), 3: (20000.0, 2)}}
    assert globalCollector == {'signal': {8: 10000.0, 3: 10000.0}}


def test_filter_off(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'_reference_reduce_worker': {4: (10000.0, 1), 5: (10000.0, 1)}}
    assert localCollector == {'_reference_reduce_localCollector': {4: (20000.0, 2), 5: (20000.0, 2)}}
    assert globalCollector == {'reference': {4: 10000.0, 5: 10000.0}}
    complex_graph.reset()


def test_add(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph.add(PickN(name='referenceOne', inputs=['reference'], outputs=['referenceOne']))
    complex_graph.compile(num_workers=4, num_local_collectors=2)

    complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'_reference_reduce_worker': {4: (10000.0, 1), 5: (10000.0, 1)}}
    assert localCollector == {'_reference_reduce_localCollector': {4: (20000.0, 2), 5: (20000.0, 2)}}
    assert globalCollector == {'referenceOne': {4: 10000.0, 5: 10000.0}, 'reference': {4: 10000.0, 5: 10000.0}}


def test_dill(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)

    # dill and then undill the graph
    complex_graph = dill.loads(dill.dumps(complex_graph))

    complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 8}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 3}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'_signal_reduce_worker': {8: (10000.0, 1), 3: (10000.0, 1)}}
    assert localCollector == {'_signal_reduce_localCollector': {8: (20000.0, 2), 3: (20000.0, 2)}}
    assert globalCollector == {'signal': {8: 10000.0, 3: 10000.0}}
