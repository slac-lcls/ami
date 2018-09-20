#
# worker3a.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

for i in range(10):
  result = graph._doWorker()
  if result is not None:
    print('worker 3a result is', result)

graph._transmitWorkerData('worker3a.dat')


