# computation graph
import AMI_graph as AMI
import numpy

nextDisplayableTimestamp = 0
displayInterval = 10 # units

# cspad0
_cspad0_accumulator = numpy.array([0] * 1048576)
_cspad0_ROI = [0, 0, 1023, 1023]

def computationGraph(telemetryFrame):
  timestamp = telemetryFrame[ 'timestamp' ]
  # cspad0
  cspad0 = telemetryFrame[ "cspad0" ]
  global _cspad0_accumulator
  _cspad0_accumulator = AMI.mergeSeries(cspad0, _cspad0_accumulator, 0.9)
  _meanIn_cspad0_ROI = AMI.meanInROI(cspad0, _cspad0_ROI)

  global nextDisplayableTimestamp
  if timestamp >= nextDisplayableTimestamp:
    nextDisplayableTimestamp = nextDisplayableTimestamp + displayInterval
    return { 'timestamp' : timestamp, 'cspad0' : _cspad0_accumulator, '_meanIn_cspad0_ROI' : _meanIn_cspad0_ROI }
  else:
    return {}

telemetryFrame = AMI.ingestTelemetryFrame()
AMI.computationResultIs(computationGraph(telemetryFrame))
