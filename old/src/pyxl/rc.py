#-*-encoding:UTF-8-*-

from xdata import *
from adhoc import Stage, CancelStage
from twisted.python import log
import os, sys, re


class fSetStatus(Stage):
	def exec_(self):
		self.status = "executing"
		self.actions = {"cancel":CancelStage, "complete":SetStatus, "execute":SetStatus}
		self.execute = "complete"
	
		sc = self.main.client.roster['users'][self.main.client.jid.userhost()].resources[self.main.client.jid.resource]
		sshow = sc.show
		if sshow == "online":
			sshow = "available"
		show = Field("show", "list-single", self.main.tr("Show: "), options=[
			[self.main.status[status], status] for status in ["available","chat","away","xa","dnd","offline"]
				], values = [sshow])
		status = Field("status", "text-multi", self.main.tr("Status message: "), values = [sc.status or u""])
		priority = Field("priority", "text-single", self.main.tr("Priority"), values = [sc.priority])

		self.xform = Xform("form",fields=[show,status,priority]).buildElement()

class SetStatus(Stage):
	def exec_(self):
		self.status = "completed"
		self.actions = {}
		
		typ = None
		show = self.data["show"][0]
		if show =="available":
			show = 'online'
			self.data["show"][0] = "online"

		status = "\n".join(self.data["status"])
		self.main.sendPresence(
				jid = None,
				show = show,
				message = status,
				pri = self.data["priority"][0],
				)
		icon = self.main.getIcon(self.data["show"][0], size="16x16")
		#self.main.ui.statusButton.setIcon(self.main.getIcon(status=self.data["show"][0], size="16x16"))
		#self.main.ui.showWidget.setText(status)
		
		sc = self.main.client.roster['users'][self.main.client.jid.userhost()].resources[self.main.client.jid.resource]
		sc.show = self.data["show"][0]

		#for muc in self.main.client.groupchats.itervalues():
		#	self.main.client.sendPresence(show = unicode(show), status = unicode(self.data["status"][0]), to = '%s/%s'%(muc.jid, muc.nick))
		self.xform = Xform("result", instructions=[self.main.tr("Status changed.")]).buildElement()

class fLeaveGC(Stage):
	def exec_(self):
		self.status = "executing"
		self.actions = {"cancel":CancelStage, "complete":LeaveGC, "execute":LeaveGC}
		self.execute = "complete"

		gcop = [[key, key] for key in self.main.client.groupchats.keys()]
		
		field = Field("groupchats", "list-multi", self.main.tr("Groupchats to leave: "), options=gcop)
		self.xform = Xform("form", fields=[field], title=self.main.tr("Leave groupchats"),instructions=[self.main.tr("Choose groupchats you want remote client to leave.")]).buildElement()

class LeaveGC(Stage):
	def exec_(self):
		self.status = "completed"
		self.actions = {}
		
		for gc in self.data["groupchats"]:
			tab,index=self.main.chat.findTab(gc) 
			if tab != None:
				self.main.chat.ui.chatTab.setCurrentIndex(index)
				self.main.chat.removeTab(ask=False)
		self.xform = Xform("result", instructions=[self.main.tr("Groupchats left.")]).buildElement()

class ResendFile(Stage):
	def exec_(self):
		self.status = "executing"
		self.actions = {"cancel":CancelStage, "next":ResendFile, "execute":ResendFile}
		self.execute = "next"

		files = []
		dirs = []
		if self.data == None:
			pwd = self.main.homeDir  #pwd = os.environ["PWD"]
			jid=self.session.jid
		elif os.path.isdir(os.path.join(self.data["pwd"][0], self.data["dir"][0]))!=False and len(self.data["files"])==0 and len(self.data["dir"]) != 0:
			if self.data["dir"][0] == os.path.pardir:
				pwd = os.path.split(self.data["pwd"][0])[0]
			else:
				pwd = os.path.join(self.data["pwd"][0], self.data["dir"][0])
			jid=self.data['jid'][0]
		else:
			for file in self.data["files"]:
				f = os.path.join(self.data["pwd"][0], file)
				self.main.events.addFTUploadEvent(self.session.jid, [f], {f:unicode(self.main.tr("Sent via remote controlling"))})
			self.status = "completed"
			self.execute = None
			self.actions={}
			self.xform = None
			self.xform = Xform("form", fields=[], title=self.main.tr("Resend file"),instructions=[self.main.tr("File(-s) was sent")]).buildElement()
			return
		for f in os.listdir(pwd):
			if os.access(os.path.join(pwd,f), os.R_OK):
				if os.path.isfile(os.path.join(pwd,f)):
					files.append(["%s (%s)" % (f,self.main.utils.getNormalSize(os.path.getsize(pwd+os.path.sep+f))), f])
				else:
					dirs.append(["%s%s" % (f, os.path.sep), f])
		files.sort()
		dirs.sort()
		dirs.insert(0, ["%s%s (%s)" % (os.path.pardir, os.path.sep, self.main.tr("One directory up")), os.path.pardir])
		#dirs.extend(files)

		field_jid = Field("jid", "text-single", self.main.tr("Send file to (full) JID: "), required=False, values=[jid])
		
		field_dir = Field("dir", "list-single", self.main.tr("Choose directory: "), required=False, options=dirs)
		
		field_file = Field("files", "list-multi", self.main.tr("Choose file(-s): "), required=False, options=files)
		
		#field_zip = Field("files", "boolean", self.main.tr("Compress with ZIP to one file: "), required=False)
		
		field2 = Field("pwd", "hidden", values=[pwd])
		self.xform = Xform("form", fields=[field_jid, field_dir, field_file,  field2], title=self.main.tr("Resend file"),instructions=[self.main.tr("Choose file you want to resend from remote system or directory you want to browse."),"PWD: %s" % pwd]).buildElement()
		
class ForwardMsg(Stage):
	def exec_(self):
		self.status = "executing"
		self.actions = {"cancel":CancelStage, "next":ForwardMsg, "execute":ForwardMsg}
		
		count=0
		opt=[]
		message_from={}
		msg_arch={}
		msg_null={}
		
		if self.main.plugins.get('archive')==None:
			self.xform = Xform("form", fields=[], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("You must enable archive plugin for forward unread messages")]).buildElement()
			return
		elif self.main.plugins['archive'].get('module')==None:
			self.xform = Xform("form", fields=[], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("You must enable archive plugin for forward unread messages")]).buildElement()
			return
			
		for i in range(self.main.chat.ui.chatTab.count()):
			w=self.main.chat.ui.chatTab.widget(i)
			if w.typ == 'chat':
				coutmsg=w.chat.unread
				count=count+coutmsg
				jid=self.main.getJid(w.jid).userhost()
				msg_null[jid]=w
				if message_from.has_key(jid): # join all chat jid resources
					message_from[jid]=message_from[jid]+coutmsg
					if msg_arch.has_key(jid):
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
					else:
						msg_arch[jid]=[]
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
				else:
					message_from[jid]=coutmsg
					if msg_arch.has_key(jid):
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
					else:
						msg_arch[jid]=[]
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
				#for msg in w.chat.lastMessages:
					#if msg[0]=='in':
						#print w.jid
						#print re.sub("<[^>]*>","",msg[2])
						#print msg[3]
			elif w.typ == 'groupchat':
				#print w.chat.unread
				coutmsg=w.chat.unread
				w.chat.unread=0
				count=count+coutmsg
				jid=self.main.getJid(w.jid).full()
				msg_null[jid]=w
				if message_from.get(jid)==None: # join all jid resources, not for MUC !
					message_from[jid]=coutmsg
					if msg_arch.has_key(jid):
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
					else:
						msg_arch[jid]=[]
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
				else:
					message_from[jid]=message_from[jid]+coutmsg
					if msg_arch.has_key(jid):
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
					else:
						msg_arch[jid]=[]
						msg_arch[jid].append(self.main.plugins['archive']['module'].backend.getLastMessages(jid,coutmsg,"0:0:0"))
		
		if count==0:
			self.xform = Xform("form", fields=[], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("You have no unread messages")]).buildElement()
			return
		
		if self.data==None:
			for x in message_from:
				if message_from[x]>0:
					opt.append([unicode(x)+" - "+self.main.tr("%s message" % str(message_from[x])), unicode(x)])
			field_all = Field("fw_all", "boolean", self.main.tr("Forward all %s unread messages: " % count), required=False, values=[0])
			field_chats = Field("who", "list-multi", self.main.tr("Choose unread messages: "), required=False, options=opt)
			self.xform = Xform("form", fields=[field_all, field_chats], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("%s" % self.main.chat.ui.chatTab.count())]).buildElement()
		elif (self.data.get('who')==[] and self.data.get('fw_all')==['0']) or self.data.get('e')==['0']:
			for x in message_from:
				if message_from[x]>0:
					opt.append([unicode(x)+" - "+self.main.tr("%s message" % str(message_from[x])), unicode(x)])
			field_all = Field("fw_all", "boolean", self.main.tr("Forward all %s unread messages: " % count), required=False, values=[0])
			field_chats = Field("who", "list-multi", self.main.tr("Choose unread messages: "), required=False, options=opt)
			self.xform = Xform("form", fields=[field_all, field_chats], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("%s" % self.main.chat.ui.chatTab.count())]).buildElement()
		else:
			for x in msg_arch:
				if (self.data.get('fw_all',[''])[0]=='1' or self.data.get('fw_all',[''])[0]=='true') or (x in self.data.get('who',[])):
					for y in range(message_from[x]):
						message=Element((None, "message"))
						message["to"] = self.session.jid
						message["from"] = self.main.client.jid.full()
						#message["id"] =
						body=message.addElement("body", content=msg_arch[x][0][y][3])
						
						d = message.addElement('delay', 'urn:xmpp:delay')
						d['stamp']=self.main.utils.getStampFromFormat(msg_arch[x][0][y][0],'sec')
						
						addresses=message.addElement("addresses", "http://jabber.org/protocol/address")
						address=addresses.addElement("address", None)
						address['type'] = 'ofrom'
						address['jid'] = x
						self.main.client.xmlstream.send(message)
						#print "sending:", message.toXml()
					if msg_null[x].chat.unread>0:
						#'['+self.main.now()+']')+
						m=unicode(self.main.tr("Last %s messages were forwarded to " % msg_null[x].chat.unread) + self.session.jid)
						write_message=self.main.webkitThemeFactory.genGroupchatAction(unicode(m),self.main.now())
						msg_null[x].chat.textEditWrite(write_message)
						msg_null[x].chat.unread=0
					
			try:
				message
				field = Field("e", "hidden", values='0')
				self.xform = Xform("form", fields=[field], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("Selected unread messages were sent.")]).buildElement()
			except:
				field = Field("e", "hidden", values='0')
				self.xform = Xform("form", fields=[field], title=self.main.tr("Forward unread messages"),instructions=[self.main.tr("No selected messages")]).buildElement()
			
