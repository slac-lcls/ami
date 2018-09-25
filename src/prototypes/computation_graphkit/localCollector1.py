#
# localCollector1
#

import dill

localCollectorGraph = dill.load(open('localCollectorGraph1.dat', 'rb'))

timestamp = 10
displayInterval = 10

while timestamp < 100:
    inFileName = 'worker1.' + str(timestamp) + '.dat'
    try:
        inFile = open(inFileName, 'rb')
    except FileNotFoundError:
        break
    workerOutput1 = dill.load(inFile)
    inFile.close()

    localCollectorInput = {}
    localCollectorInput['imageSumsIn'] = [ workerOutput1['reducedImageSumOut'] ]
    localCollectorInput['countersIn'] = [ workerOutput1['counterOut'] ]
    localCollectorInput['timestampIn'] = workerOutput1['timestampOut']

    out = localCollectorGraph(localCollectorInput, outputs=['imageSumsSumOut', 'countersSumOut', 'timestampOut'])
    print(out)
    outputFileName = 'localCollector1.' + str(out['timestampOut']) + '.dat'
    dill.dump(out, open(outputFileName, 'wb'))
    timestamp = timestamp + displayInterval
