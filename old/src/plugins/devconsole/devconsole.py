# -*- coding: utf-8 -*-
import sys,os,time, weakref
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui, QtWebKit
from twisted.python import log
import base64
import xml.dom.minidom
from twisted.words.xish.domish import Element
from pyxl import jid
import traceback
#from widgets.webkitchatwidget import searchWidget


template = u"""<html><head>
<style>
body {backround: black;}
div {
color: green;
background:black;
margin:  5px;
}
</style>
<script>

//Auto-scroll to bottom.  Use nearBottom to determine if a scrollToBottom is desired.
function nearBottom() {
		return ( (document.body.scrollTop+100) >= ( document.body.offsetHeight - ( window.innerHeight * 1.2 ) ) );
}
function scrollToBottom() {
		document.body.scrollTop = document.body.offsetHeight;
}

function appendMessage(text, tagy, id, timestamp, hidden) {
shouldScroll = nearBottom();
var hl = document.getElementById('hlavni');
var message = document.createElement('div');

var tags = document.createElement('tags');
tags.innerHTML = tagy;
tags.setAttribute('name','tags');
tags.setAttribute('msgId', id)
tags.style.display = 'none';

var msg = document.createElement('div');
msg.setAttribute('id', id)
msg.innerHTML = text;
msg.setAttribute('onClick','changeTab('+timestamp+')');
if (hidden == 1){msg.style.display = 'none';}

var stamp = document.createElement('span');
stamp.setAttribute('name','timestamp');
stamp.setAttribute('t',timestamp);
//stamp.setAttribute('onClick','changeTab('+timestamp+')');
//stamp.innerHTML = '*';
//stamp.style.display = 'none';

message.appendChild(tags);
message.appendChild(msg);
message.appendChild(stamp);
hl.appendChild(message);

if (shouldScroll) setTimeout("scrollToBottom()", 100);
};

function changeTab(timestamp){
consoleObject.changeTab();
consoleObject.scroll(timestamp);
}

function scrollToTimestamp(timestamp){
var seznam = document.getElementsByName('timestamp');
var cislo = parseInt(timestamp);
var vybrane = null;
var delta = -1;
for (var x=0;x<seznam.length;x++)
{
	var cur = parseInt(seznam[x].attributes.getNamedItem("t").value);
	var curDelta = Math.abs(cislo-cur);
	if ((delta == -1) || (curDelta<delta)){ delta = curDelta; vybrane = seznam[x];}
	}
//scrollToElement(vybrane);
document.body.scrollTop = vybrane.offsetTop;
}

function scrollToElement(theElement){

  var selectedPosX = 0;
  var selectedPosY = 0;

  while(theElement != null){
    selectedPosX += theElement.offsetLeft;
    selectedPosY += theElement.offsetTop;
    theElement = theElement.offsetParent;
  }
  }


function compareTags(tags1, tags2){
var l1 = tags1.length;
var l2 = tags2.length;
for (var x=0;x<tags1.length;x++){
	for (var y=0;y<tags2.length;y++){
		if (tags1[x] == tags2[y]){
			return 1
			}
		}
	}
}

function filterMessages(tags){
var tag = tags.split(' ');
var seznam = document.getElementsByName('tags');
var rozdelene;
for (var i=0;i<seznam.length;i++) {
//var tagy = seznam[i];
rozdelene = seznam[i].innerHTML.split(' ');
var ok = compareTags(tag, rozdelene);

var id = seznam[i].getAttribute('msgId');
var msg = document.getElementById(id);
if (ok == 1){
msg.style.display = 'block';
}
else {
msg.style.display = 'none';
}

}
}
</script>
</head>
<body><div id='hlavni'></div></body></html>"""

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['notify']={'type':'boolean','label':self.main.tr("Notify on error?"),'value':'False'}
		self.config['onOnLoad']={'type':'boolean','label':self.main.tr("Enabled consoles on startup"),'value':'False'}
		self.config['XMLaddTimestamps']={'type':'boolean','label':self.main.tr("Add timestamps to xml stanzas"),'value':'False'}
		self.config['historyMaxCount']={'type':'number-spin','label':self.main.tr("Max history entries"),'value':'50'}
		self.config['historySave']={'type':'boolean-radio','label':self.main.tr('History saving type'),'value':'one','options':{'one':self.main.tr('always after command input'),'close':self.main.tr('on jabbim close'),'never':self.main.tr('never')}}
		self.config['historyDataPy']={'type':'hidden','value':''}
		self.config['historyDataXML']={'type':'hidden','value':''}
		pyPreset=['#0. volna pozice, novy preset ulozite pomoci Ctrl+Shift+0\n',
			'#1. vypis features konkretniho kontaktu\nself.main.client.getFeaturesByJid(JID)',
			'#2. jid z retezce\nself.main.getJid(JID)',
			'#3. ziskani celeho jid i s nejprioritnejsi resource\nself.main.client.getHighestJid(JID)',
			'#4. ziskani kontaktu v rosteru\nself.main.client.getContactByJid(jid)',
			'#5. nacteni pluginu\nself.main.loadPlugin(\'plugin\');\nself.main.config[\'plugins\'].append(\'plugin\');',
			'#6. vyhozeni pluginu\nself.main.unloadPlugin(\'plugin\');\nself.main.config[\'plugins\'].remove(\'plugin\');',
			'#7. volna pozice, novy preset ulozite pomoci Ctrl+Shift+7',
			'#8. volna pozice, novy preset ulozite pomoci Ctrl+Shift+8',
			'#9. volna pozice, novy preset ulozite pomoci Ctrl+Shift+9']
		tempPreset=[]
		for i in range(10):
			tempPreset.append(base64.b64encode(pyPreset[i]));			
		self.config['presetDataPy']={'type':'hidden','value':tempPreset}
		xmlPreset=['#0. volna pozice, novy preset ulozite pomoci Ctrl+Shift+0\n',
			"<iq to='USER@DOMAIN' from='you@yourserver.tld'>\n<query xmlns=''>\n</iq>",
			"<message to='USER@DOMAIN' from='you@yourserver.tld'>\n<body>Body text</body>\n</message>",
			"<presence from='you@yourserver.tld'>\n<show>???</show>\n<status>???</status>\n</presence>",
			'#4. volna pozice, novy preset ulozite pomoci Ctrl+Shift+4',
			'#5. volna pozice, novy preset ulozite pomoci Ctrl+Shift+5',
			'#6. volna pozice, novy preset ulozite pomoci Ctrl+Shift+6',
			'#7. volna pozice, novy preset ulozite pomoci Ctrl+Shift+7',
			'#8. volna pozice, novy preset ulozite pomoci Ctrl+Shift+8',
			'#9. volna pozice, novy preset ulozite pomoci Ctrl+Shift+9']
		tempPreset=[]
		for i in range(10):
			tempPreset.append(base64.b64encode(xmlPreset[i]));			

		self.config['presetDataXML']={'type':'hidden','value':tempPreset}		
		self.config['__sort__']=['notify','onOnLoad','XMLaddTimestamps','historyMaxCount','historySave','historyDataXML','historyDataPy']


class Console(QtCore.QObject):
	def __init__(self,plugin, mytab):
		QtCore.QObject.__init__(self)
		self.plugin = plugin
		self.mytab = mytab

	@QtCore.pyqtSignature("")
	def changeTab(self):
		if self.mytab == 'xml':
			self.plugin.setTabShell()
		elif self.mytab == 'log':
			self.plugin.setTabXML()
			
	@QtCore.pyqtSignature("QString")
	def scroll(self, timestamp):
		if self.mytab == 'xml':
			self.plugin.window.ui.pythonOutput.page().mainFrame().evaluateJavaScript('scrollToTimestamp("%s")'%timestamp)
		elif self.mytab == 'log':
		    self.plugin.window.ui.xmlOutput.page().mainFrame().evaluateJavaScript('scrollToTimestamp("%s")'%timestamp)
			
		

		
class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'devconsole'
		self.installTranslator()
		self.description = self.tr('Extra debug window')
		self.author = "Jiri 'Sef' Gabrys, Ondra 'triak' Kunc"
		self.name = self.tr('DevConsoles Plugin')
		self.version = '0.065'
		self.category = ['log', 'misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.historyPy = []
		self.historyXML = []
		self.historyPyPosition=-1;
		self.historyXMLPosition=-1;
		self.configDialog=config(self)
		self.id = 1
		if main:
			self.loadConfig()
			self.loadHistory()
			self.window = self.loadWindow("%s/devconsole_ui.py" % self.pluginDir)
			self.window.setWindowIcon(self.main.windowIcon())
			self.window.ui.tabWidget.setTabIcon(0,QtGui.QIcon("%s/xml.png" % self.pluginDir))
			self.window.ui.tabWidget.setTabIcon(1,QtGui.QIcon("%s/python.png" % self.pluginDir))
			self.log = False
			self.registerHandler('onXmlEvent',self.onXml)
			self.registerHandler('on_element', self.on_element)
			self.window.ui.xmlOutput.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
			self.window.ui.xmlOutput.setHtml(template)
			self.window.ui.pythonOutput.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
			self.window.ui.pythonOutput.setHtml(template)
##			self.window.ui.pythonSearchWidget=searchWidget(self.window.ui.pythonOutput,self.window)
##			self.window._5.addWidget(self.ui.pythonSearchWidget)
			self.xmlConsoleObject = Console(self, 'xml')
			self.pythonConsoleObject = Console(self, 'log')

		#both tabs
			#Ctrl+Enter(Return) executes command list
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Return),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.ctrlEnter)
			#Ctrl-E toggles enable/disable log output
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_E | QtCore.Qt.ControlModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.togglePythonEnabled)
			
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_S | QtCore.Qt.AltModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.setTabShell)
			
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_X | QtCore.Qt.AltModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.setTabXML)
			
			#Ctrl-R to erase log
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_R | QtCore.Qt.ControlModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.clearLog)
			#Ctrl+Up lists history to past
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Up | QtCore.Qt.ControlModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.historyBackward)
			#Ctrl+Down lists history to recently executed
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Down | QtCore.Qt.ControlModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.historyForward)
		#xml console
			QtCore.QObject.connect(self.window.ui.xmlSendButton,QtCore.SIGNAL("clicked()"),self.send)
			QtCore.QObject.connect(self.window.ui.xmlMessagePreset,QtCore.SIGNAL("clicked()"),self.message)
			QtCore.QObject.connect(self.window.ui.xmlPresencePreset,QtCore.SIGNAL("clicked()"),self.presence)
			QtCore.QObject.connect(self.window.ui.xmlIqPreset,QtCore.SIGNAL("clicked()"),self.iq)
			QtCore.QObject.connect(self.window.ui.xmlClearButton,QtCore.SIGNAL("clicked()"),self.clearLog)
			QtCore.QObject.connect(self.window.ui.xmlOutput,QtCore.SIGNAL("linkClicked ( const QUrl &)"),self.webkitLinkClicked)
			QtCore.QObject.connect(self.window.ui.xmlFilter,QtCore.SIGNAL("returnPressed()"),self.xmlFilterChanged)
			QtCore.QObject.connect(self.window.ui.xmlOutput.page().mainFrame(),QtCore.SIGNAL("javaScriptWindowObjectCleared ()"),self.xmlCleared)
		#python console
			QtCore.QObject.connect(self.window.ui.pythonEnableBox, QtCore.SIGNAL("stateChanged(int)"),self.pythonEnableToggled)
			QtCore.QObject.connect(self.window.ui.pythonClearButton, QtCore.SIGNAL("clicked()"),self.clearLog)
			QtCore.QObject.connect(self.window.ui.pythonExecuteButton, QtCore.SIGNAL("clicked()"),self.execute)
			QtCore.QObject.connect(self.window.ui.pythonOutput.page().mainFrame(),QtCore.SIGNAL("javaScriptWindowObjectCleared ()"),self.pythonCleared)
			#Ctrl+Shift+Up inserts previous command from history to the top of current shell
			short=QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Up | QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier),self.window)
			QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.shellAppendPrevious)
			#preset save & load
			def gen_preset(n, load):
				if load:
					def call_it(): self.loadPreset(n)
				else:
					def call_it(): self.savePreset(n)
				return call_it
			keys = [QtCore.Qt.Key_0, QtCore.Qt.Key_1, QtCore.Qt.Key_2, QtCore.Qt.Key_3, QtCore.Qt.Key_4,
				QtCore.Qt.Key_5, QtCore.Qt.Key_6, QtCore.Qt.Key_7, QtCore.Qt.Key_8, QtCore.Qt.Key_9]
			for i in range(len(keys)):
				short=QtGui.QShortcut(QtGui.QKeySequence(keys[i] | QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier),self.window)
				QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"), gen_preset(i, False))
				short=QtGui.QShortcut(QtGui.QKeySequence(keys[i] | QtCore.Qt.ControlModifier),self.window)
				QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"), gen_preset(i, True))
			if self.config['onOnLoad']=='True':
				self.window.ui.xmlEnableBox.setChecked(True);
				self.window.ui.pythonEnableBox.setChecked(True);
		else:
			self.loadConfig(homedir)
	
	def buildMainWindowMenu(self):
		menu=self.mainWindowMenu()
		menu.addAction("Show console",self.showSlot)
	
	def buildMainWindowToolBar(self):
		self.toolBarButton = self.mainWindowToolBarAction(QtGui.QIcon("%s/icon.png" % self.pluginDir),"",self.showSlot)
	
	def on_remove(self):
		if self.config['historySave']=='close':
			self.saveHistory();
		try:
			log.removeObserver(self.observer)
		except ValueError:
			pass # fixes problem with removal of unregistered observer
	
	def showSlot(self):
		self.window.show()
	def togglePythonEnabled(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.window.ui.pythonEnableBox.setChecked(not self.window.ui.pythonEnableBox.isChecked())
		else:
			self.window.ui.xmlEnableBox.setChecked(not self.window.ui.xmlEnableBox.isChecked())
		
	def pythonEnableToggled(self, state):
		if (not self.log) and self.window.ui.pythonEnableBox.isChecked():
			self.log = True
			log.addObserver(self.observer)
			#self.window.ui.pythonOutput.append('Log started')
			#self.window.ui.pythonOutput.page().mainFrame().evaluateJavaScript('appendMessage("Log started.");')
		else:
			self.log = False
			log.removeObserver(self.observer)
	
	def observer(self, msg, fromThread=False):
		if not fromThread:
			self.main.reactor.callFromThread(self.observer,msg,True)
			return
		#self.window.ui.pythonOutput.append('[%s] %s' %(time.strftime('%X'), unicode(' '.join(msg['message']).replace("<","&lt;").replace(">","&gt;"))))
		self.addMessage('[%s] %s' %(time.strftime('%X'), unicode(' '.join(msg['message']), 'utf8')))
		if msg['isError'] and self.config['notify'] == 'True':
			self.main.tray.showMessage(self.main.tr("Log"),unicode(' '.join(msg['message']), 'utf8'), QtGui.QSystemTrayIcon.Warning, 2000)
	
	def clearLog(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.window.ui.pythonOutput.setHtml(template)
		else:
			self.window.ui.xmlOutput.setHtml(template)
	def ctrlEnter(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.execute()
		else:
			self.send()
	
	def execute(self):
		code = unicode(self.window.ui.pythonInput.toPlainText ())
		#self.window.ui.pythonOutput.append('>>> '+self.window.ui.pythonInput.toPlainText ())
		self.addMessage('>>> '+self.window.ui.pythonInput.toPlainText())
		self.window.ui.pythonOutput.page().mainFrame().evaluateJavaScript('scrollToBottom()')
		self.historyPy.insert(0,code)
		self.historyPy=self.historyPy[0:long(self.config['historyMaxCount'])]
		self.historyPyPosition=-1;
		if self.config['historySave']=='one':
			self.saveHistory()
		self.window.ui.pythonInput.setText('')
		try:
			exec(code)
		except:
			print traceback.format_exc()

	def saveHistory(self):
		tmpHistory=[];
		for historyItem in self.historyPy:
			tmpHistory.append(base64.b64encode(historyItem));
		self.config['historyDataPy']=tmpHistory
		tmpHistory=[];
		for historyItem in self.historyXML:
			tmpHistory.append(base64.b64encode(historyItem));
		self.config['historyDataXML']=tmpHistory
		self.config.write()
	def loadHistory(self):
		self.historyPy=[];
		self.historyXML=[];
		tmpHistory=self.config['historyDataPy'];
		for historyItem in tmpHistory:
			self.historyPy.append(base64.b64decode(historyItem))
		tmpHistory=self.config['historyDataXML'];
		for historyItem in tmpHistory:
			self.historyXML.append(base64.b64decode(historyItem))
	def historyForward(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.historyPyPosition-=1;
			if self.historyPyPosition<0:
				self.historyPyPosition=-1;
				self.window.ui.pythonInput.setText('')
			else:
				self.window.ui.pythonInput.setText(self.historyPy[self.historyPyPosition])
		else:
			self.historyXMLPosition-=1;
			if self.historyXMLPosition<0:
				self.historyXMLPosition=-1;
				self.window.ui.xmlInput.setText('')
			else:
				self.window.ui.xmlInput.setText(self.historyXML[self.historyXMLPosition])
			
	def shellAppendPrevious(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.historyPyPosition+=1;
			if self.historyPyPosition>(len(self.historyPy)-1):
				self.historyPyPosition=len(self.historyPy)-1;
			else:
				self.window.ui.pythonInput.setText("%s\n%s" % (self.historyPy[self.historyPyPosition],self.window.ui.pythonInput.toPlainText()))
		else:
			self.historyXMLPosition+=1;
			if self.historyXMLPosition>(len(self.historyXML)-1):
				self.historyXMLPosition=len(self.historyXML)-1;
			else:
				self.window.ui.xmlInput.setText("%s\n%s" % (self.historyXML[self.historyXMLPosition],self.window.ui.xmlInput.toPlainText()))	

	def historyBackward(self):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.historyPyPosition+=1;
			if self.historyPyPosition>=len(self.historyPy):
				self.historyPyPosiition=len(self.historyPy);
				self.window.ui.pythonInput.setText(self.tr('print \'History END\''))
			else:
				self.window.ui.pythonInput.setText(self.historyPy[self.historyPyPosition])
		else:
			self.historyXMLPosition+=1;
			if self.historyXMLPosition>=len(self.historyXML):
				self.historyXMLPosition=len(self.historyXML);
				self.window.ui.xmlInput.setText(self.tr("<message>------HISTORY-END------</message>"))
			else:
				self.window.ui.xmlInput.setText(self.historyXML[self.historyXMLPosition])
	def savePreset(self,order):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.config['presetDataPy'][order]=base64.b64encode(unicode(self.window.ui.pythonInput.toPlainText ()))
			self.config.write();
		else:
			self.config['presetDataXML'][order]=base64.b64encode(unicode(self.window.ui.xmlInput.toPlainText ()))
			self.config.write();

	def loadPreset(self,order):
		if self.window.ui.tabWidget.currentIndex()==1:
			self.window.ui.pythonInput.setText(base64.b64decode(self.config['presetDataPy'][order]))
		else:
			self.window.ui.xmlInput.setText(base64.b64decode(self.config['presetDataXML'][order]))
		
	def iq(self):
		self.window.ui.xmlInput.setText("<iq to='USER@DOMAIN' from='"+self.main.client.jid.full()+"'>\n<query xmlns=''>\n</iq>")

	def message(self):
		self.window.ui.xmlInput.setText("<message to='USER@DOMAIN' from='"+self.main.client.jid.full()+"'>\n<body>Body text</body>\n</message>")

	def presence(self):
		self.window.ui.xmlInput.setText("<presence from='"+self.main.client.jid.full()+"'>\n<show>???</show>\n<status>???</status>\n</presence>")

	def send(self):
		text=unicode(self.window.ui.xmlInput.toPlainText())
		self.historyXML.insert(0,text)
		self.historyXML=self.historyXML[0:long(self.config['historyMaxCount'])]
		self.historyXMLPosition=-1;
#		try:
		xmlObj=xml.dom.minidom.parseString(text)
		iqelems=xmlObj.getElementsByTagName('iq')
		if iqelems:
			id=iqelems[0].getAttribute('id');
			if not id:
				id = "H_%d" % Element._idCounter
				Element._idCounter = Element._idCounter + 1
			iqelems[0].setAttribute('id',id)
			self.main.client.disp(id)
#		text=xmlObj.toxml()
#		text=text.replace('<?xml version="1.0" ?>\n','');
		for i in xmlObj.childNodes:
			self.main.client.xmlstream.send(i.toxml());
#		except Exception,e:
#			traceback.print_exc();
		self.window.ui.xmlInput.setText("")
		if self.config['historySave']=='one':
			self.saveHistory()
	
	def webkitLinkClicked():
		log.msg('link clicked')
	
	def onXml(self,xml):
		if self.window.ui.xmlEnableBox.isChecked():
			if self.config['XMLaddTimestamps']=='True':
				text=time.strftime("[%H:%M:%S]")+' ';
			else:
				text='';
			text=text+unicode(xml)
			text = text.replace('<','&lt;').replace('>','&gt;')
			tagy = ''
			if not xml.startswith('BOOT'):
				return
			tagy = 'boot '
			self.addMessage(text, tagy, 'xml')
			
	def writeOut(self, typ = 'xml'):
		if typ == 'xml':
			fp = open('devtest.html', 'w')
			fp.write(unicode(self.window.ui.xmlOutput.page().mainFrame().toHtml()).encode('utf8'))
			fp.close()
		elif typ=='log':
			fp = open('devtest.html', 'w')
			fp.write(unicode(self.window.ui.pythonOutput.page().mainFrame().toHtml()).encode('utf8'))
			fp.close()


	def xmlFilterChanged(self):
		log.msg('trying to filter %s'%(unicode(self.window.ui.xmlFilter.text())))
		self.window.ui.xmlOutput.page().mainFrame().evaluateJavaScript('filterMessages("%s")'%(unicode(self.window.ui.xmlFilter.text())))
		
	def compareTags(self, tags1, tags2):
		t1 = tags1.split(' ')
		t2 = tags2.split(' ')
		if len(t1) == 0 or len(t2) == 0:
			return False
		for tag in t1:
			if tag in t2:
				return True
		return False
		

	def addMessage(self, text, tagy='', typ='log'):
		stamp = unicode(time.time())
		if len(unicode(self.window.ui.xmlFilter.text())) == 0:
			hidden = '0'
		elif self.compareTags(tagy, unicode(self.window.ui.xmlFilter.text())):
			hidden = '0'
		else:
			hidden = '1'
		

		text = text.replace('"', '&apos;').replace("'", '&apos;').replace('<','&lt;').replace('>','&gt;').replace('\n', '</br>')

		if typ == 'xml':
			self.window.ui.xmlOutput.page().mainFrame().evaluateJavaScript('appendMessage("%s", "%s", "%s", "%s", %s);'%(text, tagy, self.addNextId(), stamp, hidden))
		elif typ == 'log':
			self.window.ui.pythonOutput.page().mainFrame().evaluateJavaScript('appendMessage("%s", "", "", "%s", %s);'%(text, stamp, hidden))
		else:
			raise TypeError

	def on_element(self, el):
		if self.window.ui.xmlEnableBox.isChecked():
			if type(el) == unicode:
				#we received input from xml console
				#just display it without parsing
				log.msg('got unicode element')
				self.addMessage(el, typ='xml')
				return
			
			typ = ''
			tagy = ''
			if not el.hasAttribute('from'):
				frm = self.main.client.jid
			else:
				frm = jid.JID(el['from'])
			if not el.hasAttribute('to'):
				to = jid.JID(self.main.client.jid.host)
			else:
				to = jid.JID(el['to'])


			if frm.full() == self.main.client.jid.full() or frm.userhost() in self.main.client.groupchats.keys():
				tagy += 'from '
				typ = 'from'
			else:
				tagy += 'to '
				typ = 'to'
			tagy += frm.userhost() + ' '
			tagy += to.userhost() + ' '
			tagy += unicode(frm.user) + ' '
			tagy += unicode(to.user) + ' '

			tagy += el.name + ' '
			if el.name == 'iq' and el['type']!= 'result' :
				try:
					tagy += el.firstChildElement().defaultUri + ' '
				except:
					log.msg('unknown iq')
					log.msg(el.toXml())
					
			self.addMessage(el.toXml(), tagy, 'xml')

	def setTabXML(self):
		self.window.ui.tabWidget.setCurrentIndex(0);
	
	def setTabShell(self):
		self.window.ui.tabWidget.setCurrentIndex(1);
		
	def addNextId(self):
		self.id += 1
		return str(self.id)
	
	def xmlCleared(self):
		self.window.ui.xmlOutput.page().mainFrame().addToJavaScriptWindowObject("consoleObject",self.xmlConsoleObject)

	def pythonCleared(self):
		self.window.ui.pythonOutput.page().mainFrame().addToJavaScriptWindowObject("consoleObject",self.pythonConsoleObject)
