from ami.graphkit_wrapper2 import Graph, Map, Filter, FilterOn, FilterOff, ReduceByKey
import networkx as nx
import itertools as it


def roi(cspad):
    return cspad[:100, :100]


graph = Graph(name='graph')
graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=sum))
graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
graph.add(ReduceByKey(name='Binning On', condition_needs=['laseron'], inputs=['delta_t', 'sum'], outputs=['signal']))
graph.add(Map(name='Mean', inputs=['signal'], outputs=['result'], func=sum))

graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
graph.add(ReduceByKey(name='Binning Off', condition_needs=['laseroff'],
                      inputs=['delta_t', 'sum'], outputs=['reference']))

g = graph.graph
inputs = [n for n, d in g.in_degree() if d == 0]
outputs = [n for n, d in g.out_degree() if d == 0]

global_operation = set()
filters = set()

sources_targets = list(it.product(inputs, outputs))
for s, t in sources_targets:
    nodes = list(nx.algorithms.all_simple_paths(g, s, t))[0]

    reductions = filter(lambda node: isinstance(node, ReduceByKey), nodes)

    for reduction in reductions:
        before = list(filter(lambda node: isinstance(node, ReduceByKey), nx.algorithms.dag.ancestors(g, reduction)))
        if before == []:
            global_operation.add(reduction)

    color = 'worker'
    for node in nodes:
        if type(node) is str:
            continue

        gnode = g.nodes[node]
        if 'color' not in gnode:
            gnode['color'] = set()

        if node not in global_operation:
            gnode['color'].add(color)
        elif node in global_operation:
            gnode['color'].add(color)
            color = 'collector'
            gnode['color'].add(color)

    filter_node = filter(lambda node: isinstance(node, Filter), nodes)
    filters = filters.union(set(filter_node))
