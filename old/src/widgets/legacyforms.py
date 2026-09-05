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
import pyxl
import weakref
from twisted.python import log

class legacyFormsDialog(QtGui.QDialog):
	def __init__(self,main,form,jid,typ,parent=None):
		if isinstance(parent,weakref.ref):
			parent=parent()
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(True)
		if isinstance(main,weakref.ref):
			self.main	= main
		else:
			self.main	= weakref.ref(main)
		self.typ=typ
		self.jid=jid
		self.form=form
		layout=QtGui.QGridLayout(self)
		print unicode(form)
	
		self.instructions=QtGui.QTextEdit(self)
		self.instructions.setReadOnly(True)
		layout.addWidget(self.instructions,0,0,1,2)
		self.setMaximumWidth(400);
		self.var={}
		row=1
		registered=False
		#{u'username': u'240134309', u'registered': u'', u'password': u'', u'key': u'3c5d7a5b38d08d4cbb83c7c685b77fecd1cd4934', u'instructions': u'Please enter your UIN and password'}
		for key,value in self.form.iteritems():
			if key=="title":
				self.setWindowTitle(unicode(value))
			elif key=="instructions":
				self.instructions.setText(unicode(value))
			elif key=="registered":
				registered=True
			elif key=="password":
				label=QtGui.QLabel(self.tr("Password:"),self)
				layout.addWidget(label,row,0)
				widget=QtGui.QLineEdit(self)
				widget.setEchoMode(QtGui.QLineEdit.Password)
				widget.setText(unicode(value))
				layout.addWidget(widget,row,1)
				self.var[key]=widget
				row+=1
			elif key=="key":
				self.var[key]=unicode(value)
			else:
				label=QtGui.QLabel(key+":",self)
				layout.addWidget(label,row,0)
				widget=QtGui.QLineEdit(self)
				widget.setText(unicode(value))
				layout.addWidget(widget,row,1)
				self.var[key]=widget
				row+=1
		if registered:
			label=QtGui.QLabel(self.tr("Service has been already registered."),self)
			layout.addWidget(label,row,0,1,2)
			row+=1

		self.ok=QtGui.QPushButton(self.tr("OK"),self)
		self.cancel=QtGui.QPushButton(self.tr("Cancel"),self)

		if registered:
			self.unregister=QtGui.QPushButton(self.tr("Unregister"),self)
			layout.addWidget(self.unregister,row,1)
			QtCore.QObject.connect(self.unregister,QtCore.SIGNAL("clicked()"),self.unregisterClicked)

		QtCore.QObject.connect(self.ok,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.cancel,QtCore.SIGNAL("clicked()"),self.reject)
		
		layout.addWidget(self.ok,row+1,0)
		layout.addWidget(self.cancel,row+1,1)

	def unregisterClicked(self):
		self.main().client.setRegisterForm(self.jid,remove=True)

		self.reject()
	def accept(self):
		form={}
		if self.typ=="disco":
			for key,widget in self.var.iteritems():
				if key=="key":
					form[key]=widget
				else:
					form[key]=unicode(widget.text())
			self.main().client.setRegisterForm(self.jid,legacy=form)
			#print form
		self.done(1)

	#def reject(self):
		#self.close()
