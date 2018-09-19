#
# workerFunctions.py
#

import AMI_common as AMI
import numpy

def mean(self):
  print('in mean()', self, self.data)
  (data, samples) = self.data
  if samples == 0:
    self.data = ( self.operand, 1 )
  else:
    self.data = ( data + self.operand, samples + 1 )
  print('mean result', self.data)
  return self

def mean_(self):
  print("in mean_ worker reset", self)
  self.data = ( None, 0 )
  return self


def roi(self, value):
  print('in roi(' + str(value) + ')', self)
  string = str(value[0]) + ':' + str(value[1]) + ',' + str(value[2]) + ':' + str(value[3])
  expression = 'self.operand[' + string + '].copy()'
  self.data = eval(expression)
  print('roi result', self.data)
  return self


def calibrate(self, image):
  self.calibratedImage = image # call calibration code here
  self.result = self.calibratedImage
  return self


def peakfind(self, image):
  self.peaks = [ [ 0, 0 ] ]
  self.result = self.peaks
  return self

