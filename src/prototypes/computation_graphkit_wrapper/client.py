from ami.graphkit_wrapper import Graph, Map, ReduceByKey
from operator import add
import dill


def run_client():
    graph = Graph(name='graph')
    graph.add(Map(name='add', inputs=['a', 'b'], outputs=['c'], func=add))
    graph.add(ReduceByKey(name='localReduce', inputs=['c'], outputs=['d']))
    graph.add(ReduceByKey(name='globalReduce', inputs=['d'], outputs=['e']))

    with open('graph.dat', 'wb') as f:
        dill.dump(graph, f)


if __name__ == '__main__':
    run_client()
