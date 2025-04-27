import dill
import numpy as np
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import PickN, Accumulator, RollingBuffer, SumN, Map


def test_filter_on(complex_graph):
    complex_graph.compile(num_workers=4, num_local_collectors=2)
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


def test_rolling_buffer():
    graph = Graph(name='graph')

    graph.add(RollingBuffer(name='ScatterPlot', inputs=['x', 'y'], outputs=['count', 'scatter'], N=8))
    graph.add(Map(name='ScatterUnzip', inputs=['count', 'scatter'], outputs=['scatter_x', 'scatter_y'],
                  func=lambda c, a: zip(*a)))

    graph.compile(num_workers=4, num_local_collectors=2)

    for node in graph.graph.nodes():
        if type(node) is str:
            continue
        if node.name == 'ScatterPlot_worker':
            assert (node.N == 2)
        elif node.name == 'ScatterPlot_localCollector':
            assert (node.N == 4)
        elif node.name == 'ScatterPlot_globalCollector':
            assert (node.N == 8)

    worker1 = graph({'x': 0, 'y': 1}, color='worker')
    worker1 = graph({'x': 2, 'y': 3}, color='worker')
    assert (worker1 == {'scatter_worker': [(0, 1), (2, 3)], 'count_worker': 2})
    worker1 = graph({'x': 4, 'y': 5}, color='worker')
    assert (worker1 == {'scatter_worker': [(2, 3), (4, 5)], 'count_worker': 3})

    worker1 = {'scatter_worker': [(2, 3), (4, 5)], 'count_worker': 2}
    worker2 = {'scatter_worker': [(3, 2), (5, 4)], 'count_worker': 2}
    worker3 = {'scatter_worker': [(0, 1), (2, 3)], 'count_worker': 2}
    worker4 = {'scatter_worker': [(1, 0), (3, 2)], 'count_worker': 2}

    localCollector1 = graph(worker1, color='localCollector')
    localCollector1 = graph(worker2, color='localCollector')
    assert (localCollector1 == {'scatter_localCollector': [(2, 3), (4, 5), (3, 2), (5, 4)],
                                'count_localCollector': 4})
    localCollector1 = graph(worker3, color='localCollector')
    assert (localCollector1 == {'scatter_localCollector': [(3, 2), (5, 4), (0, 1), (2, 3)],
                                'count_localCollector': 6})
    localCollector1 = graph(worker4, color='localCollector')
    assert (localCollector1 == {'scatter_localCollector': [(0, 1), (2, 3), (1, 0), (3, 2)],
                                'count_localCollector': 8})

    localCollector1 = {'scatter_localCollector': [(0, 1), (2, 3), (4, 5), (6, 7)],
                       'count_localCollector': 8}
    localCollector2 = {'scatter_localCollector': [(8, 9), (10, 11), (12, 13), (14, 15)],
                       'count_localCollector': 8}
    globalCollector = graph(localCollector1, color='globalCollector')
    globalCollector = graph(localCollector2, color='globalCollector')
    assert (globalCollector == {'scatter_x': (0, 2, 4, 6, 8, 10, 12, 14),
                                'scatter_y': (1, 3, 5, 7, 9, 11, 13, 15)})
    localCollector1 = {'scatter_localCollector': [(16, 17), (18, 19), (20, 21), (22, 23)],
                       'count_localCollector': 8}
    globalCollector = graph(localCollector1, color='globalCollector')
    assert (globalCollector == {'scatter_x': (8, 10, 12, 14, 16, 18, 20, 22),
                                'scatter_y': (9, 11, 13, 15, 17, 19, 21, 23)})


def test_global_replace():
    threshold = 4

    def threshold_img(img):
        return np.where(img >= threshold, 1, 0)

    def reduction(res, *rest):
        res += np.sum(rest, axis=0)
        return res

    name = "ThresholdingHitFinder.0"
    inputs = ['cspad']
    outputs = ["ThresholdingHitFinder.0.out"]
    mapped_outputs = [name+'_threshold']
    summed_outputs = [name+"_count", name+"_sum"]

    nodes = [Map(name=name+"_map",
                 inputs=inputs, outputs=mapped_outputs,
                 func=threshold_img, parent=name),
             Accumulator(name=name+"_accumulated",
                         inputs=mapped_outputs, outputs=summed_outputs,
                         reduction=reduction, parent=name),
             Map(name=name+"_unzip",
                 inputs=summed_outputs, outputs=outputs,
                 func=lambda count, s: s, parent=name),
             PickN(name="_auto_"+name+"_view", inputs=outputs, outputs=["_auto_"+name], N=1)]

    graph = Graph(name='graph')

    graph.add(nodes)
    graph.compile()

    img = 10*np.random.randn(4, 4)

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 1,
                'ThresholdingHitFinder.0_sum_worker': threshold_img(img)}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 2,
                'ThresholdingHitFinder.0_sum_worker': 2*threshold_img(img)}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    localCollector = graph(worker, color='localCollector')
    expected = {'ThresholdingHitFinder.0_count_localCollector': 2,
                'ThresholdingHitFinder.0_sum_localCollector': 2*threshold_img(img)}
    for k in localCollector.keys():
        np.testing.assert_equal(localCollector[k], expected[k])

    globalCollector = graph(localCollector, color='globalCollector')
    np.testing.assert_equal(globalCollector['_auto_ThresholdingHitFinder.0'], 2*threshold_img(img))

    graph.heartbeat_finished()

    worker = graph({'cspad': img}, color='worker')
    localCollector = graph(worker, color='localCollector')
    globalCollector = graph(localCollector, color='globalCollector')
    np.testing.assert_equal(globalCollector['_auto_ThresholdingHitFinder.0'], 3*threshold_img(img))

    nodes = [Map(name=name+"_map",
                 inputs=inputs, outputs=mapped_outputs,
                 func=threshold_img, parent=name),
             SumN(name=name+"_accumulated",
                  inputs=mapped_outputs, outputs=summed_outputs,
                  N=2, parent=name),
             Map(name=name+"_unzip",
                 inputs=summed_outputs, outputs=outputs,
                 func=lambda count, s: s, parent=name)]

    graph.add(nodes)
    graph.compile()

    worker = graph({'cspad': img}, color='worker')
    assert (worker == {'ThresholdingHitFinder.0_sum_worker': None,
                       'ThresholdingHitFinder.0_count_worker': None})

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 2,
                'ThresholdingHitFinder.0_sum_worker': 2*threshold_img(img)}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    localCollector = graph(worker, color='localCollector')
    expected = {'ThresholdingHitFinder.0_count_localCollector': 2,
                'ThresholdingHitFinder.0_sum_localCollector': 2*threshold_img(img)}
    for k in localCollector.keys():
        np.testing.assert_equal(localCollector[k], expected[k])

    globalCollector = graph(localCollector, color='globalCollector')
    np.testing.assert_equal(globalCollector['_auto_ThresholdingHitFinder.0'], 2*threshold_img(img))

    graph.reset()

    worker = graph({'cspad': img}, color='worker')
    assert (worker == {'ThresholdingHitFinder.0_sum_worker': None,
                       'ThresholdingHitFinder.0_count_worker': None})

    localCollector = graph(worker, color='localCollector')
    assert (localCollector == {})

    globalCollector = graph(localCollector, color='globalCollector')
    assert (globalCollector == {})

    nodes = [Map(name=name+"_map",
                 inputs=inputs, outputs=mapped_outputs,
                 func=threshold_img, parent=name),
             RollingBuffer(name=name+"_accumulated",
                           inputs=mapped_outputs, outputs=summed_outputs,
                           N=2, parent=name),
             Map(name=name+"_unzip",
                 inputs=summed_outputs, outputs=outputs,
                 func=lambda count, s: sum(s), parent=name)]

    graph.add(nodes)
    graph.compile()

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 1,
                'ThresholdingHitFinder.0_sum_worker': [threshold_img(img)]}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 2,
                'ThresholdingHitFinder.0_sum_worker': [threshold_img(img), threshold_img(img)]}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    localCollector = graph(worker, color='localCollector')
    expected = {'ThresholdingHitFinder.0_count_localCollector': 2,
                'ThresholdingHitFinder.0_sum_localCollector': [threshold_img(img), threshold_img(img)]}
    for k in localCollector.keys():
        np.testing.assert_equal(localCollector[k], expected[k])

    globalCollector = graph(localCollector, color='globalCollector')
    np.testing.assert_equal(globalCollector['_auto_ThresholdingHitFinder.0'], 2*threshold_img(img))

    graph.reset()

    worker = graph({'cspad': img}, color='worker')
    expected = {'ThresholdingHitFinder.0_count_worker': 1,
                'ThresholdingHitFinder.0_sum_worker': [threshold_img(img)]}
    for k in worker.keys():
        np.testing.assert_equal(worker[k], expected[k])

    localCollector = graph(worker, color='localCollector')
    expected = {'ThresholdingHitFinder.0_count_localCollector': 1,
                'ThresholdingHitFinder.0_sum_localCollector': [threshold_img(img)]}
    for k in localCollector.keys():
        np.testing.assert_equal(localCollector[k], expected[k])

    globalCollector = graph(localCollector, color='globalCollector')
    np.testing.assert_equal(globalCollector['_auto_ThresholdingHitFinder.0'], threshold_img(img))
