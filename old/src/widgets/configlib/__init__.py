from PyQt4 import QtCore, QtGui
import sys; sys.path.append('..')
import os
from pyxl import jid as jidT
from os.path import basename
import traceback
from include import rot13

class pluginConfiguration(QtGui.QDialog):
	def __init__(self,plugin,parent):
		apply(QtGui.QDialog.__init__,(self,parent))
		self.plugin=plugin
		self.setWindowTitle(plugin.name+" preferences")

		self.plugin.on_showPreferences(self)

		layout=QtGui.QGridLayout(self)
		self.var,row=makePreferences(self.plugin.config,self,layout,self.plugin.configDialog.config)

		layout2=QtGui.QHBoxLayout()
		close=QtGui.QPushButton("Close",self)
		save=QtGui.QPushButton("Save",self)
		layout2.addStretch()
		layout2.addWidget(close)
		layout2.addWidget(save)
		
		QtCore.QObject.connect(save, QtCore.SIGNAL("clicked()"),self.accept)
		QtCore.QObject.connect(close, QtCore.SIGNAL("clicked()"),self.reject)
		
		layout.addLayout(layout2,row,0,1,2)
	
	def accept(self):
		self.plugin.on_saveConfig()
		for key,value in getVarData(self.var).iteritems():
			self.plugin.config[key]=value
			print key,"=",unicode(value)
		self.plugin.writeConfig()
		self.done(1)

	def reject(self):
		self.plugin.on_endPreferences()
		#self.close()
		return QtGui.QDialog.reject(self)

def updateVarData(var,main):
	if var.has_key("__widget__"):
		return var['__widget__'].updateData(main)
	for key,value in var.iteritems():
		if main.has_key(key):
			val=main[key]
			if key=="passwd":
				val=rot13.scramble(val)
		else:
			continue
		
		typ=value['type']
		widget=value['widget']
		if (typ=="text-single" or typ=="text-private") or typ=='directory':
			widget.setText(val)
		elif typ=="time-interval":
			d=val.split(":")
			t=QtCore.QTime(int(d[0]),int(d[1]),int(d[2]))
			widget.setTime(t)
		elif typ=="text-multi":
			widget.setText(unicode(val))
		elif typ=="boolean":
			if unicode(val)=="0" or unicode(val).lower()=="false":
				widget.setChecked(False)
			elif unicode(val)=="1" or unicode(val).lower()=="true":
				widget.setChecked(True)
		elif typ=="list-single":
			if widget.findData(QtCore.QVariant(unicode(val)))!=None:
				widget.setCurrentIndex(widget.findData(QtCore.QVariant(unicode(val))))
		elif typ=="number-spin":
			widget.setValue(int(val))
		elif typ=="boolean-radio":
			data=widget.checkedButton().data
			if unicode(val)==unicode(data):
				widget.checkedButton().setChecked(True)
			else:
				widget.checkedButton().setChecked(False)
		elif typ=="jid-list":
			widget.jids.clear()
			if isinstance(val,list):
				for jid in val:
					QtGui.QListWidgetItem(unicode(jid),widget.jids)
		elif typ=="custom":
			widget.setWidgetValue(val)

def getVarData(var):
	ret={}
	if var.has_key("__widget__"):
		return var['__widget__'].getData()
	for key,value in var.iteritems():
		typ=value['type']
		widget=value['widget']
		if (typ=="text-single" or typ=="text-private") or typ=='directory':
			ret[key]=unicode(widget.text())
		elif typ=="time-interval":
			ret[key]=unicode(widget.time().toString("H:m:s"))
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
		elif typ=="number-spin":
			ret[key]=unicode(widget.value())
		elif typ=="boolean-radio":
			ret[key]=unicode(widget.checkedButton().data)
		elif typ=="jid-list":
			jids=[]
			for i in range(widget.jids.count()):
				item=widget.jids.item(i)
				jids.append(unicode(item.text()))
			ret[key]=jids
		elif typ=="custom":
			ret[key]=widget.getWidgetValue()
	return ret

class directoryWidget(QtGui.QLineEdit):
	def getDirectory(self):
		directory=unicode(QtGui.QFileDialog.getExistingDirectory(self,self.tr("Choose directory"),self.text(),QtGui.QFileDialog.ShowDirsOnly| QtGui.QFileDialog.DontResolveSymlinks))
		if len(directory)!=0:
			self.setText(directory)

class jidListWidget(QtGui.QWidget):
	"""
	Widget for displaying jid-list type in configAPI
	"""
	def __init__(self,parent=None):
		QtGui.QWidget.__init__(self,parent)
		# layout
		layout=QtGui.QGridLayout(self)
		self.jids=QtGui.QListWidget(self)
		add=QtGui.QPushButton(self.tr("Add"),self)
		remove=QtGui.QPushButton(self.tr("Remove"),self)
		layout.addWidget(self.jids,0,0,1,2)
		layout.addWidget(add,1,0,1,1)
		layout.addWidget(remove,1,1,1,1)
		# signals
		QtCore.QObject.connect(add,QtCore.SIGNAL("clicked()"),self.addJid)
		QtCore.QObject.connect(remove,QtCore.SIGNAL("clicked()"),self.removeJid)
	
	def removeJid(self):
		items=self.jids.selectedItems()
		if len(items)==0:
			return
		# TODO => allow to remove more items
		self.jids.takeItem(self.jids.row(items[0]))
		del items[0]
		
	def addJid(self):
		jid=""
		while 1:
			jid,b=QtGui.QInputDialog.getText(self,self.tr("Add Jabber ID"),self.tr("Enter Jabber ID:"), QtGui.QLineEdit.Normal, jid)
			jid=unicode(jid)
			if b==True and len(jid)!=0:
				try:
					isJid=jidT.JID(jid)
				except:
					isJid=None
				if isJid:
					QtGui.QListWidgetItem(jid,self.jids)
					break
			else:
				break

def makePreferences(main,parent,layout,form,row=1):
	var={}
	boxes={}
	tabs={}
	getBox=False
	getTab=False
	par=parent
	lay=layout
	keys=form.keys()
	if "__widget__" in keys:
		var['__widget__']=form['__widget__'](main,form,parent)
		layout.addWidget(var['__widget__'],row,0,1,2)
		return var,row+1
	if "__sort__" in keys:
		keys=form['__sort__']
	usingTabs=False
	for key in keys:
		if form[key].has_key("tab"):
			if not usingTabs:
				usingTabs=True
				tabWidget=QtGui.QTabWidget(parent)
				layout.addWidget(tabWidget,row,0,1,2)
				row+=1
			if not tabs.has_key(form[key]['tab']):
				tabs[form[key]['tab']]=[QtGui.QWidget(tabWidget)]
				tabs[form[key]['tab']].append(QtGui.QGridLayout(tabs[form[key]['tab']][0]))
				tabs[form[key]['tab']].append(0)
				tabWidget.addTab(tabs[form[key]['tab']][0],form[key]['tab'])
	row_=int(row)
	for key in keys:
		x=form[key]
		val=x['value']
		if x.has_key('tab'):
			par=tabs[x['tab']][0]
			lay=tabs[x['tab']][1]
			getTab=True
			row=tabs[x['tab']][2]
			tabs[x['tab']][2]+=1
		if x.has_key('groupbox'):
			if not boxes.has_key(x['groupbox']):
				if x.has_key('tab'):
					boxes[x['groupbox']]=[QtGui.QGroupBox(x['groupbox'],tabs[x['tab']][0])]
					boxes[x['groupbox']].append(QtGui.QGridLayout(boxes[x['groupbox']][0]))
					tabs[x['tab']][1].addWidget(boxes[x['groupbox']][0],row,0,1,2)
				else:
					boxes[x['groupbox']]=[QtGui.QGroupBox(x['groupbox'],parent)]
					boxes[x['groupbox']].append(QtGui.QGridLayout(boxes[x['groupbox']][0]))
					layout.addWidget(boxes[x['groupbox']][0],row,0,1,2)
					row+=1
				boxes[x['groupbox']].append(0)
				oldrow=int(row)
			boxes[x['groupbox']][2]+=1
			row=boxes[x['groupbox']][2]
			par=boxes[x['groupbox']][0]
			lay=boxes[x['groupbox']][1]
			getBox=True
		elif getBox:
			getBox=False
			if not usingTabs:
				row=int(oldrow)
				par=parent
				lay=layout
			#if not tabs.has_key(x['tab']):
				#tabs[x['tab']]=[QtGui.QGroupBox(x['groupbox'],parent)]
		if main.has_key(key):
			val=main[key]
			if key=="passwd":
				val=rot13.scramble(val)
		if x['type']=="text-single":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QLineEdit(par)
			widget.setText(unicode(val))
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
		elif x['type']=="custom":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			
			widget=x['widget'](par)
			widget.setWidgetValue(val)
			if not label:
				lay.addWidget(widget,row,0,1,2)
			else:
				lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
		elif x['type']=="directory":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=directoryWidget(par)
			widget.setText(unicode(val))
			chooser=QtGui.QPushButton("...")
			QtCore.QObject.connect(chooser,QtCore.SIGNAL("clicked()"),widget.getDirectory)
			l_=QtGui.QHBoxLayout()
			l_.addWidget(widget)
			l_.addWidget(chooser)
			lay.addLayout(l_,row,1)
			var[key]={'widget':widget,'type':x['type'],'widgets':[chooser,label]}
			row+=1
		elif x['type']=="jid-list":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=jidListWidget(par)
			if isinstance(val,list):
				for jid in val:
					QtGui.QListWidgetItem(unicode(jid),widget.jids)
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
		elif x['type']=="time-interval":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QTimeEdit(par)
			d=val.split(":")
			t=QtCore.QTime(int(d[0]),int(d[1]),int(d[2]))
			widget.setTime(t)
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
		elif x['type']=="number-spin":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QSpinBox(par)
			if x.has_key("min"):
				widget.setMinimum(int(x['min']))
			if x.has_key("max"):
				widget.setMaximum(int(x['max']))
			widget.setValue(int(val))
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
		elif x['type']=="fixed":
			label=QtGui.QLabel(par)
			label.setOpenExternalLinks(True)
			label.setWordWrap(True)
			label.setTextFormat(QtCore.Qt.RichText)
			policy=label.sizePolicy()
			policy.setHeightForWidth(True)
			policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
			label.setSizePolicy(policy)
			label.setText(unicode(val))
			lay.addWidget(label,row,0,1,2)
			#for d in x.elements():
				#if d.name == "desc":
					#widget.setToolTip(unicode(d))
			row+=1
		elif x['type']=="text-multi":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QTextEdit(par)
			#text=""
			#for child in x.elements():
				#if child.name == 'value':
					#text+=unicode(child)+"\n"
			widget.setText(unicode(val))
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			#for d in x.elements():
				#if d.name == "desc":
					#widget.setToolTip(unicode(d))
			row+=1
		elif x['type']=="boolean":
			try:
					ltext=x['label']
			except KeyError:
					ltext=""
			widget=QtGui.QCheckBox(ltext,par)
			#for child in x.elements():
				#if child.name == 'value':
			if unicode(val)=="0" or unicode(val).lower()=="false":
				widget.setChecked(False)
			elif unicode(val)=="1" or unicode(val).lower()=="true":
				widget.setChecked(True)
			if x.has_key('column'):
				if x['column']=='right':
					lay.addWidget(widget,row,1,1,1)
				else:
					lay.addWidget(widget,row,0,1,2)
			else:
				lay.addWidget(widget,row,0,1,2)
			var[key]={'widget':widget,'type':x['type']}
			#for d in x.elements():
				#if d.name == "desc":
					#widget.setToolTip(unicode(d))
			row+=1
		elif x['type']=="boolean-radio":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0,1,2)
			row+=1
			group=QtGui.QButtonGroup()
			for data,lab in x['options'].iteritems():
				widget=QtGui.QRadioButton(lab,par)
				widget.data=unicode(data)
				if unicode(val)==unicode(data):
					widget.setChecked(True)
				else:
					widget.setChecked(False)
				if x.has_key('column'):
					if x['column']=='right':
						lay.addWidget(widget,row,1,1,1)
					else:
						lay.addWidget(widget,row,0,1,2)
				else:
					lay.addWidget(widget,row,0,1,2)
				group.addButton(widget)
				row+=1
			var[key]={'widget':group,'type':x['type']}
		elif x['type']=="text-private":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QLineEdit(par)
			widget.setEchoMode(QtGui.QLineEdit.Password)
			#for child in x.elements():
				#if child.name == 'value':
			widget.setText(unicode(val))
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			#for d in x.elements():
				#if d.name == "desc":
					#widget.setToolTip(unicode(d))
			row+=1
		elif x['type']=="list-single":
			try:
				label=QtGui.QLabel(x['label'],par)
				label.setOpenExternalLinks(True)
				label.setWordWrap(True)
				label.setTextFormat(QtCore.Qt.RichText)
				policy=label.sizePolicy()
				policy.setHeightForWidth(True)
				policy.setVerticalPolicy(QtGui.QSizePolicy.Minimum)
				label.setSizePolicy(policy)
			except KeyError:
				label=None
			lay.addWidget(label,row,0)
			widget=QtGui.QComboBox(par)
			for iKey,iValue in x['items'].iteritems():
				widget.addItem(unicode(iKey),QtCore.QVariant(unicode(iValue)))
			if widget.findData(QtCore.QVariant(unicode(val)))!=None:
				widget.setCurrentIndex(widget.findData(QtCore.QVariant(unicode(val))))
			lay.addWidget(widget,row,1)
			var[key]={'widget':widget,'type':x['type'],"widgets":[label]}
			row+=1
			# TODO
			##<field var='userlist' type='list-single' label='Userlist on GG server'><value>get</value><option label='ignore'><value>ignore</value></option><option label='retrieve'><value>get</value></option></field>
			#try:
				#label=QtGui.QLabel(x['label'],parent)
			#except KeyError:
				#label=None
			#layout.addWidget(label,row,0)
			#widget=QtGui.QComboBox(parent)
			#default=""
			#for child in x.elements():
				#if child.name == 'value':
					#default=unicode(child)
				#elif child.name=="option":
					#for ch in child.elements():
						#if ch.name=="value":
							#if unicode(ch)==default:
								#widget.insertItem(0,unicode(child['label']),QtCore.QVariant(unicode(ch)))
							#else:
								#widget.addItem(child['label'], QtCore.QVariant(unicode(ch)))
			#widget.setCurrentIndex(0)
			#layout.addWidget(widget,row,1)
			#var[key]={'widget':widget,'type':x['type']}
			#for d in x.elements():
				#if d.name == "desc":
					#widget.setToolTip(unicode(d))
			row+=1
		if var.has_key(key):
			if x.has_key("tooltip"):
				var[key]['widget'].setToolTip(unicode(x['tooltip']))

	for tab in tabs.keys():
		lay=tabs[tab][1]
		lay.addItem(QtGui.QSpacerItem(0,10,QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Expanding))
		

	for key in keys:
		x=form[key]
		val=x['value']
		if main.has_key(key):
			val=main[key]
			if key=="passwd":
				val=rot13.scramble(val)
		if x.has_key("disabled") and var.has_key(key):
			var[key]['widget'].setDisabled(True)
		if x['type']=="boolean":
			if x.has_key("enable"):
				for w in x['enable']:
					widgets=[var[w]['widget']]
					if var[w].has_key("widgets"):
						widgets+=var[w]['widgets']
					for widget in widgets:
						QtCore.QObject.connect(var[key]['widget'],QtCore.SIGNAL("toggled (bool)"),widget.setEnabled)
						if unicode(val)=="0" or unicode(val).lower()=="false":
							widget.setEnabled(False)
						elif unicode(val)=="1" or unicode(val).lower()=="true":
							widget.setEnabled(True)
			if x.has_key("disable"):
				for w in x['disable']:
					widgets=[var[w]['widget']]
					if var[w].has_key("widgets"):
						widgets+=var[w]['widgets']
					for widget in widgets:
						QtCore.QObject.connect(var[key]['widget'],QtCore.SIGNAL("toggled (bool)"),widget.setDisabled)
						if unicode(val)=="0" or unicode(val).lower()=="false":
							widget.setDisabled(False)
						elif unicode(val)=="1" or unicode(val).lower()=="true":
							widget.setDisabled(True)
			if x.has_key("show"):
				for w in x['show']:
					widgets=[var[w]['widget']]
					if var[w].has_key("widgets"):
						widgets+=var[w]['widgets']
					for widget in widgets:
						QtCore.QObject.connect(var[key]['widget'],QtCore.SIGNAL("toggled (bool)"),widget.setVisible)
						if unicode(val)=="0" or unicode(val).lower()=="false":
							widget.setVisible(False)
						elif unicode(val)=="1" or unicode(val).lower()=="true":
							widget.setVisible(True)
			if x.has_key("hide"):
				for w in x['hide']:
					widgets=[var[w]['widget']]
					if var[w].has_key("widgets"):
						widgets+=var[w]['widgets']
					for widget in widgets:
						QtCore.QObject.connect(var[key]['widget'],QtCore.SIGNAL("toggled (bool)"),widget.setHidden)
						if unicode(val)=="0" or unicode(val).lower()=="false":
							widget.setHidden(False)
						elif unicode(val)=="1" or unicode(val).lower()=="true":
							widget.setHidden(True)


	if usingTabs:
		return var,row_
	else:
		return var,row
