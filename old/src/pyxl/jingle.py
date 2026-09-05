import sys,  re,  time,  random
from calendar import timegm
from twisted.python import log
import jid
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
from base64 import b64encode, b64decode
from twisted.protocols import socks
from twisted.words.protocols.jabber.xmlstream import IQ, TimeoutError
from twisted.internet.protocol import Protocol, ClientFactory, Factory
from socket import getaddrinfo
import socks5, events, base64
from twisted.internet import threads, defer, reactor

import ft


class JingleInit:
	def __init__(self,  client):
		self.client = client
		self.dispatcher = self.client.dispatcher
		self.ft = self.client.ft
		self.main = self.client.main
		self.disp = self.client.disp
		self.xmlLang = self.client.xmlLang
		self.chyba = self.client.chyba
		self.sessions = {}

	def send(self,  xml):
		self.client.xmlstream.send(xml)

	def onJingleInitiate(self,   el):
		print 'jingle session received'
		self.disp(el['id'])
		payload = el.firstChildElement()
		sid =  payload['sid']
		contents = []
		for e in payload.elements():
			contents.append(self.getContent(e))
		print contents
		obj = JingleSession(self, jid.JID(el['to']), jid.JID(el['from']), payload['sid'],  contents)
		self.sessions[payload['sid']] = obj
		obj.ack(el['id'], el['to'], el['from'])
		if contents[0].description =='urn:xmpp:tmp:jingle:apps:file-transfer':
			print self.client.jid.full(), el['from']
			self.client.ft[sid] = ft.FT( self.client.jid.full(), el['from'] , self.client.FT,  contents[0].fileprops,  filepath=None, sid =sid, typ='jingle')
			self.ft[sid].sessionObj = ft.Jingle(self.ft[sid])
			if contents[0].transport == 'urn:xmpp:tmp:jingle:transports:ibb':
				self.ft[sid].sessionObj.transportReady = True
			self.ft[sid].mode = 'receive'
			self.client.on_fileReceived(sid, el['id'])
			self.dispatcher.publishEvent('FTStartedEvent', sid, el['id'])

	def onJingleAccept(self,   el):
		print 'jingle session-accept received'
		self.disp(el['id'])
		payload = el.firstChildElement()
		sid =  payload['sid']
		contents = []
		for e in payload.elements():
			contents.append(self.getContent(e))
		self.sessions[sid].onAcceptSession(contents)
		self.sessions[sid].ack(el['id'],  el['to'], el['from'])

	def onJingleContentReplace(self,   el):
		print 'jingle content-replace received'
		self.disp(el['id'])
		payload = el.firstChildElement()
		sid =  payload['sid']
		contents = []
		for e in payload.elements():
			contents.append(self.getContent(e))
		self.sessions[sid].onContentReplace(contents)
		self.sessions[sid].ack(el['id'], el['to'], el['from'])

	def onJingleTerminate(self,   el):
		print 'jingle session-terminate received'
		self.disp(el['id'])
		payload = el.firstChildElement()
		sid =  payload['sid']
		try:
			reason = payload.firstChildElement().firstChildElement().name
		except:
			reason = None
		self.sessions[sid].onTerminateSession(reason)
		self.sessions[sid].ack(el['id'], el['to'], el['from'])


	def getContent(self,  xml):
		creator = xml['creator']
		name = xml['name']
		for el in xml.elements():
			if el.name == 'description':
				props = {}
				profile = el.defaultUri
				if profile == 'urn:xmpp:tmp:jingle:apps:file-transfer':
					e = el.firstChildElement().firstChildElement()
					props.update(e.attributes)
					props['type'] = e.name
					for elm in e.elements():
						if elm.name == 'preview':
							props['preview'] = unicode(elm)
							props['previewType'] = elm.getAttribute('type', 'image/jpeg')
						elif elm.name == 'desc':
							props['desc'] = unicode(elm)
			elif el.name == 'transport':
				transport = self.getTransport(el)
		return Content(creator,  name, profile ,  transport,  props)

	def getTransport(self,  el):
		if el.defaultUri == 'urn:xmpp:tmp:jingle:transports:raw-udp':
			return UDPTransport(el)
		elif el.defaultUri == 'urn:xmpp:tmp:jingle:transports:bytestreams' or el.defaultUri == 'urn:xmpp:tmp:jingle:transports:ibb':
			return FTTransport().fromXml(el)


class Transport:
	def getType(self):
		return self.typ
	def toXml(self):
		return Element((self.typ,  'transport'))

class FTTransport(Transport):
	def fromXml(self,  el):
		self.typ = el.defaultUri
		return self

	def fromString(self,  typ):
		self.typ = typ
		return self

class UDPTransport(Transport):
	def __init__(self,  el):
		self.typ = el.defaultUri
		self.candidates = []
		for e in el.elements():
			self.candidates.append(e.attributes)

	def toXml(self):
		el = Element((self.typ,  'transport'))
		for candidate in self.candidates:
			c = el.addElement('candidate')
			c.attributes.update(candidate)
		return el

class Content:
	def __init__(self,  creator,  name,  description,  transport,  props={}):
		self.creator = creator
		self.name = name # zatim nevim k cemu to presne je, jmeno souboru je v FT payloadu
		self.description = description # co vlastne budem prenaset
		self.transport = transport
		self.fileprops = props #pro FT


	def __str__(self):
		return self.toXml().toXml()

	def __repr__(self):
		return '%s: %s %s'%(self.description.split(':')[-1],  self.transport.getType().split(':')[-1],  unicode(self.fileprops))

	def toXml(self):
		content = Element((None, 'content'))
		content['creator'] = self.creator
		content['name'] = self.name
		if self.description == 'urn:xmpp:tmp:jingle:apps:file-transfer':
			file = content.addElement('description', self.description).addElement(self.fileprops['type']).addElement('file', 'http://jabber.org/protocol/si/profile/file-transfer')
			preview = None
			for k, v in self.fileprops.iteritems():
				if k == 'desc':
					if len(v) != 0:
						file.addElement('desc',  content = v)
				elif k.startswith('preview'):
					continue #nekde je to borken
#					if preview == None:
#						preview = file.addElement('preview')
#					if k == 'preview':
#						preview.addContent(v)
#					else:
#						preview['type'] = v
				elif k=='type':
					continue
				else:
					file[k] = unicode(v)

		content.addChild(self.transport.toXml())
		return content


class JingleSession:
		def __init__(self,  init,  tojid,  fromjid, sid,  contents = []):
			self.tojid = tojid
			self.fromjid = fromjid
			self.init = init
			self.role = None
			self.contents = contents
			self.state = 'PENDING'
			self.sessionState = 'session-initiate' # session-accept, session-terminate, session-info
			self.sid = sid

		def createFTContent(self,  transport, props):
			print 'create FT!'
			print self.contents
			props['type'] = 'offer'
			trans = FTTransport()
			trans.fromString(transport)
			content = Content('initiator',  'file offer',  'urn:xmpp:tmp:jingle:apps:file-transfer', trans ,  props)
			self.contents=[content]
			print content.__str__()
			print unicode(content)


		def initSession(self):
			self.role = 'initiator'
			iq = IQ(self.init.client.xmlstream, 'set')
			iq['to'] = self.tojid.full()
			#iq['from'] = self.fromjid.full()
			jingle = iq.addElement('jingle', 'urn:xmpp:tmp:jingle' )
			jingle['action'] = 'session-initiate'
			jingle['initiator'] = self.fromjid.full()
			jingle['sid'] = self.sid
			for content in self.contents:
				jingle.addChild(content.toXml())
			self.init.disp(iq['id'])
			d = iq.send()
			d.addCallback(self._initAck)

		def _initAck(self,  res):
			print 'ack received'
			if self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:bytestreams':
				self.init.client.FT.socksSend(self.sid)
			elif self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:ibb':
				self.init.client.FT.ibbSend(self.sid)


		def acceptSession(self):
			iq = IQ(self.init.client.xmlstream, 'set')
			iq['to'] = self.fromjid.full()
			#iq['from'] = self.tojid.full()
			jingle = iq.addElement('jingle', 'urn:xmpp:tmp:jingle' )
			jingle['action'] = 'session-accept'
			jingle['initiator'] = self.fromjid.full()
			jingle['sid'] = self.sid
			for content in self.contents:
				jingle.addChild(content.toXml())
			self.init.disp(iq['id'])
			print iq.toXml()
			d = iq.send()

		def terminateSession(self,  reason = None):
			self.state = 'ENDED'
			iq = IQ(self.init.client.xmlstream, 'set')
			if self.fromjid != self.init.client.jid:
				iq['to'] = self.fromjid.full()
				#iq['from'] = self.tojid.full()
			else:
				#iq['from'] = self.fromjid.full()
				iq['to'] = self.tojid.full()
			jingle = iq.addElement('jingle', 'urn:xmpp:tmp:jingle' )
			jingle['action'] = 'session-terminate'
			jingle['initiator'] = self.fromjid.full()
			jingle['sid'] = self.sid
			if reason != None:
				jingle.addElement('reason').addElement(reason)
			self.init.disp(iq['id'])
			print iq.toXml()
			d = iq.send()

		def onAcceptSession(self, contents):
			# muze se content zmenit v session-accept? musi se to predat?
			print self.contents, contents
			if self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:bytestreams':
				self.init.client.ft[self.sid].sessionObj.humanReady = True
			elif self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:ibb':
				self.init.client.ft[self.sid].sessionObj.humanReady = True


		def onTerminateSession(self,  reason):
			self.state = 'ENDED'
			if self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:bytestreams':
				self.init.client.FT.on_ftEnd(self.sid,  reason)
			elif self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:ibb':
				self.init.client.FT.on_ftEnd(self.sid,  reason)

		def contentReplace(self,  content):
			iq = IQ(self.init.client.xmlstream, 'set')
			if self.fromjid != self.init.client.jid:
				iq['to'] = self.fromjid.full()
				#iq['from'] = self.tojid.full()
			else:
				#iq['from'] = self.fromjid.full()
				iq['to'] = self.tojid.full()
			jingle = iq.addElement('jingle', 'urn:xmpp:tmp:jingle' )
			jingle['action'] = 'content-replace'
			jingle['initiator'] = self.fromjid.full()
			jingle['sid'] = self.sid
			jingle.addChild(content.toXml())
			self.init.disp(iq['id'])
			print iq.toXml()
			d = iq.send()

		def onContentReplace(self,  contents):
			self.contents = contents
			if self.contents[0].transport.getType() == 'urn:xmpp:tmp:jingle:transports:ibb':
				self.init.client.FT.ibbSend(self.sid)

		def ack(self,  id, frm, to):
			print 'ack'
			iq = Element((None,'iq'))
			iq['to'] = to
			#iq['from'] = frm
			iq['id'] = id
			iq['type'] = 'result'
			self.init.send(iq)

