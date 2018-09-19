#
# AMI_server.py
#

import numpy as np
from AMI_common import *


def workerGraph():
  pickledGraph = Graph('worker')
  graph = pickledGraph.deserialize()
  graph._doReset()
  printGraph(graph)
  return graph

def submitResultToCollector(result):
  filename = "resultStore.dat"
  print('writing to', filename)
  pickle.dump(result, open(filename, "wb"))

