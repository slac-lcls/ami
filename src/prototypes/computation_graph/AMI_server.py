#
# AMI_server.py
#

import numpy
from AMI_common import *


def workerGraph():
  pickledGraph = Graph('worker')
  graph = pickledGraph.deserialize()
  printGraph(graph)
  return graph

def ingestTelemetryFrame():
  return { "timestamp" : 0, "field0" : 1, "normalizeField" : 2, "weightField" : 3, "cspad0" : {}, "userObject0" : { 0 }, "userObject2" : { 2 } }

def submitResultToCollector(result):
  filename = "resultStore.dat"
  print('writing to', filename)
  pickle.dump(result, open(filename, "wb"))
