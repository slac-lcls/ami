from ami.graphkit_wrapper import Graph, Map, FilterOn, FilterOff, ReduceByKey
import numpy as np


def roi(cspad):
    return cspad[:100, :100]


graph = Graph(name='graph')
graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=np.sum))

graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
graph.add(ReduceByKey(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'], outputs=['signal']))

graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
graph.add(ReduceByKey(name='BinningOff', condition_needs=['laseroff'],
                      inputs=['delta_t', 'sum'], outputs=['reference']))

graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
worker = graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
print("Worker: ", worker)
graph(worker, color='localCollector')
localCollector = graph(worker, color='localCollector')
print("LocalCollector: ", localCollector)
globalCollector = graph(localCollector, color='globalCollector')
print("GlobalCollector: ", globalCollector)
