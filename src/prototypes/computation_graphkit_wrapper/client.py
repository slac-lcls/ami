from ami.graphkit_wrapper import Graph, Map, FilterOn, FilterOff, Binning
import numpy as np
import dill


def run_client():
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

    with open('graph.dat', 'wb') as f:
        dill.dump(graph, f)


if __name__ == '__main__':
    run_client()
