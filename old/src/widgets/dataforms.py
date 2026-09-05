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

from twisted.python import log

def makeDataForm(parent,layout,form,row=1):
	var={}
	for x in form.elements():
		if unicode(x.name)=="field":
			if x['type']=="text-single":
				try:
						label=QtGui.QLabel(x['label'],parent)
				except KeyError:
						label=None
				layout.addWidget(label,row,0)
				widget=QtGui.QLineEdit(parent)
				for child in x.elements():
					if child.name == 'value':
						widget.setText(unicode(child))
				layout.addWidget(widget,row,1)
				var[x['var']]={'widget':widget,'type':x['type']}
				row+=1
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
			elif x['type']=="fixed":
				try:
					label=QtGui.QLabel(x['label'],parent)
					layout.addWidget(label,row,0)
				except KeyError:
					label=None
				text=QtGui.QLabel(parent)
				text.setWordWrap(True)
				for child in x.elements():
					if child.name == 'value':
						text.setText(unicode(child))
				if label==None:
					layout.addWidget(text,row,0,1,2)
				else:
					layout.addWidget(text,row,1)
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
			elif x['type']=="text-multi":
				try:
						label=QtGui.QLabel(x['label'],parent)
				except KeyError:
						label=None
				layout.addWidget(label,row,0)
				widget=QtGui.QTextEdit(parent)
				text=""
				for child in x.elements():
					if child.name == 'value':
						text+=unicode(child)+"\n"
				widget.setText(unicode(text))
				layout.addWidget(widget,row,1)
				var[x['var']]={'widget':widget,'type':x['type']}
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
			elif x['type']=="boolean":
				try:
						ltext=x['label']
				except KeyError:
						ltext=""
				widget=QtGui.QCheckBox(ltext,parent)
				for child in x.elements():
					if child.name == 'value':
						if unicode(child)=="0" or unicode(child).lower()=="false":
							widget.setChecked(False)
						elif unicode(child)=="1" or unicode(child).lower()=="true":
							widget.setChecked(True)
				layout.addWidget(widget,row,0,1,2)
				var[x['var']]={'widget':widget,'type':x['type']}
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
			elif x['type']=="text-private":
				try:
						label=QtGui.QLabel(x['label'],parent)
				except KeyError:
						label=None
				layout.addWidget(label,row,0)
				widget=QtGui.QLineEdit(parent)
				widget.setEchoMode(QtGui.QLineEdit.Password)
				for child in x.elements():
					if child.name == 'value':
						widget.setText(unicode(child))
				layout.addWidget(widget,row,1)
				var[x['var']]={'widget':widget,'type':x['type']}
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
			elif x['type']=="list-single":
				#<field var='userlist' type='list-single' label='Userlist on GG server'><value>get</value><option label='ignore'><value>ignore</value></option><option label='retrieve'><value>get</value></option></field>
				try:
						label=QtGui.QLabel(x['label'],parent)
				except KeyError:
						label=None
				layout.addWidget(label,row,0)
				widget=QtGui.QComboBox(parent)
				default=""
				cur=0
				for child in x.elements():
					if child.name == 'value':
						default=unicode(child)
					elif child.name=="option":
						for ch in child.elements():
							if ch.name=="value":
								widget.addItem(child['label'], QtCore.QVariant(unicode(ch)))
								if unicode(ch)==default:
									widget.setCurrentIndex(cur)
								cur=cur+1
				layout.addWidget(widget,row,1)
				var[x['var']]={'widget':widget,'type':x['type']}
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
			elif x['type']=="list-multi":
				#<field var='userlist' type='list-single' label='Userlist on GG server'><value>get</value><option label='ignore'><value>ignore</value></option><option label='retrieve'><value>get</value></option></field>
				try:
					label=QtGui.QLabel(x['label'],parent)
				except KeyError:
					label=None
				layout.addWidget(label,row,0)
				widget=QtGui.QListWidget(parent)
				widget.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
				default=[]
				for child in x.elements():
					if child.name == 'value':
						default.append(unicode(child))
					elif child.name=="option":
						for ch in child.elements():
							if ch.name=="value":
								item=QtGui.QListWidgetItem(unicode(child['label']))
								item.setData(32,QtCore.QVariant(unicode(ch)))
								widget.addItem(item)
								if unicode(ch) in default:
									item.setSelected(True)
				#widget.setCurrentIndex(0)
				layout.addWidget(widget,row,1)
				var[x['var']]={'widget':widget,'type':x['type']}
				for d in x.elements():
					if d.name == "desc":
						widget.setToolTip(unicode(d))
				row+=1
	return var,row

def updateDataForm(var,form,row=1):
	for x in form.elements():
		if unicode(x.name)=="field":
			if x['type']=="text-single":
				widget=var[x['var']]['widget']
				for child in x.elements():
					if child.name == 'value':
						widget.setText(unicode(child))
			elif x['type']=="text-multi":
				widget=var[x['var']]['widget']
				text=""
				for child in x.elements():
					if child.name == 'value':
						text+=unicode(child)+"\n"
				widget.setText(unicode(text))
			elif x['type']=="boolean":
				widget=var[x['var']]['widget']
				for child in x.elements():
					if child.name == 'value':
						if unicode(child)=="0" or unicode(child).lower()=="false":
							widget.setChecked(False)
						elif unicode(child)=="1" or unicode(child).lower()=="true":
							widget.setChecked(True)
			elif x['type']=="text-private":
				widget=var[x['var']]['widget']
				for child in x.elements():
					if child.name == 'value':
						widget.setText(unicode(child))
			elif x['type']=="list-single":
				widget=var[x['var']]['widget']
				widget.clear()
				default=""
				for child in x.elements():
					if child.name == 'value':
						default=unicode(child)
					elif child.name=="option":
						for ch in child.elements():
							if ch.name=="value":
								if unicode(ch)==default:
									widget.insertItem(0,unicode(child['label']),QtCore.QVariant(unicode(ch)))
								else:
									widget.addItem(child['label'], QtCore.QVariant(unicode(ch)))
				widget.setCurrentIndex(0)
			elif x['type']=="list-multi":
				widget=var[x['var']]['widget']
				widget.clear()
				default=""
				cur=None
				for child in x.elements():
					if child.name == 'value':
						default=unicode(child)
					elif child.name=="option":
						for ch in child.elements():
							if ch.name=="value":
								item=QtGui.QListWidgetItem(unicode(child['label']))
								item.setData(32,QtCore.QVariant(unicode(ch)))
								if unicode(ch)==default:
									cur=item
								widget.addItem(item)
				#widget.setCurrentIndex(0)
				if cur:
					widget.setCurrentItem(cur)
	return var,row

def getVarData(var):
	ret={}
	for key,value in var.iteritems():
		typ=value['type']
		widget=value['widget']
		if typ=="text-single" or typ=="text-private":
			ret[key]=unicode(widget.text())
		elif typ=="text-multi":
			text=unicode(widget.toPlainText())
			ret[key]=unicode(text)
		elif typ=="boolean":
			if widget.isChecked():
				text="True"
			else:
				text="False"
			ret[key]=unicode(text)
		elif typ=="list-single":
			ret[key]=unicode(widget.itemData(widget.currentIndex()).toString())
		elif typ=='list-multi':
			selected=[]
			for item in widget.selectedItems():
				selected.append(unicode(item.data(32).toString()))
			ret[key]=selected
	return ret

def sendDataForm(main,jid,form,var,t,unregister=False):
	for x in form.elements():
		if unicode(x.name)=="field":
			if x.hasAttribute("var"):
				if var.has_key(x['var']):
					widget=var[x['var']]['widget']
					typ=var[x['var']]['type']
					if typ=="text-single" or typ=="text-private":
						make=True
						for child in x.elements():
							if child.name == 'value':
								make=False
								child.children = []
								child.children.append(unicode(widget.text()))
						if make:
							x.addElement('value', content = unicode(widget.text()))
					elif typ=="text-multi":
						make=True
						text=unicode(widget.toPlainText())
						text=text.split('\n')
						#while '' in text:
							#text.remove('')
						
						for child in x.elements():
							if child.name == 'value':
								make=False
								child.children = []
								if len(text)!=0:
									child.children.append(text[0])
									text.remove(text[0])
						for tx in text:
							x.addElement('value', content = unicode(tx))
					elif typ=="list-multi":
						make=True
						#text=unicode(widget.toPlainText())
						#text=text.split('\n')
						selected=[]
						for item in widget.selectedItems():
							selected.append(unicode(item.data(32).toString()))
						
						for child in x.elements():
							if child.name == 'value':
								make=False
								child.children = []
								if len(selected)!=0:
									child.children.append(selected[0])
									selected.remove(selected[0])
						for text in selected:
							x.addElement('value', content = unicode(text))
						#if make:
							#x.addElement('value', content = unicode(widget.toPlainText()))
					elif typ=="boolean":
						make=True
						if widget.isChecked():
							text="1"
						else:
							text="0"
						for child in x.elements():
							if child.name == 'value':
								make=False
								child.children = []
								child.children.append(text)
						if make:
							x.addElement('value', content = text)
					elif typ=="list-single":
						make=True
						for child in x.elements():
							if child.name == 'value':
								make=False
								child.children = []
								child.children.append(unicode(widget.itemData(widget.currentIndex()).toString()))
						if make:
							x.addElement('value', content = unicode(widget.itemData(widget.currentIndex()).toString()))
		
	if t=="muc":
		main.client.setMUCConfig(jid, form)
	elif t=="register":
		if unregister:
			main.client.setRegisterForm(jid,remove=True)
		else:
			main.client.setRegisterForm(jid,forms=form)
	form["type"] = "submit"
	return form

class abstractDataFormsDialog(QtGui.QDialog):
	def __init__(self,main,form,jid,typ,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		self.main=main
		self.typ=typ
		self.jid=jid
		self.form=form
		layout=QtGui.QGridLayout(self)
		
		self.setMaximumWidth(400)
		self.var={}
		row=0
		for x in form.elements():
			if unicode(x.name)=="title":
				self.setWindowTitle(unicode(x))

		self.var,row=makeDataForm(self,layout,form)

		self.ok=QtGui.QPushButton(self.tr("OK"),self)
		self.cancel=QtGui.QPushButton(self.tr("Cancel"),self)

		QtCore.QObject.connect(self.ok,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.cancel,QtCore.SIGNAL("clicked()"),self.reject)
		
		layout.addWidget(self.ok,row+1,0)
		layout.addWidget(self.cancel,row+1,1)

	def getForm(self):
		return sendDataForm(self.main,"",self.form,self.var,None)



class dataFormsDialog(QtGui.QDialog):
	def __init__(self,main,form,jid,typ,parent=None):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.setModal(False)
		#print unicode(form.toXml())
		self.main=main
		self.typ=typ
		self.jid=jid
		self.form=form
		#child = form.firstChildElement()
		#print "ELEMENTS",unicode(child.toXml())
		#print "ELEMENTS",child.elements()
		layout=QtGui.QGridLayout(self)
		
		#self.instructions=QtGui.QTextEdit(self)
		#self.instructions.setReadOnly(True)
		#layout.addWidget(self.instructions,0,0,1,2)
		self.setMaximumWidth(400);
		self.var={}
		row=0
		registered=False
		for x in form.elements():
			if unicode(x.name)=="title":
				self.setWindowTitle(unicode(x))
			elif unicode(x.name)=="registered":
				registered=True

		self.var,row=makeDataForm(self,layout,form)

		self.ok=QtGui.QPushButton(self.tr("OK"),self)
		self.cancel=QtGui.QPushButton(self.tr("Cancel"),self)

		if registered:
			self.unregister=QtGui.QPushButton(self.tr("Unregister"),self)
			QtCore.QObject.connect(self.unregister,QtCore.SIGNAL("clicked()"),self.unregisterClicked)
			layout.addWidget(self.unregister,row,1)
		QtCore.QObject.connect(self.ok,QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(self.cancel,QtCore.SIGNAL("clicked()"),self.reject)
		
		layout.addWidget(self.ok,row+1,0)
		layout.addWidget(self.cancel,row+1,1)

	def unregisterClicked(self):
		sendDataForm(self.main,self.jid,form,self.var,self.typ,unregister=True)

	def accept(self):
		form=self.form
		sendDataForm(self.main,self.jid,form,self.var,self.typ)
		#for x in form.elements():
			#if unicode(x.name)=="field":
				#if x.hasAttribute("var"):
					#if self.var.has_key(x['var']):
						#widget=self.var[x['var']]['widget']
						#typ=self.var[x['var']]['type']
						#if typ=="text-single" or typ=="text-multi" or typ=="text-private":
							#make=True
							#for child in x.elements():
								#if child.name == 'value':
									#make=False
									#child.children = []
									#child.children.append(unicode(widget.text()))
							#if make:
								#x.addElement('value', content = unicode(widget.text()))
						#elif typ=="boolean":
							#make=True
							#if widget.isChecked():
								#text="1"
							#else:
								#text="0"
							#for child in x.elements():
								#if child.name == 'value':
									#make=False
									#child.children = []
									#child.children.append(text)
							#if make:
								#x.addElement('value', content = text)
						#elif typ=="list-single":
							#make=True
							#for child in x.elements():
								#if child.name == 'value':
									#make=False
									#child.children = []
									#child.children.append(unicode(widget.itemData(widget.currentIndex()).toString()))
							#if make:
								#x.addElement('value', content = unicode(widget.itemData(widget.currentIndex()).toString()))
			
		#if self.typ=="muc":
			#self.main.client.setMUCConfig(self.jid, form)
		#elif self.typ=="register":
			#self.main.client.setRegisterForm(self.jid,forms=form)

		self.done(1)

	#def reject(self):
	#	self.close()
