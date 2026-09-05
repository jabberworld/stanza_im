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
import sys, os, time
from twisted.internet import threads
from include.constants import RESOURCEPATH

class webkitThemeFactory:
	def __init__(self,chatTheme,groupchatTheme,realHomeDir):
		self.fullChatTheme=chatTheme
		self.fullGroupchatTheme=groupchatTheme
		self.realHomeDir=realHomeDir
		self.load()

	def genChatHtml(self,messages,me,user,myAvatar,userAvatar,widget):
		templates={}
		templates['incomingContent'] = self.incomingContent.replace("%sender%",user).replace("%userIconPath%",userAvatar).replace("%highlight%","").replace('id="insert"','id="insert2"')
		templates['incomingNextContent'] = self.incomingNextContent.replace("%sender%",user).replace("%userIconPath%",userAvatar).replace("%highlight%","").replace('id="insert"','id="insert2"')
		templates['outgoingContent'] = self.outgoingContent.replace("%sender%",me).replace("%userIconPath%",myAvatar).replace("%highlight%","").replace('id="insert"','id="insert2"')
		templates['outgoingNextContent'] = self.outgoingNextContent.replace("%sender%",me).replace("%userIconPath%",myAvatar).replace("%highlight%","").replace('id="insert"','id="insert2"')
		# call getLastMessages in thread
		#d=threads.deferToThread(self._genChatHtml,messages,templates)
		#return d

	#def _genChatHtml(self,messages,templates):
		html=""
		lastFromMe=None
		for msg in messages:
			d=time.localtime(msg[0]) # date
			t=self.formatTime(d[3],d[4],d[5]) # formated time
			if msg[1]!='to':
				if lastFromMe==True:
					widget.ui.webkit.messageObject.historyMessages.insert(0,[0,templates['incomingNextContent'].replace("%message%",msg[3]).replace("%time%",t)])
				else:
					lastFromMe=True
					widget.ui.webkit.messageObject.historyMessages.insert(0,[1,templates['incomingContent'].replace("%message%",msg[3]).replace("%time%",t)])
				#html+=my_message.replace("[time]",t).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",msg[3]).replace("<br/><br/>","<br/>").replace('[avatar]',selfavatar)
			else:
				#if user:
				#	who=user
				#else:
				#	who=msg[2]
				#html+=message.replace("[time]",t).replace("[user]",who.replace("<","&lt;").replace(">","&gt;").replace("\n","<br/> ")).replace("[message]",msg[3]).replace("[foreground]",color[0]).replace("[background]",color[1]).replace("<br/><br/>","<br/>").replace('[avatar]',avatar)
				if lastFromMe==False:
					widget.ui.webkit.messageObject.historyMessages.insert(0,[0,templates['outgoingNextContent'].replace("%message%",msg[3]).replace("%time%",t)])
				else:
					lastFromMe=False
					widget.ui.webkit.messageObject.historyMessages.insert(0,[1,templates['outgoingContent'].replace("%message%",msg[3]).replace("%time%",t)])
		if widget.ui.webkit.webkitLoaded:
			widget.ui.webkit.page().mainFrame().evaluateJavaScript("addHistoryMessages();")

	def formatTime(self,h,m,s):
		"""
		Returns formated time in format hh:mm:ss from integers.
		"""
		text=""
		for item in [h,m,s]:
			if item<10:
				text+="0"+str(item)+":"
			else:
				text+=str(item)+":"
		return text[:-1]

	def load(self):
		self.chatTheme,self.chatStyle=self.fullChatTheme.split("/")
		self.groupchatTheme,self.groupchatStyle=self.fullGroupchatTheme.split("/")
		print "loading chatTheme",self.chatTheme,self.chatStyle
		print "loading groupchatTheme",self.groupchatTheme,self.groupchatStyle

		#print self.realHomeDir, self.gPath, self.cPath
		self.cPath = os.path.abspath(RESOURCEPATH)+"/chatskins/%s/" % self.chatTheme
		if not os.path.exists(self.cPath + "Incoming/Content.html"):
			self.cPath = self.realHomeDir + "/chatskins/%s/" % self.chatTheme
		self.gPath = os.path.abspath(RESOURCEPATH)+"/chatskins/%s/" % self.groupchatTheme
		if not os.path.exists(self.gPath + "Incoming/Content.html"):
			self.gPath = self.realHomeDir + "/chatskins/%s/" % self.groupchatTheme
		#print self.realHomeDir, self.gPath, self.cPath
		print os.path.abspath(RESOURCEPATH)+"/chatskins/%s/" % self.chatTheme
		try:
			f=open(self.cPath+"Incoming/Content.html","r")
			self.incomingContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.incomingContent=None

		try:
			f=open(self.cPath+"Incoming/NextContent.html","r")
			self.incomingNextContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.incomingNextContent=None

		try:
			f=open(self.cPath+"Outgoing/Content.html","r")
			self.outgoingContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.outgoingContent=None

		try:
			f=open(self.cPath+"Outgoing/NextContent.html","r")
			self.outgoingNextContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.outgoingNextContent=None

		try:
			f=open(self.gPath+"Incoming/Content.html","r")
			self.incomingGroupchatContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.incomingGroupchatContent=None

		try:
			f=open(self.gPath+"Incoming/NextContent.html","r")
			self.incomingGroupchatNextContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.incomingGroupchatNextContent=None

		try:
			f=open(self.gPath+"Outgoing/Content.html","r")
			self.outgoingGroupchatContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.outgoingGroupchatContent=None

		try:
			f=open(self.gPath+"Outgoing/NextContent.html","r")
			self.outgoingGroupchatNextContent = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.outgoingGroupchatNextContent=None
		
		try:
			f=open(self.gPath+"Status.html","r")
			self.groupchatStatus = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.groupchatStatus=None

		try:
			f=open(self.cPath+"Status.html","r")
			self.chatStatus = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.chatStatus=None

		try:
			f=open(self.cPath+"Footer.html","r")
			self.chatFooter = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.chatFooter=None

		try:
			f=open(self.gPath+"Footer.html","r")
			self.groupchatFooter = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.groupchatFooter=None

		try:
			f=open(self.cPath+"Header.html","r")
			self.chatHeader = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.chatHeader=None

		try:
			f=open(self.gPath+"Header.html","r")
			self.groupchatHeader = unicode(f.read(), 'utf-8')
			f.close()
		except:
			self.groupchatHeader=None

		try:
			f=open(self.gPath+"Incoming/SenderColors.txt","r")
			self.groupchatSenderColors=f.read().replace("\n","").split(":")
			f.close()
		except:
			self.groupchatSenderColors=["#a34526","#c000ff","#045723","#7c7c7c","#ff8a00","#94452d"]

	def getGroupchatSenderColor(self,i):
		if not i:
			return ""
		colors=self.groupchatSenderColors
		if len(colors)==1:
			return colors[0]
		if i>len(colors)-1:
			return colors[i%(len(colors)-1)]
		else:
			return colors[i]

	def genChatHeader(self,name="",avatar=""):
		if not self.chatHeader:
			return ""
		return self.chatHeader.replace("%chatName%",name).replace("%incomingIconPath%",avatar)

	def genGroupchatHeader(self,name=""):
		if not self.groupchatHeader:
			return ""
		return self.groupchatHeader.replace("%chatName%",name)

	def genChatFooter(self):
		if not self.chatFooter:
			return ""
		return self.chatFooter

	def genGroupchatFooter(self):
		if not self.groupchatFooter:
			return ""
		return self.groupchatFooter

	def chatPath(self):
		return self.cPath

	def groupchatPath(self):
		return self.gPath

	def genChatStatus(self,message,time):
		if not self.chatStatus:
			return ""
		return self.chatStatus.replace("%status%","online").replace("%time%",time).replace("%message%",message)

	def genGroupchatStatus(self,message,time):
		if not self.groupchatStatus:
			return ""
		return self.groupchatStatus.replace("%status%","online").replace("%time%",time).replace("%message%",message)

	def genGroupchatAction(self,message,time):
		if not self.groupchatStatus:
			return ""
		return self.groupchatStatus.replace("%status%","").replace("%time%",time).replace("%message%",message)

	def genChatStyleSheet(self):
		return '@import url( "Variants/%s" );' % self.chatStyle

	def genGroupchatStyleSheet(self):
		return '@import url( "Variants/%s" );' % self.groupchatStyle

	# Groupchat format

	def genGroupchatIncomingContent(self,user,message,time,avatar="",color=None,highlight=""):
		print self.incomingGroupchatContent
		return self.incomingGroupchatContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%senderColor%",self.getGroupchatSenderColor(color)).replace("%highlight%",highlight).replace("%message%",message)

	def genGroupchatIncomingNextContent(self,user,message,time,avatar="",color=None,highlight=""):
		return self.incomingGroupchatNextContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%senderColor%",self.getGroupchatSenderColor(color)).replace("%message%",message)

	def genGroupchatOutgoingNextContent(self,user,message,time,avatar="",color=None):
		return self.outgoingGroupchatNextContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%senderColor%",self.getGroupchatSenderColor(color)).replace("%highlight%","").replace("%message%",message)
	
	def genGroupchatOutgoingContent(self,user,message,time,avatar="",color=None):
		return self.outgoingGroupchatContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%senderColor%",self.getGroupchatSenderColor(color)).replace("%highlight%","").replace("%message%",message)

	# Chat format

	def genIncomingContent(self,user,message,time,avatar=""):
		return self.incomingContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%highlight%","").replace("%message%",message)
	def genIncomingNextContent(self,user,message,time,avatar=""):
		return self.incomingNextContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%highlight%","").replace("%message%",message)

	def genOutgoingNextContent(self,user,message,time,avatar=""):
		return self.outgoingNextContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%highlight%","").replace("%message%",message)
	
	def genOutgoingContent(self,user,message,time,avatar=""):
		return self.outgoingContent.replace("%sender%",user).replace("%time%",time).replace("%userIconPath%",avatar).replace("%highlight%","").replace("%message%",message)
