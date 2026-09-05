"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""
from PyQt4 import QtCore, QtGui
from filetransfer_ui import *
from os.path import basename

class delegate(QtGui.QItemDelegate):
	def __init__(self,parent=None):
		apply(QtGui.QItemDelegate.__init__,(self,parent))
	def createEditor(self,parent,option,index):
		if index.column() == 1:
			return QtGui.QItemDelegate(self).createEditor(parent, option, index)
		return False

class filetransferDialog(QtGui.QDialog):
	def __init__(self,main,files,jid,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.ui=Ui_fileTransfer()
		self.ui.setupUi(self)
		self.main=main
		self.files=files
		self.jid=jid
		self.d=delegate(self.ui.treeWidget)
		self.ui.treeWidget.setItemDelegate(self.d)
		self.ui.treeWidget.setIconSize(QtCore.QSize(64,64))
		for file in self.files:
			item=QtGui.QTreeWidgetItem(self.ui.treeWidget)
			item.setText(0,basename(unicode(file)))
			item.setData(32,0,QtCore.QVariant(unicode(file)))
			item.setFlags(QtCore.Qt.ItemIsEditable| QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
		#QtCore.QObject.connect(self.ui.treeWidget, QtCore.SIGNAL("itemClicked ( QTreeWidgetItem * , int)"),self.icon)

	#def icon(self,item,old):
		#print item
		#it=item.data(32,0)
		#file=unicode(it.toString())
		#if file.lower().endswith("png") or file.lower().endswith("jpg"):
			#if item.icon(0).isNull():
				#pixmap=QtGui.QPixmap(file)
				#pixmap=pixmap.scaled(QtCore.QSize(64,64))
				#icon=QtGui.QIcon(pixmap)
				#item.setIcon(0,icon)
		

	def accept(self):
		descriptions={}
		for i in range(int(self.ui.treeWidget.topLevelItemCount())):
			child=self.ui.treeWidget.topLevelItem(i)
			it=child.data(32,0)
			file=unicode(it.toString())
			descriptions[file]=unicode(child.text(1))
		jid=self.jid
		file=self.files

		self.main.events.addFTUploadEvent(jid,file,descriptions)
		self.done(1)
