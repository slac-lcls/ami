#
# worker1.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()

result = graph._doWorker()
print('worker result is', result)

graph._transmitWorkerData('worker1.dat')
