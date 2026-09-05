# -*- coding: utf-8 -*-
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
from chat.groupchatadmin_ui import *
#import pyxl

from twisted.python import log
import dataforms

class table(QtGui.QTreeWidget):
	def __init__(self,parent=None):
		QtGui.QTreeWidget.__init__(self,parent)
		self.setDragEnabled(True)

	def startDrag(self,actions):
		# start dragging selected contact
		item=self.currentItem()
		jid=unicode(item.text(self.jidIndex))
		self.drag=QtGui.QDrag(self)
		mimeData=QtCore.QMimeData()
		mimeData.setText(jid)
		self.drag.setMimeData(mimeData)
		self.action=self.drag.start(QtCore.Qt.CopyAction)


class searchDialog(QtGui.QDialog):
	def __init__(self,main,jid,form,parent=None,add=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.main=main
		self.jid=jid
		self.form=form
		self.addDialog=add
		l=QtGui.QVBoxLayout(self)
		self.splitter = QtGui.QSplitter(self)
		self.splitter.setOrientation(QtCore.Qt.Horizontal)
		l.addWidget(self.splitter)
		self.widget=QtGui.QWidget(self.splitter)

		layout=QtGui.QGridLayout(self.widget)
		self.var,row=dataforms.makeDataForm(self.widget,layout,self.form)

		self.ok=QtGui.QPushButton(self.tr("Search"),self.widget)
		self.add=QtGui.QPushButton(self.tr("Add to roster"),self.widget)
		self.cancel=QtGui.QPushButton(self.tr("Cancel"),self.widget)

		QtCore.QObject.connect(self.ok,QtCore.SIGNAL("clicked()"),self.search)
		QtCore.QObject.connect(self.add,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.cancel,QtCore.SIGNAL("clicked()"),self.reject)

		self.table=table(self.splitter)
		self.table.header().hide()
		#self.table.hide()

		hlayout=QtGui.QHBoxLayout()
		hlayout.addStretch()
		hlayout.addWidget(self.ok)
		hlayout.addWidget(self.add)
		hlayout.addWidget(self.cancel)
		l.addLayout(hlayout)

		self.splitter.setSizes([(self.width()/3)*2,(self.width()/3)])

	def accept(self):
		item=self.table.currentItem()
		if item:
			if self.addDialog:
				self.addDialog.ui.add_jid.setText(item.text(self.table.jidIndex))
				self.addDialog.jidChanged()
			else:
				self.main().addContactMainWindow(item.text(self.table.jidIndex))
			self.done(1)

	def _gotResults(self,data):
		self.table.clear()
		#self.table.show()
		#self.widget.hide()
		self.splitter.setSizes([(self.width()/3),(self.width()/3)*2])
		jid,legacy,form=data
		#<x xmlns='jabber:x:data' type='result'><title>Search Results for users.netlab.cz</title><reported><field var='jid' label='Jabber ID'/><field var='fn' label='Full Name'/><field var='given' label='Name'/><field var='middle' label='Middle Name'/><field var='family' label='Family Name'/><field var='nickname' label='Nickname'/><field var='bday' label='Birthday'/><field var='ctry' label='Country'/><field var='locality' label='City'/><field var='email' label='Email'/><field var='orgname' label='Organization Name'/><field var='orgunit' label='Organization Unit'/></reported>
		#<item><field var='jid'><value>hanzz@jabbim.pl</value></field><field var='fn'><value/></field><field var='family'><value/></field><field var='given'><value/></field><field var='middle'><value/></field><field var='nickname'><value/></field><field var='bday'><value/></field><field var='ctry'><value/></field><field var='locality'><value/></field><field var='email'><value/></field><field var='orgname'><value/></field><field var='orgunit'><value/></field></item></x>
		fields={}

		i=0
		for x in form.elements():
			if x.name=="reported":
				for field in x.elements():
					if field.name=="field":
						fields[field['var']] = { 'index': i, 'empty': True }
						self.table.headerItem().setText(i,field['label'])
						i+=1
			elif x.name=="item":
				item=QtGui.QTreeWidgetItem(self.table)
				for field in x.elements():
					if field.name=="field":
						text=u""
						for y in field.elements():
							if y.name=="value":
								text=unicode(y).strip()
						item.setText(fields[field['var']]['index'], text)
						if len(text) > 0:
							fields[field['var']]['empty'] = False;
						if not self.table.jidIndex:
							if field['var']=='jid':
								self.table.jidIndex=fields[field['var']]['index']
		# set all columns' visibility before resizing any of them
		for f in fields.itervalues():
			self.table.setColumnHidden(f['index'], f['empty'])
		for f in fields.itervalues():
			if not f['empty']:
				self.table.resizeColumnToContents(f['index'])
		self.table.header().show()

	def search(self):
		self.table.jidIndex=None
		form=dataforms.sendDataForm(self.main(),self.jid,self.form,self.var,"only get form")
		d=self.main().client.setSearchForm(self.jid,forms=form)
		d.addCallback(self._gotResults)


		#dataforms.sendDataForm(self.main,self.jid,self.form,self.var,"muc")
		#self.done(1)

	#def reject(self):
		#self.close()
