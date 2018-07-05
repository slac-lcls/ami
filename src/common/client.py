#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI
import useDefined

def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar') # create an empty graph
  
  # Env data source, plot mean v time, normalize by, weight by
  dataPoint = AMI.Point('field0') # 'field0' matches an XTC field name
  dataPoint.setMean() # compute the mean of this field
  graph.export(dataPoint) # export to the Result store
  graph.export(AMI.Point('normalizeField')) # export XTC field to the Result store
  graph.export(AMI.Point('weightField')) # export XTC field to the Result store
  graph.export(AMI.Point('timestamp')) # export XTC field to the Result store
  
  # 1D array with recirculated datum
  sourceVector = AMI.vector('intensityVector') # 'intensityVector' is an XTC field
  userObject = userDefined.object('userObject0', sourceVector) # a custom user object
  graph.export(userObject) # export to the Result store, must support computation and reduction
  meanIntensity = AMI.Result('userObject0').meanIntensity # obtain from the result store
  userObject2 = userDefine.object2('userObject2', sourceVector, dataPoint, meanIntensity)
  graph.export(userObject2) # export to the Result store
  
  # 2D cspad with ROI computation
  image = AMI.cspad('cspad0') # 'cspad0' is an XTC field, 2D image
  shape = image.shape() # get dimensions
  roi = [ shape[2] * .1, shape[3] * .1, shape[2] * .9, shape[3] * .9 ]
  image.setROI(roi) # set an inset ROI
  image.setMean() # compute the mean in the ROI
  graph.export(image) # export to Result store
  
  return graph


def normalizedWeighted(x, normalize, weight):
  return x / normalize * weight


graph = workerGraph()
AMI.submitGraphToManager(graph) # pickle the graph and send to GraphManager

while(True):
  data = AMI.displayResult() # get the current frame of subscribed data
  x = data['timestamp']
  y = normalizedWeighted(data['field0'].mean.0, data['normalizeField'], data['weightField'])
  print x, y
  userObject = data['userObject0']
  userObject2 = data['userObject2']
  print userObject.fieldA, userObject2.fieldB
  image = data['cspad0']
  print image.mean.0

