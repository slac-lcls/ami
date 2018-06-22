#
# display graph sample1
#
# scale cspad intensities according to average pixel intensity in ROI
#

import AMI_graph as AMI

def displayGraph(collectorResult):
  return { '_cspad0_stripChartBuffer' : collectorResult[ '_cspad0_stripChartBuffer' ], '_timeAveraged_cspad0_stripChartBuffer' : collectorResult[ '_timeAveraged_cspad0_stripChartBuffer' ], 'cspad0' : cspad0, '_meanIn_cspad0_ROI' : _meanIn_cspad0_ROI }

collectorResult = AMI.getCollectorResult()
AMI.displayResultIs(displayGraph(collectorResult))
