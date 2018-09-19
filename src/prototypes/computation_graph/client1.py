#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import numpy
import AMI_client as AMI
import userDefined

def simpleWorkerGraph():
  graph = AMI.Graph('simple_worker_graph')
  image = AMI.DataElement('xppcspad')
  image._dataIs(numpy.ones((1024, 1024)))
  roiLambda = lambda image: [ (int(image.operand.shape[0] * .1)), (int(image.operand.shape[0] * .9)), (int(image.operand.shape[1] * .1)), (int(image.operand.shape[1]* .9)) ]
  subimage = image._worker('roi', roiLambda)
  meanSubimage = subimage._worker('mean')
  graph.addNode(meanSubimage)
  graph.If('1 < 2')
  graph.addNode(meanSubimage._localCollector('mean')._globalCollector('mean'))
  image2 = AMI.DataElement('xppcspad')
  image2._dataIs(numpy.ones((512, 512)))
  graph.addNode(image2._worker('mean')._localCollector('mean')._globalCollector('mean'))
  graph.Endif()
  graph.addNode(AMI.DataElement('timestamp'))
  return graph

def complexWorkerGraph():
  graph = AMI.Graph("first_milestone")
  image = AMI.DataElement('xppcspad')
  calibratedImage = image._worker('calibrate')
  peaks = calibratedImage._worker('peakfind')
  laser = AMI.DataElement('laser')
  graph.If(lambda: laser)
  # bin laser-on by x,y,t
  # bin laser-off by x,y
  # take sidebands and interpolate to subtract in signal region (both laser on/off)
  # project laser on/off along y (now have x,t)
  # subtract laser-off from laser-on cube in each time bin
  graph.Endif()
  return graph


graph = simpleWorkerGraph()
AMI.printGraph(graph)
AMI.submitGraphToManager(graph) # pickle the graph and send to GraphManager

