#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI

def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar')
  dataPoint = AMI.Point('field0')
  dataPoint.setMean()
  graph.add(dataPoint)
  graph.add(AMI.Point('normalizeField'))
  graph.add(AMI.Point('weightField'))
  graph.add(AMI.Point('timestamp'))
  return graph

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

