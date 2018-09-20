#
# client
#
# Env data source, plot mean v time, normalize by, weight by
#

import AMI_client as AMI

def normalizedWeighted(x, normalize, weight):
  return float(x) / float(normalize) * float(weight)


if(True):
  data = AMI.displayResult() # get the current frame of subscribed data
  print data
