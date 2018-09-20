#
# localCollector1.py
#

import AMI_server as AMI

print('read work graph')
graph = AMI.workerGraph()
graph._receiveWorkerData('worker1a.dat')

result = graph._doLocalCollector()
print('localCollector result is', result)

graph._transmitLocalCollectorData('localCollector1.dat')

