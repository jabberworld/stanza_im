"""
Copyright (C) 2007 	Jan 'Hanzz' Kaluza (hanzz at njs.netlab.cz)
Copyright (C) 2007	Jiri 'Sef' Gabrys	(sef at njs.netlab.cz)

This program is free software; you can redistribute it and/or
#modify it under the terms of the GNU General Public License
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
import sys; sys.path.append('..')
import os
from statuseditor_ui import *
from configobj import ConfigObj
from statuswidget_ui import *

class statusWidgetWindow(QtGui.QDialog):
	def __init__(self,jid,main,parent=None,ID=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.main=main
		self.parent=parent
		self.ui=Ui_statusWidgetWindow()
		self.ui.setupUi(self)
		self.ID=ID
		#config=ConfigObj(self.main.homeDir+'/statusmessages',encoding='UTF8')
		if self.ID:
			self.main.cache.get_status_by_id(str(ID)).addCallback(self.gotStatus)
		self.ui.show.addItem(self.main.getIcon(status="online",size="16x16"), self.main.status["online"],QtCore.QVariant("online"))
		self.ui.show.addItem(self.main.getIcon(status="chat",size="16x16"), self.main.status["chat"],QtCore.QVariant("chat"))
		self.ui.show.addItem(self.main.getIcon(status="away",size="16x16"), self.main.status["away"],QtCore.QVariant("away"))
		self.ui.show.addItem(self.main.getIcon(status="xa",size="16x16"), self.main.status["xa"],QtCore.QVariant("xa"))
		self.ui.show.addItem(self.main.getIcon(status="dnd",size="16x16"), self.main.status["dnd"],QtCore.QVariant("dnd"))
		self.ui.show.setCurrentIndex(self.ui.show.findData(QtCore.QVariant(self.main.selfStatus)))
		self.jid=jid
		#app.connect(self.ui.show, QtCore.SIGNAL("activated ( const QString & )"),self.ui.status.setPlainText)

	def gotStatus(self,data):
		if not data:
			return
		if len(data)==0:
			return
		self.ui.show.setCurrentIndex(self.ui.show.findData(QtCore.QVariant(unicode(data[0][0]))))
		self.ui.status.setPlainText(unicode(data[0][1]))

	def accept(self):
		show=unicode(self.ui.show.itemData(self.ui.show.currentIndex()).toString())
		#config=ConfigObj(self.main.homeDir+'/statusmessages',encoding='UTF8')
		#config[show].append(unicode(self.ui.status.toPlainText ()))
		#config.write()
		if not self.ID:
			d=self.main.cache.set_status(show,unicode(self.ui.status.toPlainText ()))
			d.addCallback(self.main.status_table_updated)
			self.main.sendPresence(self.jid,show,unicode(self.ui.status.toPlainText ()))
		else:
			d=self.main.cache.update_status(show,unicode(self.ui.status.toPlainText ()),self.ID)
			d.addCallback(self.parent.profileRemoved)
		self.done(1)

class statusEditorWindow(QtGui.QDialog):
	def __init__(self,main,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.main=main
		self.ui=Ui_statusEditor()
		self.ui.setupUi(self)
		self.loadStatuses()
		QtCore.QObject.connect(self.ui.statusList, QtCore.SIGNAL("itemSelectionChanged()"),self.statusChanged)
		QtCore.QObject.connect(self.ui.removeStatus, QtCore.SIGNAL("clicked()"),self.removeProfile)
		QtCore.QObject.connect(self.ui.editStatus, QtCore.SIGNAL("clicked()"),self.editProfile)
		#QtCore.QObject.connect(self.ui.newProfile, QtCore.SIGNAL("clicked()"),self.newProfile)
		
		self.ui.removeStatus.setEnabled(False)
		self.ui.editStatus.setEnabled(False)

	def loadStatuses(self,data=None):
		print data
		if data==None:
			d=self.main.cache.get_status()
			d.addCallback(self.loadStatuses)
			return
		else:
			config={}
			config['online']=[]
			config['offline']=[]
			config['chat']=[]
			config['away']=[]
			config['xa']=[]
			config['dnd']=[]
			for status in data:
				config[status[0]].append([status[1],str(status[2])])
		self.ui.statusList.clear()
		self.ui.removeStatus.setEnabled(False)
		self.ui.editStatus.setEnabled(False)
		for key in ['online','chat','away','xa','dnd']:
			for val in config[key]:
				status=val[0]
				index=val[1]
				item=QtGui.QListWidgetItem(self.main.getIcon(status=key,size="16x16"),unicode(status),self.ui.statusList)
				#item.setData(32,QtCore.QVariant(int(config[key].index(status))))
				item.key=key
				item.index=int(index)
			
		return []


	def editProfile(self):
		item=self.ui.statusList.currentItem()
		cs = statusWidgetWindow(None,self.main,self,item.index)
		ret=cs.exec_()
		#if ret==1:
			#self.loadStatuses()

	def removeProfile(self):
		item=self.ui.statusList.currentItem()
		self.main.cache.del_status(str(item.index)).addCallback(self.profileRemoved)
	
	def profileRemoved(self,data=None):
		self.loadStatuses()
		self.main.buildStatusWidgetMenu()

	def statusChanged(self):
		if self.ui.statusList.currentItem():
			self.ui.removeStatus.setEnabled(True)
			self.ui.editStatus.setEnabled(True)
		else:
			self.ui.removeStatus.setEnabled(False)
			self.ui.editStatus.setEnabled(False)
	

