import AMI_graph as AMI
import numpy

  # cspad0
_meanIn_cspad0_ROI_stripChartBuffer = []
_meanIn_cspad0_ROI_stripChartBufferWidth = 1024
_meanIn_cspad0_ROI_stripChartBufferRollingSum = 0
_timeAveraged__meanIn_cspad0_ROI_stripChartBuffer = []
_timeAveraged__meanIn_cspad0_ROI_stripChartBufferWidth = 1024

def collectorGraph(computationResult):

  # cspad0
  if len(_meanIn_cspad0_ROI_stripChartBuffer) >= _meanIn_cspad0_ROI_stripChartBufferWidth:
    _meanIn_cspad0_ROI_stripChartBufferRollingSum = _meanIn_cspad0_ROI_stripChartBufferRollingSum - _meanIn_cspad0_ROI_stripChartBuffer[0]
    _meanIn_cspad0_ROI_stripChartBuffer = _meanIn_cspad0_ROI_stripChartBuffer[1:]
  _meanIn_cspad0_ROI = computationResult[ "_meanIn_cspad0_ROI" ]
  _meanIn_cspad0_ROI_stripChartBuffer.append(_meanIn_cspad0_ROI)
  _meanIn_cspad0_ROI_stripChartBufferRollingSum = _meanIn_cspad0_ROI_stripChartBufferRollingSum + _meanIn_cspad0_ROI

  if len(_timeAveraged__meanIn_cspad0_ROI_stripChartBuffer) >= _timeAveraged__meanIn_cspad0_ROI_stripChartBufferWidth:
    _timeAveraged__meanIn_cspad0_ROI_stripChartBuffer = _timeAveraged__meanIn_cspad0_ROI_stripChartBuffer[1:]
  _timeAveraged__meanIn_cspad0_ROI_stripChartBuffer.append(_meanIn_cspad0_ROI_stripChartBufferRollingSum / len(_meanIn_cspad0_ROI_stripChartBuffer))

  return { 'timestamp' : timestamp, '_meanIn_cspad0_ROI_stripChartBuffer' : computationResult[ '_meanIn_cspad0_ROI_stripChartBuffer' ], '_timeAveraged__meanIn_cspad0_ROI_stripChartBuffer' : computationResult[ '_timeAveraged__meanIn_cspad0_ROI_stripChartBuffer' ], 'cspad0' : computationResult[ 'cspad0' ], '_meanIn_cspad0_ROI' : computationResult[ '_meanIn_cspad0_ROI' ] }

computationResult = AMI.getComputationResult()
AMI.collectorResultIs(collectorGraph(computationResult))
