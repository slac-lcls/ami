import pytest
import dill
import shutil
import subprocess
import numpy as np

from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning


@pytest.fixture(scope='module')
def complex_graph(tmpdir_factory):
    graph = Graph(name='graph')

    def roi(cspad):
        return cspad[:100, :100]

    graph.add(Map(name='Roi', inputs=['cspad'], outputs=['roi'], func=roi))
    graph.add(Map(name='Sum', inputs=['roi'], outputs=['sum'], func=np.sum))

    graph.add(FilterOn(name='FilterOn', condition_needs=['laser'], outputs=['laseron']))
    graph.add(Binning(name='BinningOn', condition_needs=['laseron'], inputs=['delta_t', 'sum'],
                      outputs=['signal']))

    graph.add(FilterOff(name='FilterOff', condition_needs=['laser'], outputs=['laseroff']))
    graph.add(Binning(name='BinningOff', condition_needs=['laseroff'],
                      inputs=['delta_t', 'sum'], outputs=['reference']))

    fname = tmpdir_factory.mktemp("graphs", False).join("complex_graph.dill")

    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname

@pytest.fixture(scope='module')
def xtcwriter(tmpdir_factory):
    if shutil.which('xtcwriter') is not None:
        fname = tmpdir_factory.mktemp("xtcs", False).join('data.xtc2')
        p = subprocess.run(['xtcwriter', '-f', fname], stdout=subprocess.PIPE)
        if p.returncode == 0:
            return fname
