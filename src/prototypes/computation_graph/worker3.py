#
# worker3.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
print('worker 3 result is', result)

graph._transmitWorkerData('worker3.dat')


