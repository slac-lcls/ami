#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI
import userDefined

def simpleWorkerGraph():
  graph = AMI.Graph('simple_worker_graph')
  image = AMI.CSPAD('cspad0', dimensions = [ 1024, 1024 ]) # name of XTC field
  shape = image._shape()
  roi = [ shape[0] * .1, shape[1] * .1, shape[0] * .9, shape[1]* .9 ]
  image._setROI(roi)._setSum() # set an inset ROI with a sum
  graph.export(image)
  graph.export(AMI.Point('timestamp')) # export XTC field to the Result store
  return graph



def workerGraph():
  graph = AMI.Graph('workerGraph_Env_one_scalar') # create an empty graph
  
  # Env data source, plot mean v time, normalize by, weight by
  dataPoint = AMI.Point('field0') # 'field0' matches an XTC field name
  dataPoint._setMean() # compute the mean of this field
  graph.export(dataPoint) # export to the Result store
  graph.export(AMI.Point('normalizeField')) # export XTC field to the Result store
  graph.export(AMI.Point('weightField')) # export XTC field to the Result store
  graph.export(AMI.Point('timestamp')) # export XTC field to the Result store
  
  # 1D array with recirculated datum
  graph.iff('field0 > 0', dataPoint)
  sourceVector = AMI.Vector('intensityVector', dimensions = [ 10 ]) # 'intensityVector' is an XTC field
  userObject = userDefined.object('userObject0', sourceVector) # a custom user object
  graph.export(userObject) # export to the Result store, must support computation and reduction
  userObject0 = graph.import_('userObject0')
  meanIntensity = userObject0._get('meanIntensity')
  userObject2 = userDefined.object2('userObject2', sourceVector, dataPoint, meanIntensity)
  graph.export(userObject2) # export to the Result store
  
  # 2D cspad with ROI computation
  graph.iff('meanIntensity > 1', meanIntensity)
  image = AMI.CSPAD('cspad0', dimensions = [ 1024, 1024 ] ) # 'cspad0' is an XTC field, 2D image
  shape = image._shape() # get dimensions
  roi = [ shape[0] * .1, shape[1] * .1, shape[0] * .9, shape[1]* .9 ]
  image._setROI(roi) # set an inset ROI
  image._setMean() # compute the mean in the ROI
  graph.export(image) # export to Result store
  
  graph.endif()
  graph.endif()
  
  return graph



graph = workerGraph()
#graph = simpleWorkerGraph()
AMI.submitGraphToManager(graph) # pickle the graph and send to GraphManager


