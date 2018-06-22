#
# generateGraphs.py
#

import AMI_server, AMI_client



if __name__ == '__main__':

  from PyQt5.QtGui import *
  from PyQt5.QtWidgets import *
  from PyQt5.QtCore import *

  import sys
  import client_sample2
  app = QApplication(sys.argv)
  mainWindow = client_sample2.MainWindow()
  
  computationGraph = AMI_server.computationGraph()

  collectorGraph = AMI_server.collectorGraph()

  displayGraph = AMI_client.displayGraph()

  # TODO display graphs in visual/text form

