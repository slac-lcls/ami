#
# server
#

import AMI_server as AMI


graph = AMI.workerGraph()

nextSampleTime = 0
samplingInterval = 100


if True:
  telemetryFrame = AMI.ingestTelemetryFrame()
  print('execute telemetry frame', telemetryFrame)
  result = graph._domap(telemetryFrame)
  print( 'execution result=', result)
  timestamp = telemetryFrame['timestamp']
  if timestamp >= nextSampleTime:
    AMI.submitResultToCollector(result)
    nextSampleTime = timestamp + samplingInterval

