#
# server sample 2
#

import AMI_server as AMI
import numpy


if __name__ == '__main__':
  
  computationGraph = AMI.computationGraph()
  collectorGraph = AMI.collectorGraph()

  computationGraph.initialize()
  collectorGraph.initialize()

  telemetryFrame = AMI.ingestTelemetryFrame()
  computationResult = computationGraph.execute(telemetryFrame)
  collectorGraph.execute(computationResult)
  computationGraph.finalize()
  collectorGraph.finalize()
