#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI
import userDefined

def simpleWorkerGraph():
  graph = AMI.Graph('simple_worker_graph')
  image = AMI.DataElement('cspad0', origin=[0,0], shape=[1024,1024])
  roi = [ (int(image.shape[0] * .1)), (int(image.shape[0] * .9)), (int(image.shape[1] * .1)), (int(image.shape[1]* .9)) ]
  subimage = image._map('roi', roi)
  graph.export(subimage._map('sum', ))
#  graph.export(image._map('roi', roi)._map('mean'))
  graph.export(AMI.DataElement('timestamp')) # export XTC field to the Result store
  return graph


def complexWorkerGraph():
  graph = AMI.Graph("first_milestone")
  image = AMI.DataElement('cspad0', origin=[0,0], shape=[1024,1024])
  calibratedImage = image._map('calibrate')
  peaks = calibratedImage._map('peakfind')
  laser = AMI.DataElement('laser')
  graph._If('$1', laser)
  # bin laser-on by x,y,t
  # bin laser-off by x,y
  # take sidebands and interpolate to subtract in signal region (both laser on/off)
  # project laser on/off along y (now have x,t)
  # subtract laser-off from laser-on cube in each time bin
  graph._Endif()
  return graph


graph = simpleWorkerGraph()
AMI.printGraph(graph)
AMI.submitGraphToManager(graph) # pickle the graph and send to GraphManager

