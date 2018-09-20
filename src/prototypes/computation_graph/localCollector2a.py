#
# localCollector2.py
#

import AMI_server as AMI

print('read work graph')
graph1 = AMI.workerGraph()
graph1._receiveWorkerData('worker1.dat')

graph2 = AMI.workerGraph()
graph2._receiveWorkerData('worker2.dat')

result = graph1._doLocalCollector(graph2)
print('localCollector 2a result is', result)

graph1._transmitLocalCollectorData('localCollector2a.dat')


