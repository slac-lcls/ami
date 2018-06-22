#
# server
#

import AMI_server as AMI






graph = AMI.workerGraph()
for element in graph.elements:
  element.initializeComputation()


nextSampleTime = 0
samplingInterval = 100

if True:
  telemetryFrame = AMI.ingestTelemetryFrame()
  result = {}
  for element in graph.elements:
    result.update(element.executeComputation(telemetryFrame))
  timestamp = telemetryFrame['timestamp']
  if timestamp >= nextSampleTime:
    AMI.submitResultToCollector(result)
    nextSampleTime = timestamp + samplingInterval

