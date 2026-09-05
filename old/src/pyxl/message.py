# -*- coding: utf-8 -*-
import sys,  re
from calendar import timegm
from twisted.python import log
import jid
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
from twisted.web.microdom import escape

class Message:
	def __init__(self, to,  frm = None, body = None,  typ = 'chat',  subject = None,  lang = 'en'):
		self.to = jid.JID(to)
		if frm != None:
			self.frm = jid.JID(frm)
		else:
			self.frm = frm
		self.body = body
		self.typ = typ
		self.subject = subject
		self.composing = None
		self.xhtml = None
		self.evil = False
		self.lang = lang
		self.receiptId = None
		self.attention = False
		self.pep = {}
		self.delay = None
		self.error = None
		self.gpg_encrypted_body = None
		
	
	def toXml(self):
		message = Element((None,'message'))
		message['xml:lang'] = self.lang
		message['to'] = self.to.full()
		if self.frm != None:
			message['from'] = self.frm.full()
		if self.body != None and self.body.strip() != '':
			if self.gpg_encrypted_body != None:
				message.addElement('body', content = 'This message is encrypted.')
				encrypted_message = Element(('jabber:x:encrypted','x'))
				encrypted_message.addContent(self.gpg_encrypted_body)
				message.addChild(encrypted_message)
			else:
				message.addElement('body', content = self.body)
		message['type'] = self.typ

#		if self.groupchats.has_key(JID.userhost()):
#			message['from'] = JID.userhost() + '/' + self.groupchats[JID.userhost()].nick
		if (self.typ=='groupchat' or self.typ == 'normal') and self.subject:
			message.addElement('subject', content = self.subject)
		if self.xhtml != None:
			html = message.addElement('html','http://jabber.org/protocol/xhtml-im')
			body = html.addElement('body', 'http://www.w3.org/1999/xhtml')
			body.addRawXml(self.xhtml)

		if self.composing:
			message.addElement(self.composing, 'http://jabber.org/protocol/chatstates' )

		if self.subject != None:
			message.addElement('subject',  content = self.subject)

		if len(message.children) == 0:
			return None
#		self.on_xml(message.toXml())
		if self.evil and self.body != None and self.body.strip() != '' :
			message.addElement('evil', 'http://jabber.org/protocol/evil')

		if self.receiptId and self.body != None  and self.body != '' and self.typ!='groupchat':
			message['id'] = self.receiptId
			message.addElement('request', 'urn:xmpp:receipts')

		print message.toXml()
		return message

	def setBody(self,  body):
		self.body = body

	def getBody(self):
		return self.body

	def setError(self,  error):
		self.error = error

	def setSubject(self,  subject):
		self.subject = subject

	def setXHTML(self,  xhtml):
		self.xhtml = xhtml

	def setComposing(self,  composing):
		self.composing = composing

	def setDelay(self,  delay):
		self.delay = delay

	def setAttention(self,  attention):
		self.attention = attention

	def setPEP(self, typ, payload):
		self.pep[typ] = payload

	def setFrom(self,  frm):
		self.frm = jid.JID(frm)

	def setGpgEncryptedBody(self,  body):
		self.gpg_encrypted_body = body

	def getGpgEncryptedBody(self):
		return self.gpg_encrypted_body


	def setReceiptId(self,  id):
		self.receiptId = id

	def legacyUnpack(self):
		return (self.frm.full(), self.typ, self.body, self.subject ,  self.xhtml, self.composing ,  self.delay, self.error)

	def legacyUnpackSend(self):
		return (self.to.full(), self.body, self.typ, self.subject,self.composing, self.xhtml,  False)



class MessageInit:
	def __init__(self,  client):
		self.client = client
		self.dispatcher = self.client.dispatcher
		self.client.sendMessage = self.sendMessage

		self.dispatcher.registerHandler('on_message_send', self._sendMessage, 'on_message_send')
	def _sendMessage(self, msg):
		if not (self.client.hasFeature(msg.to.full(), 'http://jabber.org/protocol/xhtml-im') or msg.typ == 'groupchat'):
			msg.setXHTML(None)
			log.err('XHTML-IM filtered while sending message to: '+ msg.to.full())

 		if msg.composing != None:
			try:
				allowComposing = self.main.config['allowChatstate']
			except:
				allowComposing = 'True'
			feature = self.client.hasFeature(msg.to.full(), 'http://jabber.org/protocol/chatstates')
			if not (feature and allowComposing == 'True') or msg.typ == 'groupchat':
				msg.setComposing(None)
				log.err('Composing event filtered while sending message to: '+ msg.to.full())

		xml = msg.toXml()
		if xml != None:
			self.client.xmlstream.send(xml)

	def sendMessage(self, to=None, body=None, typ='chat', subject = None, composing = None, xhtml = None,  muc = False,  msg = None):
		# Posle zpravu na jid
		if msg == None:
			msg = Message(to,  body = body,  typ = typ,  subject = subject,  lang = self.client.xmlLang)
			msg.setComposing(composing)
			msg.setXHTML(xhtml)

#		self.on_xml(message.toXml())
		if self.client.evil :
			msg.evil = True

		if self.client.hasFeature(msg.to.full(), 'urn:xmpp:receipts') and msg.body != None  and msg.body != '' and msg.typ!='groupchat':
			id = "H_%d" % Element._idCounter
			Element._idCounter = Element._idCounter + 1
			msg.setReceiptId(id)
			self.client.messageReceipts[id] = msg
		self.dispatcher.publishEvent('on_message_send', msg)

	def send(self,  xml):
		self.client.xmlstream.send(xml)

	def onMessage(self, el):
		try:
			typ = el['type']
		except:
			typ = 'normal'
		frm = el['from']
		frmjid = jid.JID(frm)
		if frmjid.resource:
			frm=unicode(frmjid.userhost()).lower()+"/"+frmjid.resource
		else:
			frm=unicode(frm).lower()

		msg = Message(self.client.jid.full(), el['from'],  typ = typ)

		body = subject =xhtml = chatstate = delay = error = attention = receipts = pep = event = None
		for child in el.elements():
			if child.name == "request":
				if child.defaultUri == "urn:xmpp:receipts":
					message=Element((None, "message"))
					message["to"] = el["from"]
					message["from"] = self.client.jid.full()
					try:
						message["id"] = el["id"]
					except KeyError:
						pass # kdyby to nejakej chytrak poslal bez id, muze jabbim shodit
					message.addElement("received", "urn:xmpp:receipts")
					self.send(message)
			if child.name == "body":
				body = unicode(child)
				msg.setBody(body)
			if child.name == 'error':
				error = 'error'
				for x in child.elements():
					if x.name != 'text':
						error = x.name
				msg.setError(error)
			if child.name == "subject":
				subject = unicode(child)
				msg.setSubject(subject)
			if child.name == 'html':
				xbody = child.firstChildElement()
				xbody.attributes = {}
				del(xbody.defaultUri)
				del(xbody.uri)
				xhtml = xbody.toXml().replace('<body>','').replace('</body>', '')
				msg.setXHTML(xhtml)
			if child.name in ['active',  'inactive',  'composing',  'paused',  'gone']:
				chatstate = child.name
				try:
					if not 'http://jabber.org/protocol/chatstates' in self.client.roster['users'][frmjid.userhost()].resources[frmjid.resource].features:
						self.client.roster['users'][frmjid.userhost()].resources[frmjid.resource].features.append('http://jabber.org/protocol/chatstates')
				except:
					pass #proste user neni v rosteru, nebo je to muc, nebo cojavim ;)

				msg.setComposing(chatstate)
			if child.name == 'delay':
				# xep-0203:
				#  The format MUST adhere to the dateTime format specified in XEP-0082
				#  and MUST be expressed in UTC.
				stamp = child.getAttribute('stamp')
				m = re.match(r'(\d\d\d\d)-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.\d+)?Z', stamp)
				if m:
					delay = timegm( map(int, m.groups()[0:6]) + [0,0,0] )
					msg.setDelay(delay)
			if child.name == 'x':
				if child.defaultUri == 'jabber:x:delay' :
					# xep-0091:
					#   The format SHOULD be "CCYYMMDDThh:mm:ss"
					#   ... not the format defined in XEP-0082.
					#   The timezone is be understood as UTC.
					stamp = child.getAttribute('stamp')
					m = re.match(r'(\d\d\d\d)(\d\d)(\d\d)T(\d\d):(\d\d):(\d\d)', stamp)
					if m:
						delay = timegm( map(int, m.groups()[0:6]) + [0,0,0] )
						msg.setDelay(delay)
				if child.defaultUri == 'jabber:x:event':
					elm = child.firstChildElement()
					if elm:
						chatstate = elm.name
						msg.setComposing(chatstate)
				if child.defaultUri == 'http://jabber.org/protocol/muc#user': # invitation
					return
				if child.defaultUri == 'http://jabber.org/protocol/rosterx':
					self.client._processRosterX(frm, child)
				if child.defaultUri == 'jabber:x:encrypted':
					gpg_encrypted_body = unicode(child)
					msg.setGpgEncryptedBody(gpg_encrypted_body)

			if child.name == 'confirm': # xep0070 - processed elsewhere
				return

			if child.name == 'attention':
				attention = True
			if child.name == 'received':
				try:
					del self.client.messageReceipts[el['id']]
				except:
					log.err('Couldn\'t remove nonexisten message id')
					return
				print self.client.messageReceipts
				self.client.on_receipt(frmjid, el['id'])
				return

			if child.name == 'event' and child.defaultUri == 'http://jabber.org/protocol/pubsub#event' and typ != 'error':
				log.msg('RAW PUBSUB EVENT')
				log.msg(unicode(el.toXml()).encode('utf8'))
				items = child.firstChildElement()
				itm = items.firstChildElement()
				pep = items.getAttribute('node')

				if itm != None:
					children = []
					for elm in itm.elements():
						children.append(elm)
					if len(children)==1:
						payload = children[0]
					else:
						payload = children

					event = {}
#					for at in payload.elements():
#						event[at.name] = unicode(at)
				else:
					payload = None
				msg.setPEP(pep, payload)
				c = self.client.getContactByJid(frm)
				if c != None:
					c.setPEP(pep, payload) #zapisem si to do kontaktu
				self.dispatcher.publishEvent('on_pep', frm, pep, payload)

			if child.name == 'addresses' and error==None: #xep-0033 - only for remote control (xep-0146) 'ofrom'
				for ads in child.elements():
					if ads.hasAttribute('type') and ads.hasAttribute('jid'):
						if ads.getAttribute('type') == 'ofrom':
							ofrom=ads.getAttribute('jid')
							if frmjid.userhost()==self.client.jid.userhost():#from own jid
								body=u"→→→ %s" % body
							else:
								body=u"→ %s → %s" % (frmjid.full(),body)
							msg.setFrom(ofrom)
							msg.setBody(body)
							self.dispatcher.publishEvent('on_message', msg)
							return

		if error == None and el.getAttribute('type') == 'error':
			error = 'Unknown Error'

		if attention == True and delay == None and typ == 'headline':
			self.dispatcher.publishEvent('on_attention', frm, body, subject, xhtml, error)
			return

		if self.client.groupchats.has_key(jid.JID(frm).userhost()):
#			self.on_GCmessage(frm,typ,body,subject, xhtml,  chatstate,  delay)
			self.dispatcher.publishEvent('on_GCmessage', msg)
		else:
# 			self.on_message(frm,typ,body,subject, xhtml,  chatstate,  delay)
			if typ!="groupchat":
				self.dispatcher.publishEvent('on_message', msg)

	def onInvite(self, el):
		if el['type'] =='error':
			for child in el.elements():
				error = 'error'
				for x in child.elements():
					if x.name != 'text':
						error = x.name
			self.dispatcher.publishEvent('on_GCmessage', el['from'],'error','',None, None,  None, None, error)
			return
		room = el["from"]
		for child in el.children:
			if child.name == "x":
				invite = child.firstChildElement()
				break
		jid = invite["from"]
		reason = None
		cont = False
		for child in invite.children:
			if child.name == "reason":
				reason = unicode(child)
			if child.name == "continue":
				cont = True
		log.msg("invitation recieved to: %s; from %s; reason: %s" % (room, jid, reason))
		self.client.reactor.callFromThread(self.client.on_invite,jid, room, reason, cont)
#		self.main.showInvitation(jid, room, reason, cont)
