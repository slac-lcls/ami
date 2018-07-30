#
# server
#

import AMI_server as AMI


graph = AMI.workerGraph()
for node in graph._nodes:
  node._initializeMap()


nextSampleTime = 0
samplingInterval = 100


if True:
  telemetryFrame = AMI.ingestTelemetryFrame()
  print('execute telemetry frame', telemetryFrame)
  result = {}
  for node in graph._nodes:
    print node._name
    returnValue = node._map(telemetryFrame)
    if returnValue is not None:
      result.update(returnValue)
  print 'execution result=', result
  timestamp = telemetryFrame['timestamp']
  if timestamp >= nextSampleTime:
    AMI.submitResultToCollector(result)
    nextSampleTime = timestamp + samplingInterval

