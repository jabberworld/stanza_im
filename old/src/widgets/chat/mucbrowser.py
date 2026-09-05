import os
from PyQt4 import QtCore, QtGui
from mucbrowser_ui import *
import pyxl
from twisted.internet import threads
from include.constants import RESOURCEPATH

class delegate(QtGui.QItemDelegate):
	def __init__(self,column,parent=None,space=0):
		QtGui.QItemDelegate.__init__(self,parent)
		self.column=column
		self.space=space
	
	def paint(self,painter,option,index):
		# selected item
		if option.state & QtGui.QStyle.State_Selected and index.column()==self.column:
			#option.rect.setHeight(50)
			option.displayAlignment=QtCore.Qt.AlignTop
			text=unicode(index.data(32).toString())
			QtGui.QItemDelegate.paint(self,painter,option,index)
			#metrics=QtGui.QFontMetrics(option.font)
			painter.save()
			painter.setPen(option.palette.highlightedText().color())
			#print option.fontMetrics.height(),option.rect.y()
			#painter.drawText(option.rect.x()+QtGui.QApplication.style().pixelMetric(QtGui.QStyle.PM_FocusFrameHMargin) + 1,option.rect.y()+option.fontMetrics.height(),option.rect.width(),option.rect.height(),QtCore.Qt.TextWordWrap,users)
			doc=QtGui.QTextDocument()
			opt=doc.defaultTextOption()
			opt.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
			doc.setDefaultTextOption(opt)
			doc.setDefaultFont(option.font)
			doc.setPageSize(QtCore.QSizeF(option.rect.width(),option.rect.height()-option.fontMetrics.height()))
			doc.setHtml("<font color=\"%s\">"%option.palette.highlightedText().color().name()+text+"</font>")
			painter.translate(option.rect.x()+1+self.space,option.rect.y()+option.fontMetrics.height())
			doc.drawContents(painter, QtCore.QRectF(0,0,option.rect.width(),option.rect.height()))
			painter.restore()
			return

		QtGui.QItemDelegate.paint(self,painter,option,index)
	
#	def sizeHint(self,option,index):
		# selected item
	#	if option.state & QtGui.QStyle.State_Selected:
		#	return QtCore.QSize(100,50)
		#return QtGui.QItemDelegate.sizeHint(self,option,index)

class MUCBrowserDialog(QtGui.QDialog):
	def __init__(self,main,server,joinDialog,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.ui=Ui_MUCBrowser()
		self.ui.setupUi(self)
		self.main=main
		self.joinDialog=joinDialog
		self.ui.groupchats.setItemDelegate(delegate(2,self.ui.groupchats))
		QtCore.QObject.connect(self.ui.groupchats, QtCore.SIGNAL("currentItemChanged ( QTreeWidgetItem * , QTreeWidgetItem * )"),self.selectionChanged)
		QtCore.QObject.connect(self.ui.groupchats, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem *, int )"),self.CE)
		QtCore.QObject.connect(self.ui.groupchats, QtCore.SIGNAL("itemDoubleClicked ( QTreeWidgetItem *, int)"),self.accept)
		QtCore.QObject.connect(self.ui.filter,QtCore.SIGNAL(" textChanged ( const QString &)"),self.filterChanged)
		self.room=""

		self.ui.groupchats.hideColumn(1)
		self.ui.groupchats.setColumnWidth(0,42)
		self.ui.groupchats.setSortingEnabled(True)
		self.ui.groupchats.hideColumn(3)

		self.server=server
		if len(self.server)!=0:
			self.main.client.getDiscoItems(self.server, callback = self._roomsReceived)

	def filterChanged(self,text):
		d=threads.deferToThread(self.compare,unicode(text),self.rooms)
		d.addCallback(self.compared)

	def compare(self,text,rooms):
		ret=[]
		print "+compare"
		for room in rooms:
			if unicode(room[0]).find(text)!=-1 or unicode(room[1]).find(text)!=-1:
				ret.append([unicode(room[0]),unicode(room[1]),int(room[2])])
		print "-compare",ret
		return ret
	def compared(self,rooms):
		print 'compared',rooms
		self.ui.groupchats.clear()
		self.showRooms(rooms)
	
	def showJid(self,b):
		if self.ui.showJid.isChecked():
			for i in range(self.ui.groupchats.topLevelItemCount()):
				item=self.ui.groupchats.topLevelItem(i)
				for x in range(item.childCount()):
					child=item.child(x)
					child.setText(1,unicode(child.text(2)))
					child.setIcon(1,child.icon(2))
					child.setText(2,"")
					child.setIcon(2,QtGui.QIcon())
			self.ui.groupchats.showColumn(1)
			self.ui.groupchats.resizeColumnToContents(1)
		else:
			self.ui.groupchats.hideColumn(1)
			for i in range(self.ui.groupchats.topLevelItemCount()):
				item=self.ui.groupchats.topLevelItem(i)
				for x in range(item.childCount()):
					child=item.child(x)
					child.setText(2,unicode(child.text(1)))
					child.setIcon(2,child.icon(1))
					child.setText(1,"")
					child.setIcon(1,QtGui.QIcon())
		self.ui.groupchats.setColumnWidth(0,42)
	
		#self.ui.groupchats.setColumnWidth(0,36)

	def CE(self,item,i):
		pass
		#if item.isExpanded():
			#self.ui.groupchats.collapseItem(item)
		#else:
			#self.ui.groupchats.expandItem(item)

	def selectionChanged(self,item,old):
		if item and old:
			item.setSizeHint(0,old.sizeHint(0))

		if old:
			old.setData(0,QtCore.Qt.SizeHintRole,QtCore.QVariant())

		if item.parent()==None:
			room = item.data(0, 32).toString()
			self.main.client.getDiscoItems(room, callback = self._participantsReceived, callback_par = (room, item,old))
			#r = room.split('@')[0]
			#self.ui.roomLabel.setText(self.tr("Room: ")+r)
			#self.room=r
			#self.ui.name.setText(r)


	def _participantsReceived(self, par):
		item = par[1]
		for i in range(int(item.childCount())):
			item.takeChild(0)
		if len(self.main.client.disco[unicode(par[0])][(unicode(par[0]),None)]['items'])!=0:
			users="<b>Users:</b> "
			for usr in self.main.client.disco[unicode(par[0])][(unicode(par[0]),None)]['items'].itervalues():
				users+=usr['name']+", "
		else:
			users="There is no user"
		if item in self.ui.groupchats.selectedItems():
			item.setData(2,32,QtCore.QVariant(users))
			metrics=QtGui.QApplication.fontMetrics()
			print self.ui.groupchats.columnWidth(2),self.ui.groupchats.columnWidth(1)
			rect=metrics.boundingRect(0, 0,self.ui.groupchats.columnWidth(2), self.main.height(), QtCore.Qt.TextWordWrap, "Users: "+unicode(item.data(2,32).toString()))
			print 'aa',metrics.height(),rect.height()
			item.setSizeHint(0,QtCore.QSize(100,metrics.height()*2+rect.height()))

	def getNum(self, string):
		def reverse(s):
			s = list(s)
			s.reverse()
			return "".join(s)
		s = reverse(string)
		i1, i2 = s.find(")"), s.find("(")
		try:
			cislo = int(reverse(s[i1+1:i2]))
		except:
			cislo = 0
		return cislo

	def sortRooms(self, x, y):
		if x[2] > y[2]:
			return 1
		elif x[2] == y[2]:
			return 0
		elif x[2] < y[2]:
			return -1

	def _roomsReceived(self, res):
		self.rooms = []
		self.ui.groupchats.clear()
		for room in self.main.client.disco[self.server][(self.server,None)]['items'].itervalues():
			self.rooms.append((room['name'], room['jid'], self.getNum(room['name'])))

		self.rooms.sort(self.sortRooms)
		self.showRooms(self.rooms)


	def showRooms(self,rooms):
		icon=QtGui.QIcon(RESOURCEPATH+"images/16x16/categories/muc.png")
		for room in rooms:
			item = QtGui.QTreeWidgetItem(0)
			item.setText(1,room[1])
			item.setText(2,room[0])
			item.setText(3,(int(room[2])+1)*'a')
			item.setData(0, 32, QtCore.QVariant(room[1]))
			item.setIcon(0,icon)
			self.ui.groupchats.insertTopLevelItem(0, item)
		self.ui.groupchats.sortByColumn(3,QtCore.Qt.DescendingOrder)

	def accept(self,item=None,index=None):
		item=self.ui.groupchats.currentItem()
		if not item:
			return
		room = item.data(0, 32).toString()
		self.joinDialog.ui.roomName.setText(room.split("@")[0])

		self.done(1)
