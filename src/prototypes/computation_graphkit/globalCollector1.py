
#
# globalCollector1
#

import dill

globalCollectorGraph = dill.load(open('globalCollectorGraph1.dat', 'rb'))

timestamp = 10
displayInterval = 10

while timestamp < 100:
    inFileName = 'localCollector1.' + str(timestamp) + '.dat'
    try:
        inFile = open(inFileName, 'rb')
    except FileNotFoundError:
        break
    localCollectorOutput1 = dill.load(inFile)
    inFile.close()

    globalCollectorInput = {}
    globalCollectorInput['imageSumsIn'] = localCollectorOutput1['imageSumsSumOut']
    globalCollectorInput['countersSumIn'] = localCollectorOutput1['countersSumOut']
    globalCollectorInput['timestampIn'] = localCollectorOutput1['timestampOut']

    out = globalCollectorGraph(globalCollectorInput, outputs=['imageMeanOut', 'timestampOut'])
    print(out)
    outputFileName = 'globalCollector1.' + str(out['timestampOut']) + '.dat'
    dill.dump(out, open(outputFileName, 'wb'))
    timestamp = timestamp + displayInterval
