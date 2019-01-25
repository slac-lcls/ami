from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning
import numpy as np

graph = Graph(name='graph')
graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=lambda cspad: cspad[:100, :100]))
graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=np.sum))

graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
graph.add(Binning(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'], outputs=['signal']))

graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
graph.add(Binning(name='BinningOff', condition_needs=['laseroff'], inputs=['delta_t', 'sum'], outputs=['reference']))

graph.compile(num_workers=4, num_local_collectors=2)
