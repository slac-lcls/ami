#
# collector graph sample1
#
# downsample data to display rate
# collect stripchart display points
# also compute average across time
#

import AMI_graph as AMI

_cspad0StripChartBuffer = []
_cspad0StripChartBufferWidth = 1024
_cspad0StripChartBufferRollingSum = 0
_timeAveragedCspad0StripChartBuffer = []
_timeAveragedCspad0StripChartBufferWidth = 1024

def collectorGraph(computationResult):

  if len(_cspad0StripChartBuffer) >= _cspad0StripChartBufferWidth:
    _cspad0StripChartBufferRollingSum = _cspad0StripChartBufferRollingSum - _cspad0StripChartBuffer[0]
    _cspad0StripChartBuffer = _cspad0StripChartBuffer[1:]
  _meanIn_cspad0ROI = computationResult[ '_meanIn_cspad0ROI' ]
  _cspad0StripChartBuffer.append(_meanIn_cspad0ROI)
  _cspad0StripChartBufferRollingSum = _cspad0StripChartBufferRollingSum + _meanIn_cspad0ROI

  if len(_timeAveragedCspad0StripChartBuffer) >= _timeAveragedCspad0StripChartBufferWidth:
    _timeAveragedCspad0StripChartBuffer = _timeAveragedCspad0StripChartBuffer[1:]
  _timeAveragedCspad0StripChartBuffer.append(_cspad0StripChartBufferRollingSum / len(_cspad0StripChartBuffer))

  return { '_cspad0StripChartBuffer' : _cspad0StripChartBuffer, '_timeAveragedCspad0StripChartBuffer' : _timeAveragedCspad0StripChartBuffer, 'cspad0' : computationResult[ 'cspad0' ], '_meanIn_cspad0ROI' : computationResult[ '_meanIn_cspad0ROI' ] }

computationResult = AMI.getComputationResult()
AMI.collectorResultIs(collectorGraph(computationResult))
