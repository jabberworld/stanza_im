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
import socket
from xmlrpclib import loads, dumps

from twisted.internet import defer, threads
from twisted.python import log
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.words.xish.domish import Element

import jid
from groupchat import Groupchat
from xdata import Field, Xform


MUCLISTTYPES = {
'voice': ('http://jabber.org/protocol/muc#admin', 'participant', 'role'),
'ban': 	('http://jabber.org/protocol/muc#admin', 'outcast', 'affiliation'),
'member': ('http://jabber.org/protocol/muc#admin', 'member', 'affiliation'),
'moderator': ('http://jabber.org/protocol/muc#admin', 'moderator', 'role'),
'owner': 	('http://jabber.org/protocol/muc#admin', 'owner', 'affiliation'),
'admin': 	('http://jabber.org/protocol/muc#admin', 'admin', 'affiliation')}
class derived:
	def on_authFailed(self,xmlstream):
		pass
	def on_init(self):
		pass
	def on_presence(self,frm,show, error=None):
		pass
	def on_GCpresenceError(self,  fromjid,  code,  type,  name, text):
		pass
	def on_firstpresence(self,  bulk):
		for pres in bulk:

			self.on_presence(pres[0], pres[1])
		pass
	def on_privacyFail(self):
		pass
	def on_bookmarksFail(self):
		pass
	def on_shutdown(self):
		pass
	def on_xml(self, xml):
		pass
	def on_authd(self):
		pass
	def on_metaFail(self, err):
		pass
	def on_UpdateContact(self,jid):
		pass
	def on_DeleteContact(self,jid):
		pass

	def on_subscribe(self,kdo, msg):
		pass
	def on_unsubscribe(self, kdo):
		pass
	def on_unsubscribed(self, kdo):
		pass
	def on_subscribed(self, kdo):
		pass
	def on_unavailable(self,frm):
		pass

	def on_message(self, msg):
		pass
	def on_GCmessage(self, msg):
		pass

	def on_GCpresence(self,  muc, nick,  show,  status,  codes = [], reason = '', actor = None,n=None):
		pass

	def on_versionreceive(self, jid, version):
		#version = (name, version, os)
		pass

	def on_discoInfoReceived(self, jid, node):
		# v self.disco[jid][(jid,node)] jsou info data nebo error
		pass
	def on_discoItemsReceived(self, jid, node):
		# v self.disco[jid][(jid,node)] jsou info data nebo error
		pass

	def on_privacyReceived(self):

		pass

	def on_time202Received(self, jid, utc, tzo):
		pass

	def on_rosterAddUser(self, contact):
		pass

	def on_rosterArrived(self):
		pass

	def on_roleErr(self,  muc,  err,  nick):
		pass

	def on_affiliationErr(self,  muc,  err,  nick):
		pass
	def on_vcardReceived(self,  jid, card):
		pass

	def on_fileReceived(self, jid, file, methods, id):
		pass

	def on_ftEnd(self, sid, error = None): #pokud je error None je vse v poradku, jinak strucny popis chyby.
		del self.ft[sid]

	def on_ftTransfered(self, sid, bytes): #pocet prenesenych bajtu pro prenos se SID
		pass

	def on_disconnect(self):
		pass

	def on_verify(self, id, thread, props, frm, typ): #xep0070
		self.replyVerify(id, thread, props, frm, typ, False)
		pass
	def on_connect(self):
		pass
	def on_invite(self, jid, room, reason = None, cont = False):
		pass

	def on_avatarUpdate(self, jid):
		pass

	def on_rosterx(self,frm, out, id, typ):
		pass

	def on_pep(self, frm, ns, payload):
		pass

	def on_receivedFiles(self, id,  frm,  files, size):
		pass

	def on_receipt(self, frm, id):
		pass
		########################################################################################################################

	########################################################################################################################
	def sendPresence(self, to = None, show = None, status = None, priority = None, typ = None, caps = True):
		"""Posle presenci na zvoleny jid"""
		presence = Element((None, 'presence'))
		presence['xml:lang'] = self.xmlLang
		presence['from'] = self.jid.full()
		if to:
			presence['to'] = to
		else:
			self.roster['users'][self.jid.userhost()].setStatus(self.jid.resource, show, status)
		if status:
			presence.addElement('status', content = status)
		if show:
			if show == 'offline':
				typ = 'unavailable'
			elif show == 'online':
				pass
			else:
				presence.addElement('show', content = show)
		if priority:
			presence.addElement('priority', content = unicode(priority))
		if typ:
			presence['type'] = typ
		if caps:
			c = presence.addElement('c', 'http://jabber.org/protocol/caps')
			c['node'] = self.caps_node
			if self.caps_ext != None:
				c['ver'] = self.caps_ext
				c['hash'] = 'sha-1'

		x = presence.addElement('x', 'vcard-temp:x:update')
		if self.main.avatarDef.has_key(self.jid.userhost()) and self.main.avatarDef[self.jid.userhost()] != 'None':
			x.addElement('photo', content = self.main.avatarDef[self.jid.userhost()])
		else:
			x.addElement('photo')

		log.msg('sending out presence to: ' + unicode(to))
#		self.on_xml(presence.toXml())
		if self.evil :
			presence.addElement('evil', 'http://jabber.org/protocol/evil')
		self.xmlstream.send(presence)






	def sendInvitation(self, jid, room, reason = None, cont = False):
		message = Element((None,'message'))
		message['xml:lang'] = self.xmlLang
		message['to'] = room
		x = message.addElement('x','http://jabber.org/protocol/muc#user')
		invite =  x.addElement('invite')
		invite['to'] = unicode(jid)
		if reason != None:
			invite.addElement("reason", content = unicode(reason))
		if cont:
			invite.addElement("continue")

#		self.on_xml(message.toXml())
		self.xmlstream.send(message)


	def declineInvitation(self, jid, room, reason = None):
		message = Element((None,'message'))
		message['xml:lang'] = self.xmlLang
		message['to'] = room
		x = message.addElement('x','http://jabber.org/protocol/muc#user')
		decline =  x.addElement('decline')
		decline['to'] = unicode(jid)
		if reason != None:
			decline.addElement("reason", content = unicode(reason))

#		self.on_xml(message.toXml())
		self.xmlstream.send(message)

	def sendPEP(self,  ns,  payload): #paylod is Element node or list of nodes
		iq = IQ(self.xmlstream, 'set')
		pb = iq.addElement('pubsub', 'http://jabber.org/protocol/pubsub' ).addElement('publish')
		pb['node'] = ns
		p = pb.addElement('item')
		log.msg('pep payload:' + unicode(payload))
		if type(payload) == list:
			for itm in payload:
				p.addChild(itm)
		else:
			p.addChild(payload)
		self.disp(iq['id'])
		d = iq.send()
		d.addCallback(self._pepReceived).addErrback(self.chyba)

	def getRoster(self):
		""" Posle zadost o roster na server """
		log.msg('get roster')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:roster'
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._onRosterArrive).addErrback(self.chyba)
		log.msg('poslana zadost o roster')


	def getMUCConfig(self, jid, callback = None):
		""" Posle zadost o registracni formular na dany jid """
		log.msg('get muc config')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='http://jabber.org/protocol/muc#owner'
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._onMUCConfigReceived, callback, jid).addErrback(self.chyba)
		return d

	def setMUCConfig(self, jid, forms):
		""" Posle zadost o registracni formular na dany jid """
		log.msg('set muc config')
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'set'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='http://jabber.org/protocol/muc#owner'
		x = q.addChild(forms)
		x['type'] = 'submit'
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		return d

	def getRegisterForm(self, jid, callback = None):
		""" Posle zadost o registracni formular na dany jid """
		log.msg('get reg form')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:register'
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._onRegisterGet, callback, jid).addErrback(self.chyba)
		return d

	def setRegisterForm(self, jid, legacy=None, forms = None, remove = False):
		log.msg('set reg form')
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'set'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:register'
		if remove:
			q.addElement('remove')
		else:
			if legacy != None:
				for k,v in legacy.iteritems():
					if k == 'instructions':
						continue
					q.addElement(k, content = v)
			elif forms != None:
				x = q.addChild(forms)
				x['type'] = 'submit'
			else:
				return False
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		return d

	def sendContact(self, komu, contact):
		if not self.hasFeature(komu, 'http://jabber.org/protocol/rosterx'):
			return
		log.msg('sending roster contact')
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'set'
		iq['to'] = komu
		x = iq.addElement('x', 'http://jabber.org/protocol/rosterx')
		item = x.addElement('item')
		item['jid'] = contact.jid
		item['name'] = contact.name
		item['action'] = 'add'

		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		return d


	def getSearchForm(self, jid):
		""" Posle zadost o formular pro hledani na dany jid """
		log.msg('get reg form')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:search'
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._onSearchGet, jid).addErrback(self.chyba)
		return d

	def setSearchForm(self, jid, legacy=None, forms = None):
		log.msg('set search form')
		iq = IQ(self.xmlstream, 'set')
		iq['type'] = 'set'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:search'
		if legacy != None:
			for k,v in legacy.iteritems():
				if k == 'instructions':
					continue
				q.addElement('k', content = v)
		elif forms != None:
			x = q.addChild(forms)
			x['type'] = 'submit'
		else:
			return False
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		return d.addCallback(self._onSearchResult, jid)

	def sendRosterUpdate(self, jid, name, subscription, groups, callback=None, params=None):
		""" Zmeni zaznam v rosteru o zadanem JIDu """
		#print jid, name, subscription, groups
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['from'] = self.jid.full()
		iq['type'] = 'set'
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:roster'
		item = q.addElement('item')
		item['jid'] = jid
		item['name'] = name
		item['subscription'] = subscription
		for group in groups:
			item.addElement('group', content = group)
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._rosterUpdateDone, callback, params).addErrback(self.chyba)

	def getVCard(self, jid):
		""" Posle zadost o vcard """
		#log.msg( 'requesting vcard for ' + unicode(jid))
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['to'] = jid
		iq.addElement('vCard', 'vcard-temp')
		self.disp(iq['id'])
		iq.timeout = 300
		log.msg("Sending VCARD IQ to %s: %s" % (jid, iq.toXml()))
		d = iq.send()
#		log.msg("XML LOG")
#		self.on_xml(iq.toXml())
		d.addCallback(self._vcardReceived).addErrback(self._noVcard, jid)
		return d

	def getTransportForm(self, jid):
		iq = IQ(self.xmlstream, 'get')
		iq['to'] = jid
		iq.addElement('query', 'jabber:iq:gateway')
		self.disp(iq['id'])
		iq.timeout = 2
		log.msg("Gateway interaction IQ")
		d = iq.send()
		d.addCallback(self._gotTransportForm)
		return d

	def _gotTransportForm(self, el):
		q= el.firstChildElement()
		r = {'prompt':'', 'desc':''}
		for i in q.elements():
			if i.name == 'prompt':
				r['prompt'] = unicode(i)
			elif i.name =='desc':
				r['desc'] = unicode(i)
		return r

	def getTransportJid(self, jid, prompt):
		iq = IQ(self.xmlstream, 'set')
		iq['to'] = jid
		q = iq.addElement('query', 'jabber:iq:gateway')
		q.addElement('prompt', content = prompt)
		self.disp(iq['id'])
		#iq.timeout = 60
		log.msg("Gateway interaction IQ")
		d = iq.send()
		d.addCallback(self._gotTransportJid)
		return d

	def _gotTransportJid(self, el):
		return unicode(el.firstChildElement().firstChildElement())

	def getLast(self, jid):
		iq = IQ(self.xmlstream, 'get')
		iq['to'] = jid
		iq.addElement('query', 'jabber:iq:last')
		self.disp(iq['id'])
		#iq.timeout = 60
		log.msg("Sending LastActivity IQ")
		d = iq.send()
		return d

	def setVCard(self,card):
		""" Posle vlastni vcard """
#		log.msg( 'requesting vcard for ' + unicode(jid))
		iq = IQ(self.xmlstream, 'set')
		#iq['xml:lang'] = self.xmlLang
		#iq['to'] = self.jid.userhost()
#		vcard = iq.addElement('vCard', 'vcard-temp')
#		for k,v in card.iteritems():
#			s = k.split('-')
#			if len(s)>1:
#				found = False
#				for el in vcard.elements():
#					if el.name == s[0]:
#						el.addElement(s[1], content = v)
#						found = True
#						break
#				if not found:
#					el = vcard.addElement(s[0])
#					el.addElement(s[1], content = v)
#			else:
#				el = vcard.addElement(k, content = v)
#
#
		iq.addChild(card)
		self.disp(iq['id'])
#		iq.timeout = 60
		#print iq.toXml()
		d = iq.send()
		log.msg("END: setVCard")
		return d

	def getBookmarks(self):
		log.msg('get bookmarks')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		q = iq.addElement('query', 'jabber:iq:private')
		q.addElement('storage', 'storage:bookmarks')
#		self.on_xml(iq.toXml())
		self.disp(iq['id'])
		d = iq.send()
		d.addCallback(self._bookmarksReceived)
		d.addErrback(self._bookmarksErrReceived)

	def setBookmarks(self):
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		q = iq.addElement('query', 'jabber:iq:private')
		storage = q.addElement('storage', 'storage:bookmarks')
		for bookmark in self.bookmarks['conference'].itervalues():
			b = storage.addElement('conference')
			b['jid'] = bookmark.jid.userhost()
			b['name'] = bookmark.name
			b['autojoin'] = unicode(bookmark.autojoin)
			if bookmark.nick:
				b.addElement('nick', content = bookmark.nick)
			if bookmark.password:
				b.addElement('password', content = bookmark.password)

		for bookmark in self.bookmarks['url'].itervalues():
			b = storage.addElement('url')
			b['name'] = bookmark.name
			b['url'] = bookmark.url

		self.disp(iq['id'])
#		self.on_xml(iq.toXml())
		d = iq.send()
		d.addCallback(self._bookmarksSet).addErrback(self.chyba)

	def sendAttention(self, to, body):
		message = Element((None,'message'))
		message['xml:lang'] = self.xmlLang
		message['to'] = to
		if body != None and body.strip() != '':
			message.addElement('body', content = body)
		message.addElement('attention', 'http://www.xmpp.org/extensions/xep-0224.html#ns')
		message['type'] = 'headline'
		self.xmlstream.send(message)

	def getMetacontacts(self, exprivacy = None):
		log.msg('get meta contacts')

		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		q = iq.addElement('query', 'jabber:iq:private')
		q.addElement('storage', 'storage:metacontacts')
#		self.on_xml(iq.toXml())
		self.disp(iq['id'])
		d = iq.send()
		d.addCallback(self._metacontactsReceived)
		d.addErrback(self._metacontactsErrReceived)

	def setMetacontacts(self):
		log.msg( 'sending metacontacts')
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		q = iq.addElement('query', 'jabber:iq:private')
		storage = q.addElement('storage', 'storage:metacontacts')
		for jid,  val in self.roster_meta.iteritems():
			m = storage.addElement('meta')
			m['jid'] = jid
			m['tag'] = val['tag']
			m['order'] = str(val['order'])
		self.disp(iq['id'])
#		self.on_xml(iq.toXml())
		d = iq.send()
		d.addCallback(self._metacontactsSet).addErrback(self.chyba)

	def delContact(self, jid):
		self.sendRosterUpdate(jid, '', 'remove', [])
		if self.roster_meta.has_key(jid):
			del self.roster_meta[jid]
			self.setMetacontacts()

	def getFeatures(self, outjid, ext = None):
		outjid = jid.JID(outjid)
		log.msg('requesting features '+ unicode(outjid.full()))
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['to'] = outjid.full()
		iq['from'] = self.jid.full()
		q = iq.addElement('query', 'http://jabber.org/protocol/disco#info')
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		d.addCallback(self._featuresReceived, ext, outjid).addErrback(self.chyba)

	def getVersion(self, jid):
		#if callback==None:
			#callback=self._versionReceived
		#if errback==None:
			#errback=self.chyba
		log.msg('requesting version info')
		iq = IQ(self.xmlstream, 'get')
		iq['to'] = jid
		iq['xml:lang'] = self.xmlLang
		q = iq.addElement('query', 'jabber:iq:version')
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		#d.addCallback(self._versionReceived).addErrback(self.chyba)
		return d

	def getDiscoInfo(self, injid, node = None,  callback = None, callback_par = None):
		#log.msg( 'requesting disco#info: '+jid)
		jd = jid.JID(injid).full()
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['to'] = jd
		iq['from'] = self.jid.full()
		q = iq.addElement('query', 'http://jabber.org/protocol/disco#info')
		if node != None:
			q['node'] = node
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		d.addCallback(self._discoInfoReceived, node,  callback, callback_par)
		d.addErrback(self._discoInfoErrReceived, (node, jd))
		return d

	def getDiscoItems(self, jid, node = None, callback = None, callback_par = None):
		log.msg('requesting disco#items ')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['to'] = jid
		iq['from'] = self.jid.full()
		q = iq.addElement('query', 'http://jabber.org/protocol/disco#items')
		if node != None:
			q['node'] = node
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		d.addCallback(self._discoItemsReceived, node, callback, callback_par)
		d.addErrback(self._discoItemsErrReceived, (node, jid))
		return d
		
	def getDiscoInfoItems(self, jid, node = None, callback = None, callback_par = None):
		return self.getDiscoItems(jid, node, callback, callback_par)

	def getTime202(self, jid):
		log.msg( 'requesting time202 info')
		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['to'] = jid
		iq.addElement('time','urn:xmpp:time')
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		d.addCallback(self._time202Received).addErrback(self.chyba)

	def joinGC(self,  jid, nick, password = None,sendRooms=True):
		gc = Groupchat(self,  jid, nick, password = password)
		self.groupchats[jid] = gc
		gc.join()
		if sendRooms:
			self.sendPEP('http://www.xmpp.org/extensions/xep-0194.html#ns', self.getChattingPayload())
		else:
		    self.sendPEP('http://www.xmpp.org/extensions/xep-0194.html#ns', Element(('http://www.xmpp.org/extensions/xep-0194.html#ns', 'room')))



	def leaveGC(self,  jid,sendRooms=True):
		self.groupchats[jid].leave()
		del self.groupchats[jid]
		log.msg( 'left MUC: '+ jid)
		if sendRooms:
			self.sendPEP('http://www.xmpp.org/extensions/xep-0194.html#ns', self.getChattingPayload())

############## MUC admin ##################
	def getMUCList(self, jid, typ = 'voice'):
		log.msg('get muc list')

		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='http://jabber.org/protocol/muc#admin'
		item = q.addElement('item')
		item[MUCLISTTYPES[typ][2]] = MUCLISTTYPES[typ][1]
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		d.addCallback(self._onMUCListGet, jid).addErrback(self.chyba)
		return d

	def setMUCList(self, jid, items, typ, remove = False):

		iq = IQ(self.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'set'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='http://jabber.org/protocol/muc#admin'
		for item in items.itervalues():
			itm = q.addElement('item')
			if item.has_key('reason') and item['reason'].strip() != '':
				itm.addElement('reason', content = item['reason'])
			del item['reason']
			itm.attributes = item
		self.disp(iq['id'])
		d = iq.send()
#		self.on_xml(iq.toXml())
		return d

	def getMUCLists(self, jid, types = ['ban', 'member', 'admin', 'owner']):
		seznam = []
		for typ in types:
			seznam.append(self.getMUCList(jid, typ))


		dl = defer.DeferredList(seznam).addCallback(self._onMUCLists, jid, types)
		return dl
################# RPC ####################3
	def callRemote(self, jid, func, params):
		iq = IQ(self.xmlstream, 'set')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'set'
		iq['to'] = jid
		q = iq.addElement('query')
		q['xmlns']='jabber:iq:rpc'
		q.addRawXml(dumps(params, func, False))
		self.disp(iq['id'])
		d = iq.send().addCallback(self._onCallResult)
		return d

	def _onCallResult(self, el):
		query = el.firstChildElement()
		call = loads(query.firstChildElement().toXml().encode('utf8'))
		return call


################# Utility ####################

	def getContactByJid(self, injid):
		jd = jid.JID(injid)
		try:
			contact = self.roster['users'].get(jd.userhost(), None)
		except:
			contact = None
		return contact

	def getMucContactByJid(self, injid):
		jd = jid.JID(injid)
		try:
			contact = self.groupchats[jd.userhost()].users[jd.resource]
		except:
			contact = None
		return contact

	def getHighestJid(self, jd):
		contact = self.getContactByJid(jd)
		if contact != None:
			res = contact.getHighestResource()
			if res != None:
				return contact.jid + '/' + res
		return jd

	def hasFeature(self, injid, feature):
		jd = jid.JID(injid)
		contact = self.getContactByJid(injid)
		f = False
		if contact != None:
			try:
				if jd.resource == None:
					jd = jid.JID(self.getHighestJid(injid))
				f = contact.resources[jd.resource].hasFeature(feature)
			except:
				f = False
		else:
			contact = self.getMucContactByJid(injid)
			try:
				f = contact.hasFeature(feature)
			except:
				f = False

		return f

	def getFeaturesByJid(self, injid):
  		jd = jid.JID(injid)
		contact = self.getContactByJid(injid)
		f = []
		if contact != None:
			try:
				if jd.resource == None:
					jd = jid.JID(self.getHighestJid(injid))
				f = contact.resources[jd.resource].getFeatures()
			except:
				f = []
		else:
			contact = self.getMucContactByJid(injid)
			try:
				f = contact.getFeatures()
			except:
				f = []
		return f

	def getIdentity(self, injid):
		try:
			jd = jid.JID(injid)
		except:
			return None
		if jd == self.jid:
			return self.identity+"/"+self.xmlLang+"/"+self.client_name
			#return self.identity+"//"+self.client_name
		try:
			if self.disco[jd.host][(jd.host,None)].has_key("identities"):
				return self.disco[jd.host][(jd.host,None)]["identities"]
			else:
				return None
		except KeyError:
			return None

	def hasIdentity(self, injid, category, typ = None):

		id = self.getIdentity(injid)

		f = False
		if id != None:
			f=False
			for identity in id.itervalues():
				if typ != None:
					if identity.get('category', None) == category and identity.get('type', None) == typ:
						f = True
				else:
					if identity.get('category', None) == category:
						f = True
					break

		return f

	def getIPAddr(self, hostname = 'default'):
		return(threads.deferToThread(self.getipaddr, hostname))

	def getipaddr(self, hostname='default'):
		if hostname == 'default' or hostname == None:
			hostname = socket.gethostname()

		ips = socket.gethostbyname_ex(hostname)[2]
		ips = [i for i in ips if i.split('.')[0] != '127']
		if len(ips) != 0:
			# check if we have succes in determining outside IP
			ip = ips[0]
		elif len(ips) == 0 and hostname == socket.gethostname():
			# when we want to determine local IP and did not have succes
			# with gethostbyname_ex then we would like to connect to say...

			# google.com and determine the local ip address bound to the
			# local socket.
			try:
				s = socket.socket()
				s.connect(('google.com', 80))
				log.msg ('___ connecting to internet to determine local ip')
				ip = s.getsockname()[0]
				del s
			except:
				log.msg ('*** cannot connect to internet in order to \
				determine outside IP address')
				raise Exception
		if len(ip) != 0:
			return ip
		else:
			log.msg ('*** unable to determine outside IP address')
			raise Exception

	def getMoodPayload(self, mood=None, text = None):
		m = Element(('http://jabber.org/protocol/mood', 'mood'))
		if mood:
			m.addElement(mood)
		if text != None and len(text) > 0 :
			m.addElement('text', content = text)
		return m

	def getActivityPayload(self, group, spec = None, text = None):
		a = Element(('http://jabber.org/protocol/activity', 'activity'))
		if group:
			g = a.addElement(group)
			if spec != None:
				g.addElement(spec)
			if text != None and len(text) > 0 :
				a.addElement('text', content = text)
		return a

	def getTunePayload(self, args):
		t = Element(('http://jabber.org/protocol/tune', 'tune'))
		for k,v in args.iteritems():
			t.addElement(k, content = v)
		return t

	def getChattingPayload(self):
		p = []
		for room in self.groupchats.iterkeys():
			r = Element(('http://www.xmpp.org/extensions/xep-0194.html#ns', 'room'))
			r.addElement('uri', content = 'xmpp:'+room)
			p.append(r)
		if len(p) ==0:
			p = r = Element(('http://www.xmpp.org/extensions/xep-0194.html#ns', 'room'))
		return p


	def createRatingList(self):
		def _subscribe (el):
			iq = IQ(self.main.client.xmlstream, "set")
			pubsub = iq.addElement('pubsub',  'http://jabber.org/protocol/pubsub#owner')
			subscriptions = pubsub.addElement('subscriptions')
			subscriptions['node'] = 'http://dev.jabbim.cz/jabbim#favroster'
			subscription =subscriptions.addElement('subscription')
			subscription['jid'] = self.jid.userhost()
			subscription['subscription'] = 'subscribed'

			self.disp(iq['id'])
			return iq.send()
		iq = IQ(self.main.client.xmlstream, "set")
		pubsub = iq.addElement('pubsub',  'http://jabber.org/protocol/pubsub')
		create = pubsub.addElement('create')
		create['node'] = 'http://dev.jabbim.cz/jabbim#favroster'
		config = pubsub.addElement('configure')
		type = Field('FORM_TYPE', 'hidden', values=['http://jabber.org/protocol/pubsub#node_config'])
		model = Field('pubsub#access_model',  values=['whitelist'])
		persistence = Field('pubsub#persist_items',  values=['1'])
		notif = Field('pubsub#deliver_notifications', values=['1'])
		notif_pay = Field('pubsub#deliver_payloads', values=['1'])
		cfg = Xform("submit",fields=[type,  model,  persistence,  notif,  notif_pay]).buildElement()
		config.addChild(cfg)
		self.disp(iq['id'])
		d = iq.send()
		d.addCallback(_subscribe)
		return d

	def deleteRatingList(self):
		iq = IQ(self.main.client.xmlstream, "set")
		pubsub = iq.addElement('pubsub',  'http://jabber.org/protocol/pubsub#owner')
		delete = pubsub.addElement('delete')
		delete['node'] = 'http://dev.jabbim.cz/jabbim#favroster'
		self.disp(iq['id'])
		d = iq.send()

	def sendUserRating(self,  jid=None):
		iq = IQ(self.main.client.xmlstream, "set")
		pubsub = iq.addElement('pubsub',  'http://jabber.org/protocol/pubsub')
		publish = pubsub.addElement('publish')
		publish['node'] = 'http://dev.jabbim.cz/jabbim#favroster'
		if jid:
			users=[self.main.userRating.users[jid]]
		else:
			users=list(self.main.userRating.users.values())
		for user in users:
			item = publish.addElement('item')
			item['id'] = user.jid
			rating = item.addElement('rating')
			rating['jid'] = user.jid
			rating['val'] = unicode(user.rating)
			rating['messages'] = unicode(user.messages)
			rating['reward'] = unicode(self.main.userRating.last_reward)
		self.disp(iq['id'])
		d = iq.send()
		return d

	def getUserRating(self,  users = None):
		def _gotRatings(el):
			log.msg( 'we got it!')
			ratings = {}
			items = el.firstChildElement().firstChildElement()
			lastReward=None
			for item in items.elements():
				rating = item.firstChildElement()
				if not lastReward:
					lastReward=rating['reward']
				ratings[rating['jid']] = rating.attributes
			ratings['lastReward']=lastReward

			return ratings
		iq = IQ(self.main.client.xmlstream, "get")
		pubsub = iq.addElement('pubsub',  'http://jabber.org/protocol/pubsub')
		items = pubsub.addElement('items')
		items['node'] = 'http://dev.jabbim.cz/jabbim#favroster'
		if users != None:
			for jid in users:
				item = items.addElement('item')
				item['id'] = jid
		self.disp(iq['id'])
		d = iq.send().addCallback(_gotRatings)
		return d



