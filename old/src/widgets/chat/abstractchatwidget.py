from PyQt4 import QtCore, QtGui, QtWebKit
from configobj import ConfigObj
#from palette import *
import urllib,re,os
from twisted.web.microdom import *
from twisted.web.domhelpers import gatherTextNodes

from widgets import filetransfer
from pyxl import jid as jidT
import time
from include import utils
from widgets.emoticonswidget import *
from widgets.linkeditor import linkEditorDialog
import weakref
from webkitchatwidget import searchWidget
from widgets import paint
from pyxl.message import Message
from include.constants import RESOURCEPATH
try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1


class normalLineEditWidget(QtGui.QTextEdit):
	"""
	QTextEdit widget for user input.
	"""
	def __init__(self,main,parent=None):
		apply(QtGui.QTextEdit.__init__,(self,parent))
		self.main=weakref.ref(main) #: abstractChatWidget pointer
		self.parent=parent #: parent
		self.setObjectName("line")
		self.composing=False #: True if user is typing
		self.timer = QtCore.QTimer(self) # timer to determine if user paused typing
		QtCore.QObject.connect(self.timer, QtCore.SIGNAL("timeout()"),self.paused)
		self.text=""
		self.t=False
		self.bold=False
		self.italic=False
		self.underline=False
		self.color=None
		self.backgroundBrush=None
		self.fontSize=None
		self.changeFormat=True
		self.reformated=False
		if self.parent.xhtml:
			QtCore.QObject.connect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)
			#QtCore.QObject.connect(self,QtCore.SIGNAL("cursorPositionChanged ()"),self.setFormat)


	def setFormat(self,fmt=None):
		# detect format of current character
		f=fmt.font()
		if len(unicode(self.textCursor().selectedText()))==0:
			b=f.bold()
			if self.bold!=b:
				self.bold=b
				self.parent.ui.boldButton.setChecked(b)
			b=f.italic()
			if self.italic!=b:
				self.italic=b
				self.parent.ui.italicButton.setChecked(b)
			b=f.underline()
			if self.underline!=b:
				self.underline=b
				self.parent.ui.underlineButton.setChecked(b)
			b=fmt.foreground().color()
			if self.color!=b:
				self.color=b
				colorIcon=QtGui.QPixmap(16,16)
				colorIcon.fill(b)
				self.parent.ui.colorButton.setIcon(QtGui.QIcon(colorIcon))
			b=fmt.background()
			if True:

				self.backgroundBrush=b
				colorIcon=QtGui.QPixmap(16,16)
				#for background color
				if fmt.background().isOpaque():
					colorIcon.fill(QtGui.QColor(b.color()))
				else:
					colorIcon.fill(QtGui.QColor(self.parent.defaultBackgroundColor))
				p=QtGui.QPixmap(RESOURCEPATH+"images/16x16/actions/format-text-bold.png")
				painter=QtGui.QPainter(colorIcon)
				painter.drawPixmap(0,0,p)
				painter.end()
				self.parent.ui.backgroundButton.setIcon(QtGui.QIcon(colorIcon))



	def formatChanged(self,format):
		if format.isAnchor() or self.signalsBlocked():
			print 'blocked'
			return
		self.blockSignals(True)
		#QtCore.QObject.disconnect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)
		if len(unicode(self.toPlainText()))==0:
			if not self.reformated:
				print "reformat"
				#self.reformated=True
				self.reformat(format)
				#QtCore.QObject.connect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)
			else:
				self.reformated=False
			self.blockSignals(False)
			return
		print "setFormat"
		self.setFormat(format)
		self.blockSignals(False)
		#QtCore.QObject.connect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)

	def reformat(self,fmt=None):
		#QtCore.QObject.disconnect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)
		self.parent.underline(self.underline)
		self.parent.bold(self.bold)
		self.parent.italic(self.italic)
		#if self.fontSize:
			#self.parent.fontSize(self.fontSize)
			#self.parent.ui.fontSize.setCurrentIndex(self.parent.ui.fontSize.findText(str(int(self.fontSize))))
		if self.color:
			self.parent.color(unicode(self.color.name()))
		if self.backgroundBrush:
			if self.backgroundBrush.isOpaque():
				self.parent.background(unicode(self.backgroundBrush.color().name()))
			else:
				self.parent.background(unicode('no'))
		
		#QtCore.QObject.connect(self,QtCore.SIGNAL("currentCharFormatChanged ( const QTextCharFormat & )"),self.formatChanged)

	def paused(self):
		"""
		Detects if user stops typing and sends 'paused' message if user stops.
		"""
		try:
			self.timer.stop()
		except:pass
		if self.text==unicode(self.toPlainText()):
			# text from previous loop is the same as currently typed text => user stops typing
			if len(self.text)!=0:
				if self.main().typ!="groupchat":
					self.main().main().client.sendMessage(self.main().jid, "",composing="paused")
			self.composing=False
		else:
			# text from previous loop is diffrent from currently typed text => user is typing
			self.timer.start(2000)
			self.text=unicode(self.toPlainText())

		self.t=False
	
	def keyPressEvent(self,event):
		if event.matches(QtGui.QKeySequence.NextChild):
			self.main().main().chat.event(event)
			return
		elif event.matches(QtGui.QKeySequence.PreviousChild):
			self.main().main().chat.event(event)
			return
		if not self.composing:
			# user starts typing
			if self.main().typ!="groupchat":
				self.main().main().client.sendMessage(self.main().jid, "",composing="composing")
		key=event.key()
		if key!=QtCore.Qt.Key_Tab:
			self.main().tabWord=None
		if (key == QtCore.Qt.Key_Return or key == QtCore.Qt.Key_Enter):
			if bool(event.modifiers() & QtCore.Qt.ControlModifier) == (self.main().main().config['sendByCtrl'] == "True"):
				self.main().sendButtonClicked()
				event.accept()
			else:
				# let QTextEdit insert a newline
				new_event = QtGui.QKeyEvent(event.type(), key, QtCore.Qt.NoModifier, event.text(), event.isAutoRepeat(), event.count())
				return QtGui.QTextEdit.keyPressEvent(self, new_event)
		elif key == QtCore.Qt.Key_Up and  self.main().hindex > 0 and (event.modifiers() & QtCore.Qt.ControlModifier): 
			self.main().hindex = self.main().hindex-1
			self.main().ui.line.setText(self.main().sent[self.main().hindex])
		elif key == QtCore.Qt.Key_Down and  self.main().hindex < len(self.main().sent) and (event.modifiers() & QtCore.Qt.ControlModifier): 

			self.main().hindex = self.main().hindex+1
			self.main().ui.line.setText(self.main().sent[self.main().hindex])
		elif key==QtCore.Qt.Key_Tab:
			self.main().tabPressed()
			return
		
		elif key == QtCore.Qt.Key_B and  (event.modifiers() & QtCore.Qt.ControlModifier):
			self.main().ui.boldButton.click()
		
		elif key == QtCore.Qt.Key_I and  (event.modifiers() & QtCore.Qt.ControlModifier):
			self.main().ui.italicButton.click()
		
		elif key == QtCore.Qt.Key_U and  (event.modifiers() & QtCore.Qt.ControlModifier):
			self.main().ui.underlineButton.click()
		else:
			QtGui.QTextEdit.keyPressEvent(self,event)

		# user starts composing so we have to start checking if he doesn't stop
		# we have to start timer only once, so there is some type of locker self.t
		if not self.t and not self.composing:
			self.text=unicode(self.toPlainText())
			self.t=True
			self.timer.start(2000)
		if not self.composing:
			self.composing=True


class abstractChatWidget(QtGui.QWidget):
	def __init__(self, initClass, webkitClass, main, jid, xhtml=True, parent=None):
		apply(QtGui.QWidget.__init__,(self,parent))
		self.ui=initClass()
		self.ui.setupUi(self)
		#self.main=main
		self.parent=parent
		self.xhtml=xhtml
		self.lastMessages=[]
		self.paintWindow = None
		self.separator=None
		
		# chat view widget (self.ui.textEdit)
		l=QtGui.QVBoxLayout(self.ui.viewWidget)
		l.setMargin(0)
		l.setSpacing(0)
		#self.ui.textEdit=textEditClass(self,self.ui.viewWidget)
		#self.ui.textEdit.hide()
		#self.ui.webkit=QtWebKit.QWebView(self)
		self.ui.webkit = webkitClass(self, self)
		#self.ui.webkit.settings().setAttribute(QtWebKit.QWebSettings.JavascriptEnabled,True)

		#self.loadWebkit()

		#self.ui.webkit.load(QtCore.QUrl("file:///home/hanzz/svn/jabbim/trunk/test.html"))
		l.addWidget(self.ui.webkit)
		self.ui.webkit.show()
		self.ui.searchWidget=searchWidget(self.ui.webkit,self)
		l.addWidget(self.ui.searchWidget)
		#self.ui.webkit.page().setLinkDelegationPolicy(QtWebKit.QWebPage.DelegateAllLinks)
		#QtCore.QObject.connect(self.ui.webkit,QtCore.SIGNAL("linkClicked ( const QUrl &)"),QtGui.QDesktopServices.openUrl)
		# chat editor widget (self.ui.line)
		layout=QtGui.QHBoxLayout(self.ui.lineWidget)
		layout.setMargin(0)
		layout.setSpacing(0)
		self.ui.line=normalLineEditWidget(self,self)
		self.ui.line.setAcceptRichText(False)
		# tiny mc test :)
		#self.ui.line=QtWebKit.QWebView(self)
  		#file="file:///"+os.getcwd()+"/index.html"
  		#self.ui.line.load(QtCore.QUrl(file))
		layout.addWidget(self.ui.line)
		self.ui.line.show()

		self.first=None #: True if first message arrived; False if arrived more than one message. Otherwise None.
		self.jid=jid #: users JID
		self.sent = []
		self.hindex = 0
		self.featuredWidget=[]

		# signals
		QtCore.QObject.connect(self.ui.sendButton, QtCore.SIGNAL("clicked ()"),self.sendButtonClicked)
		QtCore.QObject.connect(self.ui.line, QtCore.SIGNAL("returnPressed ()"),self.sendButtonClicked)
		QtCore.QObject.connect(self.ui.smileys, QtCore.SIGNAL("toggled (bool)"),self.smileysClicked)
		QtCore.QObject.connect(self.ui.boldButton, QtCore.SIGNAL("clicked ( bool )"),self.bold)
		QtCore.QObject.connect(self.ui.italicButton, QtCore.SIGNAL("clicked (bool)"),self.italic)
		QtCore.QObject.connect(self.ui.underlineButton, QtCore.SIGNAL("clicked (bool)"),self.underline)
		QtCore.QObject.connect(self.ui.linkButton, QtCore.SIGNAL("clicked (bool)"),self.link)
		#if self.typ=="chat": 
			#QtCore.QObject.connect(self.ui.paintButton,QtCore.SIGNAL("clicked()"),self.paint)
		#QtCore.QObject.connect(self.ui.fontSize,QtCore.SIGNAL("activated(const QString &)"),self.fontSize)
		
		#self.ui.textEdit.setAcceptRichText(False)
		# save init part from self.main().skin to the textEdit
		self.init=""
		#if self.main().skin.has_key("on_init"):
#			self.init=self.main().skin["on_init"]
		#self.ui.textEdit.setHtml("<br/>"+self.init)
		
		self.unread=0 #: number of unread messages
		self.unreadEvent=None

		if not self.xhtml or self.main().config['useXHTML'] == 'False':
			self.ui.boldButton.hide()
			self.ui.italicButton.hide()
			self.ui.underlineButton.hide()
			self.ui.colorButton.hide()
			self.ui.fontSize.hide()
			self.ui.backgroundButton.hide()
			self.ui.linkButton.hide()
			#if self.typ == 'chat':
				#self.ui.paintButton.hide()
		else:
			self.ui.fontSize.hide()
			#db=QtGui.QFontDatabase()
			#for size in db.standardSizes():
				#self.ui.fontSize.addItem(str(size))
			#self.ui.fontSize.setCurrentIndex(self.ui.fontSize.findText(str(QtGui.QApplication.font().pointSize())))
			#self.ui.line.fontSize=float(str(QtGui.QApplication.font().pointSize()))

			self.defaultFormat=self.ui.line.currentCharFormat()
			self.defaultColor=self.ui.line.textColor()
			self.ui.line.color=self.defaultColor
			self.defaultBackgroundColor=QtGui.QColor(self.ui.line.palette().base().color())
			colorMenu=QtGui.QMenu(self.ui.colorButton)
			backgroundMenu=QtGui.QMenu(self.ui.backgroundButton)
			colorIcon=QtGui.QPixmap(16,16)
			
			colorIcon.fill(QtCore.Qt.white)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('White'))
			action.setData(QtCore.QVariant("#ffffff"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('White'))
			action.setData(QtCore.QVariant("#ffffff"))

			colorIcon.fill(QtCore.Qt.black)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Black'))
			action.setData(QtCore.QVariant("#000000"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Black'))
			action.setData(QtCore.QVariant("#000000"))

			colorIcon.fill(QtCore.Qt.red)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Red'))
			action.setData(QtCore.QVariant("#ff0000"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Red'))
			action.setData(QtCore.QVariant("#ff0000"))

			colorIcon.fill(QtCore.Qt.green)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Green'))
			action.setData(QtCore.QVariant("#00ff00"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Green'))
			action.setData(QtCore.QVariant("#00ff00"))

			colorIcon.fill(QtCore.Qt.blue)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Blue'))
			action.setData(QtCore.QVariant("#0000ff"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Blue'))
			action.setData(QtCore.QVariant("#0000ff"))

			colorIcon.fill(QtCore.Qt.magenta)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Pink'))
			action.setData(QtCore.QVariant("#ff00ff"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Pink'))
			action.setData(QtCore.QVariant("#ff00ff"))

			colorIcon.fill(QtCore.Qt.yellow)
			action=colorMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Yellow'))
			action.setData(QtCore.QVariant("#ffff00"))
			action=backgroundMenu.addAction(QtGui.QIcon(colorIcon),self.tr('Yellow'))
			action.setData(QtCore.QVariant("#ffff00"))

			colorMenu.addSeparator()

			action=colorMenu.addAction(self.tr('No color'))
			action.setData(QtCore.QVariant("no"))
			action=backgroundMenu.addAction(self.tr('No color'))
			action.setData(QtCore.QVariant("no"))

			QtCore.QObject.connect(colorMenu, QtCore.SIGNAL("triggered ( QAction *)"),self.color)
			QtCore.QObject.connect(backgroundMenu, QtCore.SIGNAL("triggered ( QAction *)"),self.background)
			self.ui.colorButton.setMenu(colorMenu)
			self.ui.backgroundButton.setMenu(backgroundMenu)
			colorIcon.fill(self.defaultFormat.foreground().color())
			self.ui.colorButton.setIcon(QtGui.QIcon(colorIcon))
			
			#for background color
			colorIcon.fill(self.defaultBackgroundColor)
			p=QtGui.QPixmap(RESOURCEPATH+"images/16x16/actions/format-text-bold.png")
			painter=QtGui.QPainter(colorIcon)
			painter.drawPixmap(0,0,p)
			painter.end()
			self.ui.backgroundButton.setIcon(QtGui.QIcon(colorIcon))

	#def messageObjectReady(self):
		##print "messageObjectReady",self.messageObject.messageCache
		#if len(self.messageObject.messageCache)!=0:
			#self.ui.webkit.page().mainFrame().evaluateJavaScript("addNextMessage();")

	#def webkitCleared(self):
		#self.ui.webkit.page().mainFrame().addToJavaScriptWindowObject("messageObject",self.messageObject)

	#def webkitLoaded_(self):
		#self.ui.webkit.page().mainFrame().evaluateJavaScript("showLastMessages();")
		##self.main().client.reactor.callLater(1,self.writeWebkitCache)
		#self.webkitLoaded=True
		#self.messageObjectReady()

	#def writeWebkitCache(self):
		#cmds=""
		##print "CACHE:",self.messageObject.messageCache
		##print "CACHE:",self.messageObject.message
		#for msg in self.messageObject.messageCache:
			#if not msg[0]:
				#cmds+="addMessage(-1);"
			#else:
				#cmds+="insertMessage(-1);"
		##print 'CMDS',cmds
		#self.ui.webkit.page().mainFrame().evaluateJavaScript(cmds)
		#self.webkitLoaded=True

	def loadWebkit(self):
		self.ui.webkit.loadWebkit()
		#self.webkitLoaded=False
		#try:
			#typ=self.typ
		#except:
			#typ="chat"
		#if typ=="groupchat":
			#stylesheet=self.main().webkitThemeFactory.genGroupchatStyleSheet()
			#footer=self.main().webkitThemeFactory.genGroupchatFooter()
			#header=self.main().webkitThemeFactory.genGroupchatHeader()
		#else:
			#stylesheet=self.main().webkitThemeFactory.genChatStyleSheet()
			#footer=self.main().webkitThemeFactory.genChatFooter()
			#header=self.main().webkitThemeFactory.genChatHeader(self.name,self.file)
		#code=""
		#self.messageObject.messages=[]
		#i=0
		#previousName=""
		#if typ=="groupchat":
			#for m in self.lastMessages:
				#out=m[0]=="out"
				#if out:
					#if m[1]==previousName:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genGroupchatOutgoingNextContent(m[1],m[2],m[3],m[4]))
						#code+="insertMessage(%s);\n" % str(i)
					#else:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genGroupchatOutgoingContent(m[1],m[2],m[3],m[4]))
						#code+="addMessage(%s);\n" % str(i)
				#else:
					#if m[1]==previousName:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genGroupchatIncomingNextContent(m[1],m[2],m[3],m[4]))
						#code+="insertMessage(%s);\n" % str(i)
					#else:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genGroupchatIncomingContent(m[1],m[2],m[3],m[4]))
						#code+="addMessage(%s);\n" % str(i)
				#previousName=unicode(m[1])
				#i+=1
		#else:
			#for m in self.lastMessages:
				#out=m[0]=="out"
				#if out:
					#if m[1]==previousName:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genOutgoingNextContent(m[1],m[2],m[3],m[4]))
						#code+="insertMessage(%s);\n" % str(i)
					#else:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genOutgoingContent(m[1],m[2],m[3],m[4]))
						#code+="addMessage(%s);\n" % str(i)
				#else:
					#if m[1]==previousName:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genIncomingNextContent(m[1],m[2],m[3],m[4]))
						#code+="insertMessage(%s);\n" % str(i)
					#else:
						#self.messageObject.messages.append(self.main().webkitThemeFactory.genIncomingContent(m[1],m[2],m[3],m[4]))
						#code+="addMessage(%s);\n" % str(i)
				#previousName=unicode(m[1])
				#i+=1
		#html="""
#<?xml version="1.0" encoding="utf-8"?>
#<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
#<html xmlns="http://www.w3.org/1999/xhtml">
#<meta http-equiv="content-type" content="text/html; charset=utf-8" />
#<style type="text/css" media="screen,print"> @import url( "main.css" ); </style>
#<style id="mainStyle" type="text/css" media="screen,print"> %s </style>
#<script>
#function addNextMessage() {
#var b = messageObject.messageDirection();
#if (b==1) addMessage(-1);
#if (b==0) insertMessage(-1);
#b = messageObject.messageDirection();
#if (b!=-1) addNextMessage();
#}

#function addMessage(index) {
#shouldScroll = nearBottom();
#//Remove any existing insertion point
#insert = document.getElementById("insert");
#if(insert) insert.parentNode.removeChild(insert);
#messageObject.ready();
#var ni = document.getElementById('myDiv');
#var numi = document.getElementById('theValue');
#var num = (document.getElementById('theValue').value -1)+ 2;
#numi.value = num;
#var divIdName = "my"+num+"Div";
#var newdiv = document.createElement('div');
#newdiv.setAttribute("id",divIdName);
#if (index==-1) newdiv.innerHTML = messageObject.msg();
#else newdiv.innerHTML = messageObject.msg_(index);
#ni.appendChild(newdiv);
#if (shouldScroll) setTimeout("scrollToBottom()", 100);

#}
#function insertMessage(index) {
#shouldScroll = nearBottom();
#messageObject.ready();
                        #//Locate the insertion point
                        #var insert = document.getElementById("insert");

                        #//make new node
                        #range = document.createRange();
                        #range.selectNode(insert.parentNode);
                        #if (index==-1) {newNode = range.createContextualFragment(messageObject.msg());}
						#else {newNode = range.createContextualFragment(messageObject.msg_(index));}

                        #//swap
                        #insert.parentNode.replaceChild(newNode,insert);
#if (shouldScroll) setTimeout("scrollToBottom()", 100);

#}

#function removeById(index) {

                        #//Locate the insertion point
                        #var insert = document.getElementById(index);
                        #//make new node
                        #range = document.createRange();
                        #range.selectNode(insert.parentNode);
                        #newNode = range.createContextualFragment('');

                        #//swap
                        #insert.parentNode.replaceChild(newNode,insert);

#}

#function showImage(imageId,link) {
#shouldScroll = nearBottom();

                        #//Locate the insertion point
                        #var insert = document.getElementById(imageId);
                        #//make new node
                        #range = document.createRange();
                        #range.selectNode(insert.parentNode);
                        #newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="hideImage(\\''+imageId+'\\',\\''+link+'\\');")>[Hide Image]</a></div><div id="loaded'+imageId+'"><a href="'+link+'"><img src="'+link+'" /></a></div>');

                        #//swap
                        #insert.parentNode.replaceChild(newNode,insert);
#if (shouldScroll) setTimeout("scrollToBottom()", 100);

#}

#function reshowImage(imageId,link) {
#shouldScroll = nearBottom();
#document.getElementById('loaded'+imageId).style.display = 'inline';
                        #//Locate the insertion point
                        #var insert = document.getElementById(imageId);
                        #//make new node
                        #range = document.createRange();
                        #range.selectNode(insert.parentNode);
                        #newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="hideImage(\\''+imageId+'\\',\\''+link+'\\');")>[Hide Image]</a></div>');

                        #//swap
                        #insert.parentNode.replaceChild(newNode,insert);
#if (shouldScroll) setTimeout("scrollToBottom()", 100);

#}

#function hideImage(imageId,link){
   #document.getElementById('loaded'+imageId).style.display = 'none';
                        #//Locate the insertion point
                        #var insert = document.getElementById(imageId);

                        #//make new node
                        #range = document.createRange();
                        #range.selectNode(insert.parentNode);
                        #newNode = range.createContextualFragment('<div id="'+imageId+'"><a href="'+link+'" title="'+link+'">'+link+'</a> <a href="javascript:;" onclick="reshowImage(\\''+imageId+'\\',\\''+link+'\\');")>[Show Image]</a></div>');

                        #//swap
                        #insert.parentNode.replaceChild(newNode,insert);
#}

#//Auto-scroll to bottom.  Use nearBottom to determine if a scrollToBottom is desired.
#function nearBottom() {
		#return ( (document.body.scrollTop+100) >= ( document.body.offsetHeight - ( window.innerHeight * 1.2 ) ) );
#}
#function scrollToBottom() {
		#document.body.scrollTop = document.body.offsetHeight;
#}

#function showLastMessages(){
#%s
#}

#</script>
#</head>
#<body>
#<div id="Chat">
#%s
#<input type="hidden" value="0" id="theValue" />
#<div id="myDiv"> </div>
#%s
#</div>
#<a name='bottom'></a>
#</body>
#</html>
		#""" % (stylesheet,code,header,footer)

		#self.imageId=0

		## debug... we don't need it anymore
		##f=open(self.main().webkitThemeFactory.chatPath()+"/test.html","w")
		##f.write(html)
		##f.close()
		#if typ=="groupchat":
			#self.ui.webkit.page().mainFrame().setHtml(html,QtCore.QUrl("file:///"+self.main().webkitThemeFactory.groupchatPath()))
		#else:
			#self.ui.webkit.page().mainFrame().setHtml(html,QtCore.QUrl("file:///"+self.main().webkitThemeFactory.chatPath()))

	def getPaintWindow(self):
		if self.paintWindow == None:
			self.paintWindow = paint.paintWindow(self,  self)
		return self.paintWindow

	def paint(self):
		self.getPaintWindow().show()
	
	def sendPaint(self,  image,  alt = 'Image'):
		data = []
		bytes=QtCore.QByteArray()
		buf=QtCore.QBuffer(bytes)
		buf.open(QtCore.QIODevice.WriteOnly)
		if image.width()>200 or image.height()>200:
			image.save(buf,  'JPG')
		else:
			image.save(buf,  'PNG')
		hash = 'sha1+'+sha1(str(bytes)).hexdigest()+ "@bob.xmpp.org"
		print 'IMAGE', len(str(bytes))
		path = self.main().client.bobCacheDir+'/'+hash
		fp = open(path,  'wb')
		fp.write(str(bytes))
		fp.close()
		self.main().client.bobDef[hash] = path
		if len(bytes)<=(8*1024):
			img ='<img src="cid:%s" alt="%s"/>'%(hash, alt)
		else:
			img ='<img src="xmpp:%s?recvfile;sid=%s" alt="%s"/>'%(self.main().client.jid.full(), hash, alt)
		m=Message(unicode(self.jid),  typ = self.typ)
		m.setBody(alt)
		m.setXHTML(img)
		
		m.setComposing("active")
		self.main().client.sendMessage(msg = m)
		if self.typ == 'chat':
			img = '<img src="%s" alt="%s"/>'%(path, alt)
			if self.lastMessageFrom==unicode(self.main().client.jid.user):
				message=self.main().webkitThemeFactory.genOutgoingNextContent(self.main().client.jid.user,img,self.main().now(),self.selfFile)
				insert=True
			else:
				message=self.main().webkitThemeFactory.genOutgoingContent(self.main().client.jid.user,img,self.main().now(),self.selfFile)
				insert=False

			self.textEditWrite(message,insert)
		self.paintWindow.close()

	def reloadImage(self,name,data):
		self.ui.webkit.reloadImage(name,data)

	def registerFeatureForWidget(self,feature,widget):
		widget=weakref.ref(widget)
		self.featuredWidget.append([feature,widget])
		if self.main().client.hasFeature(self.jid,feature):
			widget().show()
		else:
			widget().hide()

	def unregisterFeatureForWidget(self,widget):
		for item in self.featuredWidget:
			if widget()==item[1]:
				self.featuredWidget.remove(item)
				break

	def showFeaturedWidgets(self):
		print "showFeaturedWidgets",self.featuredWidget
		# test if all widgets are alive
		x=0
		for i in range(len(self.featuredWidget)):
			if self.featuredWidget[x][1]()==None:
				print "Deleting widget for",self.featuredWidget[x][0],"because of inactivity"
				del self.featuredWidget[x]
			else:
				x+=1
		
		for item in self.featuredWidget:
			feature=item[0]
			widget=item[1]
			#print "checking ",feature," = ",self.main().client.hasFeature(self.jid,feature)
			if self.main().client.hasFeature(self.jid,feature):
				widget().show()
			else:
				widget().hide()

	def isLink(self,text):
		if text.find("://")!=-1:
			return True
		elif text.startswith("www."):
			return True
		return False

	def link(self,bool=None):
		text=unicode(self.ui.line.textCursor().selectedText())
		clipboardText=unicode(QtGui.QApplication.clipboard().text())
		url=None
		linktext=None
		if self.isLink(text):
			url=text
		elif self.isLink(clipboardText):
			url=clipboardText
			if len(text)!=0:
				linktext=text
		else:
			if len(text)!=0:
				linktext=text
		
		d=linkEditorDialog(self,url,linktext,self)
		d.exec_()
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
		#self.ui.line.textCursor().insertHtml("<a href=\"%s\">%s</a>"%(text,text))
		
		

	def fontSize(self,size):
		size=float(size)
		self.ui.line.fontSize=size
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
		#self.ui.line.setFontPointSize(size)
		fmt=QtGui.QTextCharFormat()
		fmt.setFontPointSize(size)
		cursor = self.ui.line.textCursor()
		cursor.mergeCharFormat(fmt)
		self.ui.line.setTextCursor(cursor)
		self.ui.line.mergeCurrentCharFormat(fmt)

	def color(self,action):
		"""
		Sets foreground color according to action.data(). Data should be color like #FFFFFF or string "no" for default system color.
		"""
		if isinstance(action,unicode) or isinstance(action,str):
			color=action
			if color.startswith('#'):
				self.ui.line.color=QtGui.QColor(color)
		else:
			color=unicode(action.data().toString())
			self.ui.line.color=QtGui.QColor(color)
			self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
		
		if color.startswith("#") and QtGui.QColor(color)!=self.defaultColor:
			c=QtGui.QColor(color)
			self.ui.line.setTextColor(c)
			colorIcon=QtGui.QPixmap(16,16)
			colorIcon.fill(c)
			self.ui.colorButton.setIcon(QtGui.QIcon(colorIcon))
		else:
			format=self.defaultFormat
			format.setFontItalic(self.ui.line.fontItalic())
			format.setFontUnderline(self.ui.line.fontUnderline())
			format.setFontWeight(self.ui.line.fontWeight())
			fmt=self.ui.line.currentCharFormat()
			#print 'opaque',fmt.background().isOpaque()
			if fmt.background().isOpaque():
				format.setBackground(QtGui.QBrush(fmt.background()))
				self.ui.line.backgroundBrush=fmt.background()
			#self.ui.line.blockSignals(True)
			self.ui.line.reformated=True
			self.ui.line.setCurrentCharFormat(format)
			#self.ui.line.blockSignals(False)
			colorIcon=QtGui.QPixmap(16,16)
			colorIcon.fill(self.defaultFormat.foreground().color())
			self.ui.colorButton.setIcon(QtGui.QIcon(colorIcon))

	def background(self,action):
		"""
		Sets background color according to action.data(). Data should be color like #FFFFFF or string "no" for default system color.
		"""
		if isinstance(action,unicode) or isinstance(action,str):
			color=action
			self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
			#if color.startswith('#'):
				#self.ui.line.backgroundColor=QtGui.QColor(color)
		else:
			color=unicode(action.data().toString())
			#self.ui.line.backgroundColor=QtGui.QColor(color)
			self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
		
		if color.startswith("#") and QtGui.QColor(color)!=self.defaultBackgroundColor:
			#c=QtGui.QColor(color)
			#self.ui.line.setTextColor(c)
			#colorIcon=QtGui.QPixmap(16,16)
			#colorIcon.fill(c)
			#self.ui.colorButton.setIcon(QtGui.QIcon(colorIcon))

			fmt=QtGui.QTextCharFormat()
			fmt.setBackground(QtGui.QBrush(QtGui.QColor(color)))
			self.ui.line.backgroundBrush=fmt.background()
			cursor = self.ui.line.textCursor()
			cursor.mergeCharFormat(fmt)
			self.ui.line.setTextCursor(cursor)
			self.ui.line.mergeCurrentCharFormat(fmt)
			colorIcon=QtGui.QPixmap(16,16)
			#for background color
			colorIcon.fill(QtGui.QColor(color))
			p=QtGui.QPixmap(RESOURCEPATH+"images/16x16/actions/format-text-bold.png")
			painter=QtGui.QPainter(colorIcon)
			painter.drawPixmap(0,0,p)
			painter.end()
			self.ui.backgroundButton.setIcon(QtGui.QIcon(colorIcon))


		else:
			#format=self.defaultFormat
			#format.setFontItalic(self.ui.line.fontItalic())
			#format.setFontUnderline(self.ui.line.fontUnderline())
			#format.setFontWeight(self.ui.line.fontWeight())
			#format.setBackground(QtGui.QBrush(QtGui.QColor(QtCore.Qt.red)))
			#self.ui.line.setCurrentCharFormat(format)
			
			fmt=QtGui.QTextCharFormat()
			fmt.setFontItalic(self.ui.line.fontItalic())
			fmt.setFontUnderline(self.ui.line.fontUnderline())
			fmt.setFontWeight(self.ui.line.fontWeight())
			c=QtGui.QColor(self.ui.line.textColor())
			self.ui.line.backgroundBrush=fmt.background()
			self.ui.line.setCurrentCharFormat(fmt)
			#self.ui.line.backgroundBrush=self.ui.line.currentCharFormat().background()
			if c!=self.defaultColor:
				self.ui.line.setTextColor(c)

			colorIcon=QtGui.QPixmap(16,16)
			#for background color
			colorIcon.fill(self.defaultBackgroundColor)
			p=QtGui.QPixmap(RESOURCEPATH+"images/16x16/actions/format-text-bold.png")
			painter=QtGui.QPainter(colorIcon)
			painter.drawPixmap(0,0,p)
			painter.end()
			self.ui.backgroundButton.setIcon(QtGui.QIcon(colorIcon))

	def clearLine(self):
		format=self.ui.line.currentCharFormat()
		self.ui.line.clear()
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)
		if format.isAnchor():
			self.ui.line.blockSignals(True)
			self.ui.line.reformat()
			self.ui.line.blockSignals(False)
		else:
			self.ui.line.setCurrentCharFormat(format)
		

	def italic(self,bool):
		"""
		Sets italic font according to bool.
		@type bool: boolean
		@param bool: True - italic font
		"""
		self.ui.line.italic=bool
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)

		fmt=QtGui.QTextCharFormat()
		fmt.setFontItalic(bool)
		cursor = self.ui.line.textCursor()
		cursor.mergeCharFormat(fmt)
		self.ui.line.setTextCursor(cursor)
		self.ui.line.mergeCurrentCharFormat(fmt)

	def qtHtmlToXhtml(self,xhtml,text):
		"""
		Converts html from QTextEdit to xhtml-im compatible text.
		@type xhtml: unicode
		@param xhtml: Qt html
		"""
		# remove <style>
		alinks=[]
		a=parseString(unicode(xhtml))
		for el in a.getElementsByTagName('p'):
			if el.hasAttribute("style"):
				el.removeAttribute("style")
		for el in a.getElementsByTagName('body'):
			if el.hasAttribute("style"):
				el.removeAttribute("style")
		for el in a.getElementsByTagName('a'):
			alinks.append(unicode(el.getAttribute('href')))
			alinks.append(unicode(gatherTextNodes(el)))
			for x in el.getElementsByTagName("span"):
				x.removeAttribute("style")
				#print unicode(x.toxml())
		# remove <body>
		b=a.getElementsByTagName('body')
		b=b[0]
		xhtml=b.toxml()
		# TODO: we must replace only first <body> and <p>... not tags in whole message
		xhtml=unicode(xhtml,'utf-8').replace("<body>","").replace("</body>","")#.replace("<p>","<span>").replace("</p>","</span>")
		# TODO: we must use something more secure and faster than replace and for... it's ugly but i don't know
		# better twisted based solution
		if len(xhtml.split("<p>"))==1:
			# only one <p>, so we have to change it to span.
			xhtml=xhtml.replace("<p>","<span>").replace("</p>","</span>")
		else:
			# there are more <p>, so we change </p> to <br/> and remove last <br/>
			xhtml=xhtml.replace("<p>","").replace("</p>","<br/>")
			br=xhtml.split('<br/>') # [a,b,c,d]
			t=""
			for i in range(len(br)):
				if i!=len(br)-1:
					t+=br[i]+"<br/>"
				else:
					t+=br[i]
			xhtml=t
			if xhtml[-5:]=="<br/>":
				xhtml=xhtml[:-5]
		# replace url by <a href="url"></url>
		same=False
		#print xhtml.replace("<br/>",'\n').replace("<br />",'\n')
		#print escape(text)
		if xhtml.replace("<br/>",'\n').replace("<br />",'\n')==escape(text):
			same=True
		links=[]
		#print unicode(xhtml)
		print alinks
		temp=unicode(unescape(xhtml)).replace(">","<")
		for word in temp.split("<"):
			for w in word.split(' '):
				alink=False
				for l in alinks:
					if w.find(l)!=-1:
						alink=True
						break
				if not w in links and not alink:
					#print w
					if w.find("://")!=-1:
						links.append(w.strip())
					elif w.startswith("www."):
						links.append(w.strip())
		print links
		for link in links:
			xhtml=xhtml.replace(link,'<a href="'+link+'">'+link+'</a>')
		#print xhtml
		return xhtml,same
	
	def smileysClicked(self, checked):
		"""
		Shows self.s (QFrame with emoticons).
		"""
		pos=self.ui.smileys.mapToGlobal(QtCore.QPoint(0,0))
		x=pos.x()
		y=pos.y()
		self.main().emoticonsWidget.acceptor=self
		self.main().emoticonsWidget.setGeometry(x-self.main().emoticonsWidget.pixmap.width()/2,y-self.main().emoticonsWidget.pixmap.height(), self.main().emoticonsWidget.pixmap.width(), self.main().emoticonsWidget.pixmap.height())

		self.main().emoticonsWidget.setVisible(checked) 
		
	def underline(self,bool):
		"""
		Sets underline font according to bool.
		@type bool: boolean
		@param bool: True - underline font
		"""
		self.ui.line.underline=bool
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)

		fmt=QtGui.QTextCharFormat()
		fmt.setFontUnderline(bool)
		cursor = self.ui.line.textCursor()
		cursor.mergeCharFormat(fmt)
		self.ui.line.setTextCursor(cursor)
		self.ui.line.mergeCurrentCharFormat(fmt)


	def bold(self,bool):
		"""
		Sets bold font according to bool.
		@type bool: boolean
		@param bool: True - bold font
		"""
		self.ui.line.bold=bool
		self.ui.line.setFocus(QtCore.Qt.OtherFocusReason)

		fmt=QtGui.QTextCharFormat()
		
		if bool==True:
			fmt.setFontWeight(QtGui.QFont.Bold)
		else:
			fmt.setFontWeight(QtGui.QFont.Normal)
		cursor = self.ui.line.textCursor()
		cursor.mergeCharFormat(fmt)
		self.ui.line.setTextCursor(cursor)
		self.ui.line.mergeCurrentCharFormat(fmt)

	def appendLastMessage(self,msg):
		self.lastMessages.append(msg)
		if len(self.lastMessages)>10:
			del self.lastMessages[0]

	def appendXhtml(self,text):
		self.ui.webkit.messageObject.messageCache.insert(0,[0,text])
		if len(self.ui.webkit.messageObject.messageCache)==1 and self.ui.webkit.webkitLoaded:
			self.ui.webkit.messageObjectReady()

	def webkitWrite(self,text,insert=False,ID=""):
		# look for longest-string first; e.g. for styles where both ':)' and ':)]' smileys are defined
		for k in sorted(self.main().emoticonsWidget.smileys.iterkeys(), key=len, reverse=True):
			v = self.main().emoticonsWidget.smileys[k]
			v = os.path.abspath(v)
			text=text.replace(" "+k,'&nbsp;<img alt="'+k+'" src="'+v+'"/>')
			text=text.replace("&nbsp;"+k,'&nbsp;<img alt="'+k+'" src="'+v+'"/>')
			text=text.replace(">"+k,'><img alt="'+k+'" src="'+v+'"/>')
			text=text.replace("	"+k,'<img alt="'+k+'" src="'+v+'"/>')
			text=text.replace("\t"+k,'<img alt="'+k+'" src="'+v+'"/>')
		#print text
		#if self.webkitLoaded:
			#self.messageObject.message.insert(0,unicode(text))
			#if not insert:
				#self.ui.webkit.page().mainFrame().evaluateJavaScript("addMessage(-1);")
			#else:
				#self.ui.webkit.page().mainFrame().evaluateJavaScript("insertMessage(-1);")
		#else:
			#self.messageObject.message.insert(0,unicode(text))
		if not insert:
			self.ui.webkit.messageObject.messageCache.insert(0,[1,text,ID])
		else:
			self.ui.webkit.messageObject.messageCache.insert(0,[0,text,ID])
		if len(self.ui.webkit.messageObject.messageCache)==1 and self.ui.webkit.webkitLoaded:
			self.ui.webkit.messageObjectReady()

	def textEditWrite(self,text,insert=False,ID=""):
		"""
		Appends formated message to the chat view (self.ui.textEdit).
		@type text: unicode
		@param text: formated message
		@type history: boolean
		@param history: True if text is history message (has delay). In this case self.first will not be updated.
		"""
		self.webkitWrite(text,insert)
		return 


	def addEmoticon(self,action):
		"""
		Insert emoticon according to action.objectName() to the self.ui.line. Called when user choose one of emoticons.
		@type action: QAction
		@param action: emotion QAction
		"""
		if isinstance(action,unicode):
			data=action
		else:
			data=action.data()
			data=data.toString()
		if self.main().config['chatMode']=="normal":
			cur=self.ui.line.textCursor()
			cur.insertText(" "+data)
			self.ui.line.setTextCursor(cur)
		else:
			for k,v in self.smileys.iteritems():
				data=data.replace(k,' <img src="'+RESOURCEPATH+'images/16x16/emotes/'+v+'" />')
			self.ui.line.insertHtml(data)
		self.ui.line.setFocus(QtCore.Qt.MouseFocusReason)
	
	def sendButtonClicked(self):
		pass
	
	def on_remove(self):
		pass

	def tabPressed(self):
		pass

