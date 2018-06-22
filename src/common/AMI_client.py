#
# AMI_client.py
#
# This module is used by client processes.
#

import numpy
from AMI_common import *

def dataSources():
  # TODO return a list of available data sources with types
  return [ CSPAD( 'cspad0', { 'dimensions' : [ 1024, 1024] } ) ]

def displayResult():
  # TODO return a dict containing the output of the results store
  # lock mutex
  filename = "resultStore.dat"
  print(filename)
  result = pickle.load(open(filename, "rb"))
  # unlock mutex
  return result

def submitGraphToManager(graph):
  graph.serialize()
