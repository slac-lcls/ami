#
# worker1
#

import numpy
import dill


workerGraph = dill.load(open('workerGraph1.dat', 'rb'))
reset = True
nextDisplayInterval = 10

while nextDisplayInterval < 100:

    if reset:
        workerInput = {
            'xppcspad' : numpy.ones((1024, 1024)) * 3,
            'roiLambda' : lambda image : [ (int(image.shape[0] * .1)), (int(image.shape[0] * .9)), (int(image.shape[1] * .1)), (int(image.shape[1]* .9)) ],
            'imageSumIn' : numpy.zeros((1024, 1024)),
            'counterIn' : 0,
            'timestampIn' : 0
        }
        reset = False
    else:
        workerInput2 = {}
        workerInput2['xppcspad'] = numpy.ones((1024, 1024)) * 7
        workerInput2['roiLambda'] = workerInput['roiLambda']
        workerInput2['reducedImageSumIn'] = out['reducedImageSumOut']
        workerInput2['counterIn'] = out['counterOut']
        workerInput2['timestampIn'] = out['timestampOut'] + 1
        workerInput = workerInput2

    print('--------------------------------------')
    out = workerGraph(workerInput, outputs=['reducedImageSumOut', 'counterOut', 'timestampOut'])
    print(out)

    if out['timestampOut'] >= nextDisplayInterval:
        outputFileName = 'worker1.' + str(nextDisplayInterval) + '.dat'
        dill.dump(out, open(outputFileName, 'wb'))
        nextDisplayInterval = nextDisplayInterval + 10
        reset = True
