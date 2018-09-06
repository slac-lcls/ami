#
# mapFunctions.py
#

import AMI_common as AMI
import numpy

def sum(self):
  print('in sum()')
  if not hasattr(self, 'accumulatorSum') or self.accumulatorSum is None:
    self.accumulatorSum = self.data
  else:
    self.accumulatorSum = numpy.add(self.accumulatorSum, self.data)
  self.result = self.accumulatorSum
  return self

def sum_(self):
  print("in sum_ reset")
  self.accumulatorSum = None
  self.result = None
  return self

def mean(self):
  print('in mean()')
  if not hasattr(self, 'accumulatorMean') or self.accumulatorMean is None:
    self.accumulatorMean = self.data
    self.samplesMean = 1
  else:
    self.accumulatorMean = numpy.add(self.accumulatorMean, self.data)
    self.samplesMean = self.samplesMean + 1
  self.result = (self.accumulatorMean, self.samplesMean)
  return self

def mean_(self):
  print("in mean_ reset")
  self.accumulatorMean = None
  self.result = None
  return self


def roi(self, value):
  print('in roi(' + str(value) + ')')
  string = str(value[0]) + ':' + str(value[1]) + ',' + str(value[2]) + ':' + str(value[3])
  if self.data is not None:
    expression = 'self.data[' + string + '].copy()'
    self.result = eval(expression)
  return self


def calibrate(self, image):
  self.calibratedImage = image # call calibration code here
  self.result = self.calibratedImage
  return self


def peakfind(self, image):
  self.peaks = [ [ 0, 0 ] ]
  self.result = self.peaks
  return self

