#-*-coding:UTF-8-*-

from PyQt4 import QtGui, QtCore
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.python import log
import dataforms
from commands_ui import Ui_Dialog
import weakref

class CommandsDialog(QtGui.QMainWindow):
	def __init__(self, cmds, parent = None):
		if isinstance(parent,weakref.ref):
			parent=parent()
			
		QtGui.QMainWindow.__init__(self, parent)
		#self.setModal(False)
		self.cmds = cmds
		self.ui = Ui_Dialog()
		self.ui.setupUi(self)
		
		self.group = QtGui.QButtonGroup(self)
		self.tbg = QtGui.QButtonGroup(self)

		QtCore.QObject.connect(self.group,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.buttonClicked) 
		QtCore.QObject.connect(self.tbg,QtCore.SIGNAL("buttonClicked ( QAbstractButton * )"),self.tbgButtonClicked) 
		QtCore.QObject.connect(self.ui.menuButton,QtCore.SIGNAL("clicked ()"),self.exClicked) 
		#QtCore.QObject.connect(self.ui.next,QtCore.SIGNAL("clicked ()"),self.cmds.submit)
		#QtCore.QObject.connect(self.ui.previous,QtCore.SIGNAL("clicked ()"),self.cmds.submit) 
		#QtCore.QObject.connect(self.ui.complete,QtCore.SIGNAL("clicked ()"),self.cmds.submit) 

		self.scroll=QtGui.QScrollArea(self)
		self.widget=QtGui.QWidget()
		self.ui.glayout=QtGui.QGridLayout(self.widget)
		self.scroll.setWidget(self.widget)
		self.scroll.setWidgetResizable(True)
		self.ui.vboxlayout.addWidget(self.scroll)

		self.ui.next.hide()
		self.ui.next.action = "next"
		self.tbg.addButton(self.ui.next)
	
		self.ui.previous.hide()
		self.ui.previous.action = "prev"
		self.tbg.addButton(self.ui.previous)

		self.ui.complete.hide()
		self.ui.complete.action = "complete"
		self.tbg.addButton(self.ui.complete)
		
		self.ui.cancel.hide()
		self.ui.cancel.action = "cancel"
		self.tbg.addButton(self.ui.cancel)

		self.ui.close.hide()
		self.ui.label_2.hide()
		QtCore.QObject.connect(self.ui.close,QtCore.SIGNAL("clicked ()"),self.reject)

	def _reset(self): 
		self.ui.label.setText(u"")
		#for button in self.group.buttons():
			#try:
				#self.ui.gridlayout2.removeWidget(button)
				#button.setParent(None)
			#except:
				#pass
		for i in range(self.ui.glayout.count()):
			item=self.ui.glayout.itemAt(0)
			if item.widget():
				item.widget().setParent(None)
			else:
				self.ui.glayout.removeItem(item)
		
		#self.ui.gridlayout.removeItem(self.ui.gridlayout2)
		#self.ui.gridlayout2.deleteLater
		#self.ui.gridlayout2 = QtGui.QGridLayout()
		#self.ui.gridlayout2.setObjectName("gridlayout2")
		#self.ui.gridlayout.addLayout(self.ui.gridlayout2,3,0,1,1)

		self.ui.next.hide()
		self.ui.previous.hide()
		self.ui.complete.hide()
		self.ui.cancel.hide()
		self.ui.close.hide()
		self.ui.label_2.hide()
		#if self.cmds.var:
		#	for var in self.cmds.var.values():
		#		self.ui.gridlayout2.removeWidget(var["widget"])


	def buttonClicked(self, button):
		self.cmds.execCommand(button.node, unicode(button.text()), button.jid)

	def tbgButtonClicked(self, button):
		self.cmds.submit(button.action)
	
	def exClicked(self):
		self._reset()
		self.cmds.requestCommandsList()

	def reject(self):
		self.close()
		

class Commands:
	def __init__(self, main, jid, action = None, node = None, getItems=True):
		if isinstance(main,weakref.ref):
			self.main	= main
		else:
			self.main	= weakref.ref(main)
		self.jid	= unicode(jid)
		self.dialog	= CommandsDialog(self,self.main)
		self.sessionid	= None
		self.node	= node
		self.form	= None
		self.name 	= None
		self.var = self.row = None
		self.action = action
		self.submenu = None
		if getItems==True:
			self.requestCommandsList()

	def requestCommandsList(self):
		iq		= IQ(self.main().client.xmlstream, "get")
		iq["xml:lang"] = self.main().client.xmlLang
		iq["to"]	= self.jid
		query		= iq.addElement("query", "http://jabber.org/protocol/disco#items")
		query.attributes["node"] = "http://jabber.org/protocol/commands"
		d		= iq.send()
		d.addCallback(self._commandsListRecieved).addErrback(self._errorRecieved)
		self.main().client.disp(iq["id"])
		log.msg("Sending request for Ad-Hoc Commands list")

	def _commandsListRecieved(self, el):
		log.msg("Ad-Hoc commands list recieved")
		#if self.submenu != None:
			#return
		query	= el.firstChildElement()
		commands = []
		for item in query.elements():
			if item.name != "item":
				continue
			commands.append(item.attributes)

		c = 0
		self.submenu = QtGui.QMenu()
		mainWindow=self.main()
		if unicode(self.jid) in self.main().config['commandsInTray']:
			action=self.submenu.addAction(mainWindow.tr("Remove this menu from Tray"))
			action.setObjectName("remove_from_tray")
		else:
			action=self.submenu.addAction(mainWindow.tr("Add this menu to Tray"))
			action.setObjectName("add_to_tray")
		self.submenu.addSeparator()

		for command in commands:
			action=self.submenu.addAction(command["name"])
			action.setObjectName("ad_hoc_command")
			action.setData(QtCore.QVariant(QtCore.QStringList([command['node'], command['name']])))

			button = QtGui.QPushButton(self.dialog)
			button.setText(unicode(command["name"]))
			#button.setObjectName(unicode(command["node"])) # ? + jid
			button.node = unicode(command["node"])
			button.jid = unicode(command["jid"])
			self.dialog.group.addButton(button)
			self.dialog.ui.glayout.addWidget(button, c, 0)
			c += 1
			spacerItem = QtGui.QSpacerItem(40,20,QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
			self.dialog.ui.glayout.addItem(spacerItem,c,0)


		if len(commands) == 0 :
			if self.action:
				self.action.setEnabled(False)
			self.dialog.ui.label.setText(self.main().tr("Sorry. No extra actions available."))
			self.dialog.ui.close.show()
			self.dialog.ui.line.hide()
		else:
			if self.action:
				self.action.setMenu(self.submenu)
			self.submenu.connect(self.submenu, QtCore.SIGNAL("triggered ( QAction * )"),self.execute)
			self.dialog.ui.label.setText(self.main().tr("Choose action to execute."))

	def execute(self, action):
		cmd = action.objectName()
		if cmd == "ad_hoc_command":
			self.dialog.show()
			data = action.data().toList()
			self.execCommand(data[0].toString(), data[1].toString())
		elif cmd == "add_to_tray":
			self.main().config['commandsInTray'].append(unicode(self.jid))
			self.main().buildTrayMenu()
		elif cmd == "remove_from_tray":
			self.main().config['commandsInTray'].remove(unicode(self.jid))
			self.main().buildTrayMenu()

	def execCommand(self, node, name, jid = None):
		if jid == None:
			jid = self.jid
		self.jid = jid
		self.node = node
		self.name = name
		iq = IQ(self.main().client.xmlstream, "set")
		iq["xml:lang"] = self.main().client.xmlLang
		iq["to"] = jid
		command = iq.addElement("command")
		command.attributes = {"node":node, "xmlns": "http://jabber.org/protocol/commands", "action":"execute"}
		d=iq.send()
		d.addCallback(self._formRecieved).addErrback(self._errorRecieved)
		self.main().client.disp(iq["id"])
		log.msg("Executing command %s." % node)
	
	def _errorRecieved(self, err):
		mainWindow=self.main()
		el=err.value.getElement()
		code=None
		if el.hasAttribute('code'):
			code=int(el['code'])
		if self.action:
			self.action.setEnabled(False)
		self.dialog._reset()
		self.dialog.ui.close.show()
		self.dialog.ui.label.setText("<b>%s</b>" % mainWindow.tr("Error"))
		self.dialog.ui.label_2.show()
		if code==401:
			self.dialog.ui.label_2.setText(mainWindow.tr("You don't have authorization for executing this command."))
		else:
			self.dialog.ui.label_2.setText(unicode(err.value))
		self.dialog.ui.line.hide()

	def _formRecieved(self, el):
		log.msg(`el`+str(dir(el)))
		command = el.firstChildElement()
		self.sessionid = command.getAttribute('sessionid')
		self.dialog._reset()
		actions =[]
		title = unicode(self.dialog.windowTitle()) + " - " + self.name
		if command["status"] == "completed":
			self.dialog.ui.label.setText(self.main().tr("Completed!"))
			log.msg("Completed command with sessionid %s." % self.sessionid)
		elif command["status"] == "executing":
#			self.dialog.ui.label.setText(self.main().tr("In progress."))
			log.msg("Executing command with sessionid %s." % self.sessionid)
		elif command["status"] == "canceled":
#			self.dialog.ui.label.setText("Canceled.")
			log.msg("Canceled command with sessionid %s." % self.sessionid)
		for element in command.elements():
			if element.name == "actions":
				for x in element.elements():
					actions.append(x.name)
			if element.name == "x":
				self.form = element
				for elem in element.elements():
					if elem.name == "title":
						title = unicode(elem)
					if elem.name == 'instructions':
						self.dialog.ui.label.setText(unicode(elem))
				if command["status"] == "completed":
					self.dialog.ui.close.show()
					self.var, self.row = dataforms.makeDataForm(
							self.dialog,
							self.dialog.ui.glayout,
							element
							)

				elif command["status"] == "executing":
					self.dialog.ui.cancel.show()
					self.var, self.row = dataforms.makeDataForm(
							self.dialog,
							self.dialog.ui.glayout,
							element
							)

				elif command["status"] == "canceled":
					self.dialog.ui.close.show()
					self.dialog.ui.line.hide()
					self.var, self.row = dataforms.makeDataForm(
							self.dialog,
							self.dialog.ui.glayout,
							element
							)
			if element.name == "note":
				if element["type"] == "error":
					s = self.main().tr("Error")
				elif element["type"] == "warn":
					s = self.main().tr("Warning")
				else:
					s = self.main().tr("Info")
				self.dialog.ui.label_2.show()
				self.dialog.ui.label_2.setText("<b>%s</b>: " % s +unicode(element))
				self.dialog.ui.close.show()
		if actions ==[] and command["status"] == "executing":
			actions = ["complete"]
		for a in actions:
			if a == "prev":
				self.dialog.ui.previous.show()
			if a == "next":
				self.dialog.ui.next.show()
			if a == "complete":
				self.dialog.ui.complete.show()
		spacerItem = QtGui.QSpacerItem(40,20,QtGui.QSizePolicy.Minimum,QtGui.QSizePolicy.Expanding)
		self.dialog.ui.glayout.addItem(spacerItem,self.row,0)
		self.dialog.setWindowTitle(title)


	def submit(self,action):
		iq=IQ(self.main().client.xmlstream, "set")
		iq["xml:lang"] = self.main().client.xmlLang
		iq["to"] = self.jid
		command=iq.addElement("command")
		command.attributes = {"node":self.node, "xmlns": "http://jabber.org/protocol/commands", "sessionid":self.sessionid,"action":action}
		if action != "cancel":
			form = dataforms.sendDataForm(self.main(), self.jid, self.form, self.var, None)
			command.addChild(form)
		else:
			self.dialog.reject()
		d=iq.send()
		d.addCallback(self._formRecieved).addErrback(self._errorRecieved)
		self.main().client.disp(iq["id"])
