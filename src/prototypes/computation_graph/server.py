#
# server
#

import AMI_server as AMI


print('read work graph')
graph = AMI.workerGraph()
print('reset work graph')
graph._doReset()

nextSampleTime = 0
samplingInterval = 100


if True:
  print('map worker graph')
  result = graph._doMap()
  print( 'execution result=', result)
  timestamp = 0
  if timestamp >= nextSampleTime:
    print('reduce worker graph')
    graph._doReduce()
    nextSampleTime = timestamp + samplingInterval

