'''
Created on 16.4.2010

@author: sef
'''
from PyQt4 import QtGui
class scrollBar(QtGui.QScrollArea):
	def __init__(self,parent=None):
		QtGui.QScrollArea.__init__(self,parent)
		self.y=0
		self.verticalScrollBar().setPageStep(32)
		self.verticalScrollBar().setSingleStep(32)
		self.setObjectName("scroll")