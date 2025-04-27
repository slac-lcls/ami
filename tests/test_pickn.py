import pytest
import numpy as np
from ami.graphkit_wrapper import Graph
from ami.graph_nodes import PickN, SumN, RollingBuffer


@pytest.fixture(scope='function')
def pickN_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='cspad_pickN', N=9,
                    inputs=['cspad'],
                    outputs=['ncspads']))
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
    graph.add(PickN(name='cspad_pickN', N=9,
                    inputs=['cspad', 'delta_t'],
                    outputs=['ncspads']))
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


@pytest.fixture(scope='function')
def pickList_graph():
    graph = Graph(name='graph')
    graph.add(PickN(name='cspad_pickN', N=9,
                    inputs=['cspad'],
                    outputs=['ncspads']))
    graph.compile(num_workers=4, num_local_collectors=2)
    return graph


def test_pickList(pickList_graph):
    pickList_graph({'cspad': [1, 2]}, color='worker')
    worker1 = pickList_graph({'cspad': [3, 4]}, color='worker')
    pickList_graph({'cspad': [-1, -2]}, color='worker')
    worker2 = pickList_graph({'cspad': [-3, -4]}, color='worker')

    pickList_graph(worker1, color='localCollector')
    localCollector1 = pickList_graph(worker2, color='localCollector')

    pickList_graph(localCollector1, color='globalCollector')
    globalCollector = pickList_graph(localCollector1, color='globalCollector')

    assert worker1 == {'ncspads_worker': [[1, 2], [3, 4]]}
    assert worker2 == {'ncspads_worker': [[-1, -2], [-3, -4]]}

    assert localCollector1 == {'ncspads_localCollector': [[1, 2], [3, 4], [-1, -2], [-3, -4]]}
    assert globalCollector == {'ncspads': [[1, 2], [3, 4], [-1, -2], [-3, -4], [1, 2], [3, 4], [-1, -2], [-3, -4]]}


@pytest.fixture(scope='function')
def sumN_graph(request):
    N, nworkers, ncollectors, expected = request.param

    graph = Graph(name='graph')
    graph.add(SumN(name='cspad_sumN', N=N,
                   inputs=['cspad'],
                   outputs=['cspad_counts', 'cspad_sum']))
    graph.compile(num_workers=nworkers, num_local_collectors=ncollectors)
    return graph, expected


@pytest.mark.parametrize('sumN_graph',
                         [
                            (9, 4, 2, (2, (2, 3), (2, 7))),
                            (8, 4, 2, (2, (2, 3), (2, 7))),
                            (4, 4, 2, (1, (1, 1), (1, 2))),
                            (12, 4, 2, (2, (None, None), (None, None))),
                            (12, 4, 2, (3, (3, 6), (3, 15))),
                            (4, 4, 2, (2, (1, 2), (1, 4))),
                            (1, 4, 2, (2, (1, 2), (1, 4), (1, 4), (1, 4))),
                            (4, 1, 1, (4, (4, 10), (4, 26), (4, 26), (4, 26))),
                            (4, 1, 1, (2, (None, None), (None, None))),
                         ],
                         indirect=True)
def test_sumN(sumN_graph):
    sumN_graph, expected = sumN_graph
    try:
        steps, (count1, sum1), (count2, sum2) = expected
        if count1 is not None and count2 is not None:
            count3 = count1 + count2
        else:
            count3 = None
        if sum1 is not None and sum2 is not None:
            sum3 = sum1 + sum2
        else:
            sum3 = None
        if count3 is not None:
            count4 = count3 * 2
        else:
            count4 = None
        if sum3 is not None:
            sum4 = sum3 * 2
        else:
            sum4 = None
    except ValueError:
        steps, (count1, sum1), (count2, sum2), (count3, sum3), (count4, sum4) = expected

    start = 1
    stop = start + steps
    for i in range(start, stop):
        worker1 = sumN_graph({'cspad': i}, color='worker')
    sumN_graph.reset()
    start = stop
    stop = start + steps
    for i in range(start, stop):
        worker2 = sumN_graph({'cspad': i}, color='worker')

    sumN_graph(worker1, color='localCollector')
    localCollector = sumN_graph(worker2, color='localCollector')

    sumN_graph(localCollector, color='globalCollector')
    globalCollector = sumN_graph(localCollector, color='globalCollector')

    if count1 is not None and sum1 is not None:
        assert worker1 == {'cspad_counts_worker': count1, 'cspad_sum_worker': sum1}
    else:
        assert not worker1

    if count2 is not None and sum2 is not None:
        assert worker2 == {'cspad_counts_worker': count2, 'cspad_sum_worker': sum2}
    else:
        assert not worker2

    if count3 is not None and sum3 is not None:
        assert localCollector == {'cspad_counts_localCollector': count3, 'cspad_sum_localCollector': sum3}
    else:
        assert not localCollector

    if count4 is not None and sum4 is not None:
        assert globalCollector == {'cspad_counts': count4, 'cspad_sum': sum4}
    else:
        assert not globalCollector


@pytest.fixture(scope='function')
def rollingBuffer_graph(request):
    N, nworkers, ncollectors, expected = request.param

    graph = Graph(name='graph')
    graph.add(RollingBuffer(name='cspad_rollingBuffer', N=N,
                            inputs=['cspad'],
                            outputs=['count', 'ncspads']))
    graph.compile(num_workers=nworkers, num_local_collectors=ncollectors)
    return graph, expected


@pytest.mark.parametrize('rollingBuffer_graph',
                         [
                            (9, 4, 2, (2, [1, 2], [3, 4])),
                            (8, 4, 2, (2, [1, 2], [3, 4])),
                            (4, 4, 2, (1, [1], [2])),
                            (12, 4, 2, (2, [1, 2], [3, 4])),
                            (12, 4, 2, (3, [1, 2, 3], [4, 5, 6])),
                            (4, 4, 2, (2, [2], [4])),
                            (1, 4, 2, (2, [2], [4], [4], [4])),
                            (4, 1, 1, (4, [1, 2, 3, 4], [5, 6, 7, 8], [5, 6, 7, 8], [5, 6, 7, 8])),
                            (4, 1, 1, (2, [1, 2], [3, 4], [1, 2, 3, 4], [1, 2, 3, 4])),
                         ],
                         indirect=True)
def test_rollingBuffer(rollingBuffer_graph):
    rollingBuffer_graph, expected = rollingBuffer_graph
    try:
        steps, expected1, expected2 = expected
        expected3 = expected1 + expected2
        expected4 = expected3 * 2
    except ValueError:
        steps, expected1, expected2, expected3, expected4 = expected

    start = 1
    stop = start + steps
    for i in range(start, stop):
        worker1 = rollingBuffer_graph({'cspad': i}, color='worker')
    rollingBuffer_graph.reset()
    start = stop
    stop = start + steps
    for i in range(start, stop):
        worker2 = rollingBuffer_graph({'cspad': i}, color='worker')

    rollingBuffer_graph(worker1, color='localCollector')
    localCollector = rollingBuffer_graph(worker2, color='localCollector')

    rollingBuffer_graph(localCollector, color='globalCollector')
    globalCollector = rollingBuffer_graph(localCollector, color='globalCollector')

    assert worker1 == {'count_worker': steps, 'ncspads_worker': expected1}
    assert worker2 == {'count_worker': steps, 'ncspads_worker': expected2}

    assert localCollector == {'count_localCollector': 2*steps, 'ncspads_localCollector': expected3}
    assert globalCollector == {'count': 4*steps, 'ncspads': expected4}
