import pytest
import dill
import json
import shutil
import subprocess
import numpy as np

from ami.graphkit_wrapper import Graph
from ami.graph_nodes import Map, FilterOn, FilterOff, Binning, PickN


@pytest.fixture(scope='session')
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

    fname = tmpdir_factory.mktemp("complex_graph", False).join("complex_graph.dill")

    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope='session')
def psana_graph(tmpdir_factory):
    graph = Graph(name='graph')
    graph.add(PickN(name='picker', inputs=['xppcspad:raw:raw'], outputs=['picked']))
    fname = tmpdir_factory.mktemp("psana_graph", False).join("psana_graph.dill")
    with open(fname, 'wb') as fd:
        dill.dump(graph, fd)
    return fname


@pytest.fixture(scope='session')
def xtcwriter(tmpdir_factory):
    if shutil.which('xtcwriter') is not None:
        fname = tmpdir_factory.mktemp("xtcs", False).join('data.xtc2')
        p = subprocess.run(['xtcwriter', '-f', fname], stdout=subprocess.PIPE)
        if p.returncode == 0:
            return fname


@pytest.fixture(scope='session')
def workerjson(tmpdir_factory, xtcwriter):

    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "config": {
            "filename": "data.xtc2" if xtcwriter is None else xtcwriter,
            "delta_t": {"dtype": "Scalar", "range": [0, 10], "integer": True},
            "cspad": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
            "laser": {"dtype": "Scalar", "range": [0, 2], "integer": True},
        },
    }

    fname = tmpdir_factory.mktemp("worker_config", False).join('worker.json')
    with open(fname, 'w') as fd:
        json.dump(cfg, fd)
    return fname
