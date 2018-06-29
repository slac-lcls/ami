#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI
import useDefined

def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar')
  dataPoint = AMI.Point('field0')
  dataPoint.setMean()
  graph.export(dataPoint)
  graph.export(AMI.Point('normalizeField'))
  graph.export(AMI.Point('weightField'))
  graph.export(AMI.Point('timestamp'))
  # 1D array
  sourceVector = AMI.vector('intensityVector')
  userObject = userDefined.object('userObject0', sourceVector)
  graph.export(userObject) # userObject must support computation and reduction
  userObject2 = userDefine.object2('userObject2', sourceVector, dataPoint)
  graph.export(userObject2)
  return graph

## constructor arguments:
## for a primitive type that corresponds to an xtc data element, pass in the label for the variable eg 'field0'
## for a user defined type that takes in other data objects, pass the data objects into the constructor
## questions: what kinds of errors can be detected by the graph manager versus the worker or reducer?
## how do we handle a graph failure at a worker or reducer?


def normalizedWeighted(x, normalize, weight):
  return x / normalize * weight


graph = workerGraph()
AMI.submitGraphToManager(graph)

while(True):
  data = AMI.displayResult()
  print data
  x = data['timestamp']
  y = normalizedWeighted(data['field0.mean.0'], data['normalizeField'], data['weightField'])
  print x, y

