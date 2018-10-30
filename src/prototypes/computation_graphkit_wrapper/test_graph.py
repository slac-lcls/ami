from ami.graphkit_wrapper import Graph, Map, FilterOn, FilterOff, ReduceByKey
import numpy as np


def roi(cspad):
    return cspad[:100, :100]


graph = Graph(name='graph')
graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=sum))

graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
graph.add(ReduceByKey(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'], outputs=['signal']))
graph.add(Map(name='Mean', inputs=['signal'], outputs=['result'], func=sum))

graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
graph.add(ReduceByKey(name='BinningOff', condition_needs=['laseroff'],
                      inputs=['delta_t', 'sum'], outputs=['reference']))

args = {'cspad': np.identity(1024), 'laser': True}

# graph = Graph(name='graph')
# graph.add(Map(name='mul1', inputs=['a', 'b'], outputs=['ab'], func=lambda a, b: a*b))
# graph.add(Map(name='sub1', inputs=['a', 'ab'], outputs=['a_minus_ab'], func=lambda a, b: a-b))
# graph.add(Map(name='abspow1', inputs=['a_minus_ab'], outputs=['abs_a_minus_ab_cubed'], func=lambda a: a**3))
# graph({'a': 2, 'b': 5}, color='worker')


# graph = Graph(name='graph')
# graph.add(Map(name='mul1', inputs=['a', 'b'], outputs=['ab'], func=lambda a, b: a*b))
# graph.add(FilterOn(name='FilterOn', condition_needs=['i'], outputs=['ion']))
# graph.add(Map(name='add', inputs=['ab'], outputs=['c1'], condition_needs=['ion'], func=lambda ab: ab+2))
# graph.add(Map(name='sub2', inputs=['c1'], outputs=['d'], func=lambda c: c - 2))
# graph.add(FilterOff(name='FilterOff', condition_needs=['i'], outputs=['ioff']))
# graph.add(Map(name='sub', inputs=['ab'], outputs=['c2'], condition_needs=['ioff'], func=lambda ab: ab - 2))
# graph.add(Map(name='add2', inputs=['c2'], outputs=['d'], func=lambda c: c + 1))
# graph.add(Map(name='div', inputs=['d'], outputs=['e'], func=lambda d: d/2))
# graph({'a': 1, 'b': 4, 'i': False}, color='worker')
