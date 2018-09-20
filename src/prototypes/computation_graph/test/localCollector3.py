#
# localCollector3.py
#

import AMI_server as AMI

print('read work graph')
graph1 = AMI.workerGraph()
graph1._receiveWorkerData('worker3a.dat')

graph2 = AMI.workerGraph()
graph2._receiveWorkerData('worker3b.dat')

result = graph1._doLocalCollector(graph2)
print('localCollector3 result is', result)

graph1._transmitLocalCollectorData('localCollector3.dat')

