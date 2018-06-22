#
# client sample1
#
# This client displays a cspad and a strip chart recorder.  A toggle on the GUI
# enables intensity normalization for the cspad (this normalization happens in
# the GUI).  The strip chart displays the time-averaged mean pixel intensity in
# the cspad region of interest.
#
# This sample exercises all three graphs.  The computation graph obtains the cspad
# image and computes the mean pixel intensity in the ROI.  The collector graph
#

import sys

from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

import AMI_graph as AMI


class UpdateWorker(QRunnable):
  '''
  Worker thread for updating display.
  '''
  is_interrupted = False
  
  def __init__(self):
    super(UpdateWorker, self).__init__()
  
  def updateWidgets(self, data):
    pass
  
  @pyqtSlot()
  def run(self):
    try:
      displayResult = AMI.displayResult()
      self.updateWidgets(displayResult)
      if self.is_interrupted:
        return
                  
    except Exception as e:
      print(e)
      exctype, value = sys.exc_info()[:2]#TODO
      return
                      
  def cancel(self):
    self.is_interrupted = True


class MainWindow(QMainWindow):
  
  def __init__(self, *args, **kwargs):
    super(MainWindow, self).__init__(*args, **kwargs)
    self.createGraphs()
    self.createWidgets()
    self.setWindowTitle("sample1")
    self.show()
    self.worker = UpdateWorker()
    self.threadpool = QThreadPool()
    self.threadpool.start(self.worker)

  def firstCSPAD(self, dataSources):
    return dataSources[0]#TODO
  
  def createGraphs(self):
    dataSources = AMI.dataSources()
    
    # computation graph
    computationGraph = AMI.ComputationGraph('computation1')
    cspad = AMI.CSPAD(self.firstCSPAD(dataSources).name, 1024, 1024)
    cspad.decayExponential(0.9)
    cspad.computeInROI(cspad.mean)
    computationGraph.add(cspad)
    AMI.computationGraphIs(computationGraph)
    
    # collector graph
    collectorGraph = AMI.CollectorGraph('collector1')
    stripChart = AMI.StripChart(cspad, 1024)
    stripChart.timeAverage(1024)
    collectorGraph.add(stripChart)
    AMI.collectorGraphIs(collectorGraph)
    
    # display graph
    displayGraph = DisplayGraph('display1')
    displayGraph.add(cspad)
    displayGraph.add(stripChart)
    AMI.displayGraphIs(displayGraph)
  
  def createWidgets(self):
    # setup cspad display
    # setup toggle button for intensity normalization
    # setup strip chart display
    pass

if __name__ == '__main__':
  
  app = QApplication(sys.argv)
  app.setApplicationName("sample1")
  
  window = MainWindow()
  app.exec_()
