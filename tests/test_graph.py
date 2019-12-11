import dill
import numpy as np
from ami.graph_nodes import PickN


def test_filter_on(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph.plot('test.png')
    complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 8}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 3}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'BinningOn_reduce_count_worker': {8: (10000.0, 1), 3: (10000.0, 1)}}
    assert localCollector == {'BinningOn_reduce_count_localCollector': {8: (20000.0, 2), 3: (20000.0, 2)}}
    np.testing.assert_equal(globalCollector['BinningOn.Bins'], np.array([3, 8]))
    np.testing.assert_equal(globalCollector['BinningOn.Counts'], np.array([10000., 10000.]))


def test_filter_off(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'BinningOff_reduce_count_worker': {4: (10000.0, 1), 5: (10000.0, 1)}}
    assert localCollector == {'BinningOff_reduce_count_localCollector': {4: (20000.0, 2), 5: (20000.0, 2)}}
    np.testing.assert_equal(globalCollector['BinningOff.Bins'], np.array([4, 5]))
    np.testing.assert_equal(globalCollector['BinningOff.Counts'], np.array([10000., 10000.]))


def test_add(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
    complex_graph.add(PickN(name='pickReferenceOne',
                            inputs=['BinningOff.Bins', 'BinningOff.Counts'],
                            outputs=['referenceOne']))
    complex_graph.compile(num_workers=4, num_local_collectors=2)

    complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'BinningOff_reduce_count_worker': {4: (10000.0, 1), 5: (10000.0, 1)}}
    assert localCollector == {'BinningOff_reduce_count_localCollector': {4: (20000.0, 2), 5: (20000.0, 2)}}
    np.testing.assert_equal(globalCollector['referenceOne'][0], np.array([4, 5]))
    np.testing.assert_equal(globalCollector['referenceOne'][1], np.array([10000., 10000.]))


def test_dill(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)

    # dill and then undill the graph
    complex_graph = dill.loads(dill.dumps(complex_graph))

    complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 8}, color='worker')
    worker = complex_graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 3}, color='worker')
    complex_graph(worker, color='localCollector')
    localCollector = complex_graph(worker, color='localCollector')
    globalCollector = complex_graph(localCollector, color='globalCollector')

    assert worker == {'BinningOn_reduce_count_worker': {3: (10000.0, 1), 8: (10000.0, 1)}}
    assert localCollector == {'BinningOn_reduce_count_localCollector': {3: (20000.0, 2), 8: (20000.0, 2)}}
    np.testing.assert_equal(globalCollector['BinningOn.Bins'], np.array([3, 8]))
    np.testing.assert_equal(globalCollector['BinningOn.Counts'], np.array([10000., 10000.]))
