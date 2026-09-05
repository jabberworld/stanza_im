from PyQt4 import QtCore, QtGui

class FakeTabBar(QtGui.QTabBar):
	def __init__(self, tabwidget):
		QtGui.QTabBar.__init__(self, tabwidget)
		self.roster = None  # it must be set externally when the rosterLiveWidget is created

#	def mousePressEvent(self,event):
#		if event.button()==QtCore.Qt.LeftButton:
#			i=self.tabAt(event.pos())
#			if i==0:
#				self.roster.favouriteMode=False
#				self.roster.setSize()
#				self.roster.repaint()
#				return QtGui.QTabBar.mousePressEvent(self,event)
#			elif i==1:
#				self.setCurrentIndex(0)
#				self.blockSignals(True)
#				r=QtGui.QTabBar.mousePressEvent(self,event)
#				self.blockSignals(False)
#				self.roster.favouriteMode=True
#				self.roster.setSize()
#				self.roster.repaint()
#				return r
#			else:
#				return QtGui.QTabBar.mousePressEvent(self,event)

class FakeTabWidget(QtGui.QTabWidget):
	def __init__(self, parent):
		QtGui.QTabWidget.__init__(self, parent)
		self.tabbar = FakeTabBar(self)
	        self.setTabBar(self.tabbar)
