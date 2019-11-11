
"""
Note: pytest-xprocess seems like the `approved` way to start an
external server, but not sure if it is the right thing to do

To use:
1. Inheret from AmiTBase
2. Implement one or more test() functions
"""

import pytest
import time
import numpy as np

from conftest import psanatest


@pytest.mark.parametrize('start_ami', ['static'], indirect=True)
def test_complex_graph(complex_graph_file, start_ami):
    comm_handler = start_ami
    comm_handler.load(complex_graph_file)
    start = time.time()
    while comm_handler.graphVersion != comm_handler.featuresVersion:
        end = time.time()
        if end - start > 10:
            raise TimeoutError

    bins = comm_handler.fetch('BinningOn.Bins')
    counts = comm_handler.fetch('BinningOn.Counts')
    np.testing.assert_equal(bins, np.array([1]))
    np.testing.assert_equal(counts, np.array([10000.0]))


@psanatest
@pytest.mark.parametrize('start_ami', ['psana'], indirect=True)
def test_psana_graph(psana_graph, start_ami):

    comm_handler = start_ami
    comm_handler.load(psana_graph)
    start = time.time()
    while comm_handler.graphVersion != comm_handler.featuresVersion:
        end = time.time()
        if end - start > 1000:
            raise TimeoutError
    picked_cspad = comm_handler.fetch('picked')
    assert picked_cspad.shape == (6, 6)
