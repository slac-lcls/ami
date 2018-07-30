import AMI_common as AMI

class object(AMI.GraphElement):

  def __init__(self, name, sourceVector):
    super(object, self).__init__(name)
    self.sourceVector = sourceVector


class object2(AMI.GraphElement):

  def __init__(self, name, sourceVector, dataPoint, meanIntensity):
    super(object2, self).__init__(name)
    self.sourceVector = sourceVector
    self.dataPoint = dataPoint
    self.meanIntensity = meanIntensity

