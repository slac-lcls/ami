#
# AMI_server.py
#

import numpy
from AMI_common import *

def workerGraph():
  graph = Graph('worker')
  return graph.deserialize()

def ingestTelemetryFrame():
  return { "timestamp" : 0, "field0" : 1, "normalizeField" : 2, "weightField" : 3 }

def submitResultToCollector(result):
  filename = "resultStore.dat"
  print(filename)
  print result
  pickle.dump(result, open(filename, "wb"))

