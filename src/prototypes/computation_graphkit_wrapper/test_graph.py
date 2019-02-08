from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, PickN, Binning
import numpy as np


def roi(cspad):
    return cspad[:100, :100]


graph = Graph(name='graph')
graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=np.sum))

graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
graph.add(Binning(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'], outputs=['signal']))

graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
graph.add(Binning(name='BinningOff', condition_needs=['laseroff'],
                  inputs=['delta_t', 'sum'], outputs=['reference']))
graph.add(PickN(name='roi_view', inputs=['roi'], outputs=['roi_pickone']))
graph.compile(num_workers=4, num_local_collectors=2)

graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 4}, color='worker')
worker = graph({'cspad': np.ones((200, 200)), 'laser': False, 'delta_t': 5}, color='worker')
print("Worker: ", worker)
graph(worker, color='localCollector')
localCollector = graph(worker, color='localCollector')
print("LocalCollector: ", localCollector)
globalCollector = graph(localCollector, color='globalCollector')
print("GlobalCollector: ", globalCollector)
print()
# graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 4}, color='worker')
# worker = graph({'cspad': np.ones((200, 200)), 'laser': True, 'delta_t': 5}, color='worker')
# print("Worker: ", worker)
# graph(worker, color='localCollector')
# localCollector = graph(worker, color='localCollector')
# print("LocalCollector: ", localCollector)
# globalCollector = graph(localCollector, color='globalCollector')
# print("GlobalCollector: ", globalCollector)


# print()
# graph = Graph(name='graph')
# graph.add(PickN(name='cspad', N=9, inputs=['cspad'], outputs=['ncspads']))

# graph.compile(num_workers=4, num_local_collectors=2)
# worker1 = graph({'cspad': 1}, color='worker')
# print("Worker1:", worker1)
# worker2 = graph({'cspad': 2}, color='worker')
# print("Worker2:", worker2)
# worker3 = graph({'cspad': 3}, color='worker')
# print("Worker3:", worker3)
# worker4 = graph({'cspad': 4}, color='worker')
# print("Worker4:", worker4)

# localCollector1 = graph(worker2, color='localCollector')
# print("LocalCollector1:", localCollector1)
# localCollector2 = graph(worker4, color='localCollector')
# print("LocalCollector2:", localCollector2)

# globalCollector = graph(localCollector1, color='globalCollector')
# globalCollector = graph(localCollector2, color='globalCollector')
# globalCollector = graph(localCollector2, color='globalCollector')
# print("GlobalCollector:", globalCollector)
