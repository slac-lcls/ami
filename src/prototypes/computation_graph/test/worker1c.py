#
# worker1c.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
print('worker 1c result is', result)

graph._transmitWorkerData('worker1c.dat')


