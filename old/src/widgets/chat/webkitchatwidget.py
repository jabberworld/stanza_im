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
from PyQt4 import QtCore, QtGui, QtWebKit
import os, time
import weakref
from twisted.python import log
from include.constants import RESOURCEPATH

class searchWidget(QtGui.QWidget):
	def __init__(self,webkit,parent=None):
		QtGui.QWidget.__init__(self,parent)
		self.webkit=weakref.ref(webkit)
		
		l=QtGui.QHBoxLayout(self)

		label=QtGui.QLabel(self.tr("Search:"))
		l.addWidget(label)

		self.searchText=QtGui.QLineEdit(self)
		l.addWidget(self.searchText)
		
		self.closeButton=QtGui.QPushButton(QtGui.QIcon(RESOURCEPATH+"images/icons/close.png"),"",self)
		l.addWidget(self.closeButton)
		
		QtCore.QObject.connect(self.searchText, QtCore.SIGNAL("returnPressed () "),self.searchTextFinished)
		QtCore.QObject.connect(self.closeButton, QtCore.SIGNAL("clicked () "),self.hideMe)

		short=QtGui.QShortcut("escape",self.searchText)
		QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.hideMe)

		self.hide()
		short=QtGui.QShortcut("ctrl+f",webkit)
		QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),self.showMe)
		short=QtGui.QShortcut("ctrl+c",parent)
		QtCore.QObject.connect(short, QtCore.SIGNAL("activated ()"),webkit.copySelectedText)

	def showMe(self):
		self.show()
		self.searchText.selectAll()
		self.searchText.setFocus(QtCore.Qt.MouseFocusReason)

	def hideMe(self):
		self.hide()

	def searchTextFinished(self):
		self.find(unicode(self.searchText.text()))

	def find(self,text,flags=QtWebKit.QWebPage.FindWrapsAroundDocument):
	    self.webkit().findText(text,flags)


class message(QtCore.QObject):
	def __init__(self,message):
		QtCore.QObject.__init__(self)
		self.message=[]
		self.messages=[]
		self.messageCache=[]
		self.historyMessages=[]
		self.ft={}
		self.scr=1
		self.src={}
		self.setObjectName("messageObject")
		self.handlers={}

	def addHandler(self,name,fc,data=[]):
		self.handlers[name]=[fc,data]

	@QtCore.pyqtSignature("QString")
	def removeHandler(self,name):
		if self.handlers.has_key(name):
			del self.handlers[name]

	@QtCore.pyqtSignature("",result="QStringList")
	def getHandlers(self):
		return QtCore.QStringList(self.handlers.keys())

	@QtCore.pyqtSignature("",result="QString")
	def getName(self):
		if len(self.src.keys())!=0:
			r=unicode(self.src.keys()[0])
			return r
		else:
			return ""

	@QtCore.pyqtSignature("QString",result="QString")
	def getSrc(self,sid):
		try:
			r=unicode(self.src[unicode(sid)])
		except:
			log.err('can\'t find src for '+sid)
			return ''
		#r=r"file:///c:\users\hanzz\desktop\svn/emoticons/default/smile16.png"
		return r


	@QtCore.pyqtSignature("QString")
	def handlerReady(self,name):
		name = unicode(name)
		self.handlers[name][0](*self.handlers[name][1])
		del self.handlers[name]

	@QtCore.pyqtSignature("QString")
	def reloaded(self,sid):
		del self.src[unicode(sid)]

	@QtCore.pyqtSignature("QString")
	def acceptFT(self,sid):
		self.ft[unicode(sid)].accept()

	@QtCore.pyqtSignature("QString")
	def rejectFT(self,sid):
		self.ft[unicode(sid)].reject()

	@QtCore.pyqtSignature("",result="int")
	def messageDirection(self):
		if len(self.messageCache)!=0:
			ret=self.messageCache[-1][0]
			return ret
		return -1

	@QtCore.pyqtSignature("",result="QString")
	def msg(self):
		if len(self.messageCache)!=0:
			ret=self.messageCache.pop()[1]
			#print "RET",[ret]
			return ret
		return ""

	@QtCore.pyqtSignature("",result="int")
	def historyMessageDirection(self):
		if len(self.historyMessages)!=0:
			ret=self.historyMessages[-1][0]
			print "RET",ret
			return ret
		return -1


	@QtCore.pyqtSignature("",result="QString")
	def historyMsg(self):
		if len(self.historyMessages)!=0:
			ret=self.historyMessages.pop()[1]
			return ret
		return ""

	
	@QtCore.pyqtSignature("int",result="QString")
	def msg_(self,i):
		return self.messages[i]
	
	@QtCore.pyqtSignature("",result="int")
	def scroll(self):
		return self.scr

	@QtCore.pyqtSignature("")
	def ready(self):
		#self.emit(QtCore.SIGNAL("ready()"))
		#print "READY!"
		#self.main.client.reactor.callLater(1,self.main.messageObjectReady)
		#self.main.messageObjectReady()
		pass

	@QtCore.pyqtSignature("QString")
	def log(self,test):
		#self.emit(QtCore.SIGNAL("ready()"))
		print test
		#pass

class abstractWebkitChatWidget(QtWebKit.QWebView):
	def __init__(self,chatwidget,parent=None):
		QtWebKit.QWebView.__init__(self,parent)
		self.chatwidget=weakref.ref(chatwidget)
		# webkit configuration
		self.settings().setAttribute(QtWebKit.QWebSettings.JavascriptEnabled,True)
		self.p=QtWebKit.QWebPage(self)
		self.p.javaScriptConsoleMessage=self.javaScriptConsoleMessage
		self.setPage(self.p)
		self.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
		# messageObject
		self.messageObject=message("")
		self.messageObject.w=self
		# signals
		QtCore.QObject.connect(self.messageObject,QtCore.SIGNAL("ready()"),self.messageObjectReady)
		QtCore.QObject.connect(self,QtCore.SIGNAL("loadFinished ( bool)"),self.webkitLoaded_)
		QtCore.QObject.connect(self.page().mainFrame(),QtCore.SIGNAL("javaScriptWindowObjectCleared ()"),self.webkitCleared)
#		QtCore.QObject.connect(self,QtCore.SIGNAL("linkClicked ( const QUrl &)"),QtGui.QDesktopServices.openUrl)
		QtCore.QObject.connect(self,QtCore.SIGNAL("linkClicked ( const QUrl &)"),self.openUrl)
		self.palette().setColor(QtGui.QPalette.Inactive, QtGui.QPalette.Highlight,QtGui.QColor(self.palette().color(QtGui.QPalette.Active, QtGui.QPalette.Highlight)))
		#self.palette().setColor(QtGui.QPalette.Inactive, QtGui.QPalette.HighlightedText,self.palette().highlightedText().color())

		self.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding,QtGui.QSizePolicy.Expanding))
		self.setAcceptDrops(True)
		self.page().mainFrame().setTextSizeMultiplier(float(self.chatwidget().main().config['textSizeMultiplier']))

	def javaScriptConsoleMessage(self,message,linNumber, source):
		print "JAVASCRIPT CONSOLE MESSAGE",[unicode(message)],linNumber,[unicode(source)]

	def openUrl(self,  url):
		if url.scheme() == 'xmpp':
			print "it's our!"
			self.chatwidget().main().xmppUri(url)
		else:
			QtGui.QDesktopServices.openUrl(url)
		
	def dragEnterEvent(self, event):
		if event.mimeData().hasText():
			if self.chatwidget().main().getJid(unicode(event.mimeData().text())):
				event.acceptProposedAction()
			else:
				event.ignore()
		elif event.mimeData().hasFormat("text/uri-list"):
			event.acceptProposedAction()
		else:
			event.ignore()

	def dragMoveEvent(self, event):
		event.acceptProposedAction()

	def dragLeaveEvent(self, event):
		event.acceptProposedAction()
		
	def dropEvent(self, event):
		# to be overridden
		pass

	def event(self,event):
		# tooltip request:
		if int(event.type())==110:
			hit=self.page().mainFrame().hitTestContent(event.pos())
			url=hit.linkUrl()
			if url and not url.isEmpty():
  				self.setToolTip(url.toString())
			else:
			    self.setToolTip("")
		return QtGui.QWidget.event(self,event)

	def contextMenuEvent(self,event):
		menu=QtGui.QMenu(self)
		hit=self.page().mainFrame().hitTestContent(event.pos())
		if len(hit.linkText())!=0:
			action=menu.addAction(self.tr("Open"))
			action.setObjectName("open")
			action.setData(QtCore.QVariant(hit.linkUrl()))
			menu.addAction(action)
			action=menu.addAction(self.tr("Copy link to clipboard"))
			action.setObjectName("copy_to_clipboard")
			action.setData(QtCore.QVariant(hit.linkUrl()))
			menu.addAction(action)
		if len(self.selectedText())!=0:
			action=self.pageAction(QtWebKit.QWebPage.Copy)
			action.setText(self.tr("Copy text"))
			menu.addAction(action)
		if not (hit.pixmap().isNull()):
			action=menu.addAction(self.tr('Edit Image'))
			action.setObjectName("edit_image")
			action.image = hit.pixmap().toImage()
			menu.addAction(action)
		if unicode(hit.imageUrl().toString()).split('?')[-1].startswith('receipt'):
			receiptId = unicode(hit.imageUrl().toString()).split('?')[-1][7:]
			print receiptId
			action=menu.addAction(self.tr('Resend message'))
			action.setObjectName("resend_message")
			action.setData(QtCore.QVariant(receiptId))
			menu.addAction(action)
		if unicode(hit.linkUrl().scheme()) == 'xmpp':
			raw = unicode(hit.linkUrl().toString())
			jd = unicode(hit.linkUrl().path())
			server = jd.split('@')[1]
			wellKnownMuc = ['conf.netlab.cz', 'conference.jabber.org', 'chat.chrome.pl', 'conference.jabber.ru']

			if self.chatwidget().main().client.hasIdentity(server, 'conference', 'text') or server in wellKnownMuc or raw.endswith('?join'):
				action = menu.addAction(self.tr('Join room'))
				action.setObjectName("join_muc")
				action.setData(QtCore.QVariant(jd))
				menu.addAction(action)
			else:
		   		items=self.chatwidget().main().ui.roster.getUserItems(jd)
				if len(items)==0:
					submenu=self.chatwidget().main().ui.roster.buildJidMenu(jd)
				else:
					item=items[0]
					group=item.group
					jid=item.jid
					submenu=self.chatwidget().main().ui.roster.buildContactMenu(unicode(jid),group)
				submenu.setTitle(jd)
				menu.addMenu(submenu)

		menu.addSeparator()
		action=menu.addAction(self.tr("Search"))
		action.setObjectName("search")

#		self.paction=self.pageAction(QtWebKit.QWebPage.InspectElement) 
#		self.paction.setText(self.tr("Web Inspector...")) 
#		menu.addAction(self.paction)

		try:
			typ=self.chatwidget().typ
		except:
			typ="chat"
		if typ=="groupchat":
			menu.addSeparator()
			pref=QtGui.QMenu(self.tr("Preferences"),menu)
			
			action=pref.addAction(self.tr('Show join/part messages'))
			action.setCheckable(True)
			if self.chatwidget().main().config['showMucJoinPart']=="True":
				action.setChecked(True)
			action.setObjectName("gc_toggle_join_part_messages")
			pref.addAction(action)

			action=pref.addAction(self.tr('Show status change messages'))
			action.setCheckable(True)
			if self.chatwidget().main().config['showMucStatus']=="True":
				action.setChecked(True)
			action.setObjectName("gc_toggle_status_messages")
			pref.addAction(action)
			
			pref.addSeparator()

			action=pref.addAction(self.tr('Change groupchat theme'))
			action.setObjectName("gc_theme")
			pref.addAction(action)

			menu.addMenu(pref)

		menu.addSeparator()
		zoom = QtGui.QMenu(self.tr("Zoom"),menu)
		
		action = zoom.addAction(self.tr("Zoom In"))
		action.setObjectName("zoom_in")
		
		action = zoom.addAction(self.tr("Zoom out"))
		action.setObjectName("zoom_out")
		
		action = zoom.addAction(self.tr("Reset"))
		action.setObjectName("zoom_reset")
		
		menu.addMenu(zoom)

		menu.connect(menu, QtCore.SIGNAL("triggered ( QAction * )"),self.contextMenuTriggered)
		menu.popup(event.globalPos())
		
	def contextMenuTriggered(self,action):
		cmd=action.objectName()
		if cmd=="open":
			QtGui.QDesktopServices.openUrl(action.data().toUrl())
		elif cmd=="search":
		    self.chatwidget().ui.searchWidget.showMe()
		elif cmd=="copy_to_clipboard":
			QtGui.QApplication.clipboard().setText(action.data().toUrl().toString())
		elif cmd == 'edit_image':
			print action.data()
			print unicode(action.data().toString())
			self.chatwidget().getPaintWindow().open(image = action.image)
			self.chatwidget().getPaintWindow().show()
		elif cmd == 'resend_message':
			receiptId = action.data().toString()
			if self.chatwidget().main().client.messageReceipts.has_key(receiptId):
				self.chatwidget().main().client.sendMessage(self.main.client.messageReceipts[receiptId])

		elif cmd == 'gc_toggle_join_part_messages':
			if self.chatwidget().main().config['showMucJoinPart']=="True":
				self.chatwidget().main().config['showMucJoinPart']="False"
			else:
				self.chatwidget().main().config['showMucJoinPart']="True"
			self.chatwidget().main().config.save()
		elif cmd == 'gc_toggle_status_messages':
			if self.chatwidget().main().config['showMucStatus']=="True":
				self.chatwidget().main().config['showMucStatus']="False"
			else:
				self.chatwidget().main().config['showMucStatus']="True"
			self.chatwidget().main().config.save()
		elif cmd == 'gc_theme':
			self.chatwidget().main().preferencesClicked(page=5,viewTab=2)
		elif cmd == 'join_muc':
			jd = unicode(action.data().toString())
			nickname = self.chatwidget().main().selfName
			if self.chatwidget().main().chat.addGroupChatTab(jd,nickname):
				self.chatwidget().main().client.joinGC(jd, nickname, None,self.chatwidget().main().config['sendRooms']=="True")
		elif cmd == "zoom_in":
			self.chatwidget().main().config['textSizeMultiplier']=float(self.chatwidget().main().config['textSizeMultiplier'])+0.1
			self.chatwidget().main().config.write()
			self.page().mainFrame().setTextSizeMultiplier(float(self.chatwidget().main().config['textSizeMultiplier']))
		elif cmd == "zoom_out":
			self.chatwidget().main().config['textSizeMultiplier']=float(self.chatwidget().main().config['textSizeMultiplier'])-0.1
			self.chatwidget().main().config.write()
			self.page().mainFrame().setTextSizeMultiplier(float(self.chatwidget().main().config['textSizeMultiplier']))
		elif cmd == "zoom_reset":
			self.chatwidget().main().config['textSizeMultiplier']=1.0
			self.chatwidget().main().config.write()
			self.page().mainFrame().setTextSizeMultiplier(float(self.chatwidget().main().config['textSizeMultiplier']))

	def copySelectedText(self):
		text=self.selectedText()
		if len(text)!=0:
			QtGui.QApplication.clipboard().setText(unicode(text))

	def reloadImage(self,name,data,x=None):
##		if x:
		self.messageObject.src[name]=data
		if not self.messageObject.handlers.has_key(name):
			self.messageObject.addHandler(name,self.reloadImage,[name,data,x])
		self.page().mainFrame().evaluateJavaScript("reloadImage('%s');"%name)
		log.msg("reloadImage('%s');"%name)
#		else:
	#		self.chatwidget().main().reactor.callLater(1,self.reloadImage,name,data,True)

	def removeElementById(self,i):
		self.page().mainFrame().evaluateJavaScript("removeById('%s');"%i)

	def replaceElementById(self,i,html):
		self.page().mainFrame().evaluateJavaScript("replaceById('%s','%s');"%(i,html))

	def messageObjectReady(self):
		#print "messageObjectReady",self.messageObject.messageCache
		if len(self.messageObject.messageCache)!=0:
			self.page().mainFrame().evaluateJavaScript("addNextMessage();")
		
	def webkitCleared(self):
		self.page().mainFrame().addToJavaScriptWindowObject("messageObject",self.messageObject)

	def webkitLoaded_(self):
		self.page().mainFrame().evaluateJavaScript("showLastMessages();")
		self.page().mainFrame().evaluateJavaScript("addHistoryMessages();")
		self.webkitLoaded=True
		self.messageObjectReady()
		try:
			typ=self.chatwidget().typ
		except:
			typ="chat"
		if typ=="groupchat":
			self.chatwidget().refreshStats()

	def loadWebkit(self):
		self.webkitLoaded=False
		try:
			typ=self.chatwidget().typ
		except:
			typ="chat"
		if typ=="groupchat":
			stylesheet=self.chatwidget().main().webkitThemeFactory.genGroupchatStyleSheet()
			footer=self.chatwidget().main().webkitThemeFactory.genGroupchatFooter()
			header=self.chatwidget().main().webkitThemeFactory.genGroupchatHeader()
		else:
			stylesheet=self.chatwidget().main().webkitThemeFactory.genChatStyleSheet()
			footer=self.chatwidget().main().webkitThemeFactory.genChatFooter()
			header=self.chatwidget().main().webkitThemeFactory.genChatHeader(self.chatwidget().name,self.chatwidget().file)
		code=""
		self.messageObject.messages=[]
		i=0
		previousName=""
		if typ=="groupchat":
			for m in self.chatwidget().lastMessages:
				out=m[0]=="out"
				if out:
					if m[1]==previousName:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genGroupchatOutgoingNextContent(m[1],m[2],m[3],m[4]))
						code+="insertMessage(%s);\n" % str(i)
					else:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genGroupchatOutgoingContent(m[1],m[2],m[3],m[4]))
						code+="addMessage(%s);\n" % str(i)
				else:
					if m[1]==previousName:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genGroupchatIncomingNextContent(m[1],m[2],m[3],m[4]))
						code+="insertMessage(%s);\n" % str(i)
					else:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genGroupchatIncomingContent(m[1],m[2],m[3],m[4]))
						code+="addMessage(%s);\n" % str(i)
				previousName=unicode(m[1])
				i+=1
		else:
			for m in self.chatwidget().lastMessages:
				out=m[0]=="out"
				if out:
					if m[1]==previousName:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genOutgoingNextContent(m[1],m[2],m[3],m[4]))
						code+="insertMessage(%s);\n" % str(i)
					else:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genOutgoingContent(m[1],m[2],m[3],m[4]))
						code+="addMessage(%s);\n" % str(i)
				else:
					if m[1]==previousName:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genIncomingNextContent(m[1],m[2],m[3],m[4]))
						code+="insertMessage(%s);\n" % str(i)
					else:
						self.messageObject.messages.append(self.chatwidget().main().webkitThemeFactory.genIncomingContent(m[1],m[2],m[3],m[4]))
						code+="addMessage(%s);\n" % str(i)
				previousName=unicode(m[1])
				i+=1
		style="::selection{background:%s;color:%s;}" %(self.palette().color(QtGui.QPalette.Active, QtGui.QPalette.Highlight).name(),self.palette().color(QtGui.QPalette.Active, QtGui.QPalette.HighlightedText).name())
		print "style:",style
		html="""
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<meta http-equiv="content-type" content="text/html; charset=utf-8" />
<style type="text/css" media="screen,print"> @import url( "main.css" ); </style>
<style id="mainStyle" type="text/css" media="screen,print"> %s </style>
<style type="text/css"><!-- %s --></style>
<script>

function reloadImage(name) {
	messageObject.log("test "+name)
	i = document.getElementById(name);
	if (i){
		i.src = 'refreshme';
		i.src = messageObject.getSrc(name)+'?'+Math.random();
		i.title = i.src;
		messageObject.reloaded(name);
		messageObject.removeHandler(name);
	}
	else { messageObject.log("no element found");}
}

function addHistoryMessages() {
var b = messageObject.historyMessageDirection();
if (b==1) addHistory(-1);
if (b==0) insertHistory(-1);
b = messageObject.historyMessageDirection();
if (b!=-1) addHistoryMessages();
}

function addNextMessage() {
var b = messageObject.messageDirection();
if (b==1) {addMessage(-1);messageObject.log("new message appended");}
if (b==0) {insertMessage(-1);messageObject.log("new message appended");}
var handlers = messageObject.getHandlers();
for(i=0;i<handlers.length;i++){
    h = document.getElementById(handlers[i]);
    if (h){messageObject.handlerReady(handlers[i]);}
}
b = messageObject.messageDirection();
if (b!=-1) addNextMessage();
}

function addHistory(index) {
shouldScroll = nearBottom();
//Remove any existing insertion point
insert = document.getElementById("insert2");
if(insert) insert.parentNode.removeChild(insert);
messageObject.ready();
var ni = document.getElementById('history');
var numi = document.getElementById('theValue');
var num = (document.getElementById('theValue').value -1)+ 2;
numi.value = num;
var divIdName = "my"+num+"Div";
var newdiv = document.createElement('div');
newdiv.setAttribute("id",divIdName);
if (index==-1) newdiv.innerHTML = messageObject.historyMsg();
else newdiv.innerHTML = messageObject.msg_(index);
ni.appendChild(newdiv);
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}

function insertHistory(index) {
shouldScroll = nearBottom();
messageObject.ready();
                        //Locate the insertion point
                        var insert = document.getElementById("insert2");

                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        if (index==-1) {newNode = range.createContextualFragment(messageObject.historyMsg());}
						else {newNode = range.createContextualFragment(messageObject.msg_(index));}

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}

function addMessage(index) {
shouldScroll = nearBottom();
//Remove any existing insertion point
insert = document.getElementById("insert");
if(insert) insert.parentNode.removeChild(insert);

var ni = document.getElementById('myDiv');
var numi = document.getElementById('theValue');
var num = (document.getElementById('theValue').value -1)+ 2;
numi.value = num;
var divIdName = "my"+num+"Div";
var newdiv = document.createElement('div');
newdiv.setAttribute("id",divIdName);
if (index==-1) newdiv.innerHTML = messageObject.msg();
else newdiv.innerHTML = messageObject.msg_(index);
ni.appendChild(newdiv);
messageObject.ready();
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}
function insertMessage(index) {
shouldScroll = nearBottom();

                        //Locate the insertion point
                        var insert = document.getElementById("insert");

                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        if (index==-1) {newNode = range.createContextualFragment(messageObject.msg());}
						else {newNode = range.createContextualFragment(messageObject.msg_(index));}

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);
messageObject.ready();
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}

function removeById(index) {

                        //Locate the insertion point
                        var insert = document.getElementById(index);
                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        newNode = range.createContextualFragment('');

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);

}

function replaceById(index,text) {

                        //Locate the insertion point
                        var insert = document.getElementById(index);
                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        newNode = range.createContextualFragment(text);

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);

}

function showImage(imageId,imgUrl,link) {
shouldScroll = nearBottom();

                        //Locate the insertion point
                        var insert = document.getElementById(imageId);
                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="hideImage(\\''+imageId+'\\',\\''+imgUrl+'\\',\\''+link+'\\');")>[%s]</a></div><div id="loaded'+imageId+'"><a href="'+link+'"><img src="'+imgUrl+'" /></a></div>');

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}

function reshowImage(imageId,imgUrl,link) {
shouldScroll = nearBottom();
document.getElementById('loaded'+imageId).style.display = 'inline';
                        //Locate the insertion point
                        var insert = document.getElementById(imageId);
                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="hideImage(\\''+imageId+'\\',\\''+imgUrl+'\\',\\''+link+'\\');")>[%s]</a></div>');

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);
if (shouldScroll) setTimeout("scrollToBottom()", 100);

}

function hideImage(imageId,imgUrl,link){
   document.getElementById('loaded'+imageId).style.display = 'none';
                        //Locate the insertion point
                        var insert = document.getElementById(imageId);

                        //make new node
                        range = document.createRange();
                        range.selectNode(insert.parentNode);
                        newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="reshowImage(\\''+imageId+'\\',\\''+imgUrl+'\\',\\''+link+'\\');")>[%s]</a></div>');

                        //swap
                        insert.parentNode.replaceChild(newNode,insert);
}

//Auto-scroll to bottom.  Use nearBottom to determine if a scrollToBottom is desired.
function nearBottom() {
		return ( (document.body.scrollTop+100) >= ( document.body.offsetHeight - ( window.innerHeight * 1.2 ) ) );
}
function scrollToBottom() {
		document.body.scrollTop = document.body.offsetHeight;
}

function showLastMessages(){
%s
}

</script>
</head>
<body>
<div id="Chat">
%s
<input type="hidden" value="0" id="theValue" />
<div id="history"></div>
<div id="myDiv"> </div>
%s
</div>
<a name='bottom'></a>
</body>
</html>
		""" % (stylesheet,style,self.tr('Hide image'),self.tr('Hide image'),self.tr('Show image'),code,header,footer)

		self.chatwidget().imageId=0

		# debug... we don't need it anymore
		#f=open(self.chatwidget().main().webkitThemeFactory.chatPath()+"/test.html","w")
		#f.write(html)
		#f.close()
		if typ=="groupchat":
			self.page().mainFrame().setHtml(html,QtCore.QUrl("file:///"+self.chatwidget().main().webkitThemeFactory.groupchatPath()))
		else:
			self.page().mainFrame().setHtml(html,QtCore.QUrl("file:///"+self.chatwidget().main().webkitThemeFactory.chatPath()))


class webkitChatWidget(abstractWebkitChatWidget):
	def __init__(self, chatwidget, parent=None):
		abstractWebkitChatWidget.__init__(self, chatwidget, parent)

	def dropEvent(self, event):
		"""
		Called when something is dropped to this widget.
		If there is JID dropped, new MUC is created and the jid is invited to the room.
		"""
		if event.mimeData().hasText():
			# test if it is JID
			jid2=self.chatwidget().main().getJid(unicode(event.mimeData().text()))
			if not jid2:
				event.ignore()
				return

			room=str(int(time.time())) # define room name
			# find server when we can host the room
			mucjid = None
			for jid, node in self.chatwidget().main().client.disco.iteritems():
				if not node[(jid,None)].has_key('identities'):
					continue
				for id in node[(jid,None)]['identities'].itervalues():
					#print jid, id
					if id.get('category') == 'conference' and id.get('type') == 'text' and jid.startswith('c'):
						mucjid = jid
						break
				if mucjid:
					break
			room+="@"+mucjid # room jabber id

			name=self.chatwidget().parent.tabName # get name of tab where is this widget showed
			rmIndex=int(self.chatwidget().main().chat.ui.chatTab.currentIndex()) # get index of this tab
			# join to the room and send invitation
			if self.chatwidget().main().chat.addGroupChatTab(room,self.chatwidget().main().client.jid.user,name=name):
				tab,index=self.chatwidget().main().chat.findTab(room)
				tab.chat.invitation=[unicode(jid2.full()),unicode(self.chatwidget().parent.jid)]
				self.chatwidget().main().client.joinGC(room, self.chatwidget().main().client.jid.user,sendRooms=self.chatwidget().main().config['sendRooms']=="True")
			# remove old user2user conversation tab
			# XXX: for some reason, removing the tab causes a crash
			#self.chatwidget().main().chat.removeTab(rmIndex) 
			event.acceptProposedAction()
		elif (event.mimeData().hasUrls()):
			urlList=event.mimeData().urls()
			if len(urlList)>0:
				new=[]
				for url in urlList:
					f=unicode(url.toLocalFile())
					if len(f)!=0:
						new.append(f)
				file=new
				print file
				self.chatwidget().main().showFiletransferDialog(file,self.chatwidget().jid)
			event.acceptProposedAction()
		else:
			event.ignore()

class webkitGroupChatWidget(abstractWebkitChatWidget):
	def __init__(self, chatwidget, parent=None):
		abstractWebkitChatWidget.__init__(self, chatwidget, parent)

	def dropEvent(self, event):
		if event.mimeData().hasText():
			jid = self.chatwidget().main().getJid(unicode(event.mimeData().text()))
			if not jid:
				event.ignore()
				return
			room = unicode(self.chatwidget().jid)
			reason = self.tr("Hi! I'd love to see you in multichat at ") + room
			self.chatwidget().main().client.sendInvitation(jid.full(), room, reason, cont=True)
			event.acceptProposedAction()
		else:
			event.ignore()
