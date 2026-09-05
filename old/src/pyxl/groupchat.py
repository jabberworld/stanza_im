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
from twisted.words.xish import domish
import jid as jidT
from twisted.words.protocols.jabber.xmlstream import IQ

class Groupchat:
	def __init__(self,  client,  JID,  nick, password = None):
		self.client = client
		self.jid = JID
		self.nick = nick
		self.password = password
		self.users = {} #nick: MUCContact
	
	def setRole(self, nick, role,  reason = None):
		print 'setting role'
		iq = IQ(self.client.xmlstream, 'set')
		iq['to'] = self.jid
		q = iq.addElement('query', 'http://jabber.org/protocol/muc#admin')
		item = q.addElement('item')
		item['nick'] = nick
		item['role'] = role
		if reason :
			item.addElement('reason',  content = reason)
		#self.client.on_xml(iq.toXml())
		d = iq.send()
		self.client.disp(iq['id'])
		d.addCallback(self._roleResult)
		d.addErrback(self._roleFail,  nick)

	def _roleFail(self,el,data=None):
		print "role fail"

	def _roleResult(self,  err,  nick):
		try:
			el = err.value.getElement()
		except:
			print err
			return
		self.client.on_roleError(self.jid, el.firstChildElement().name,  nick)
		
	def setAffiliation(self, nick, affiliation,  reason = None):
		print 'setting affiliation'
		iq = IQ(self.client.xmlstream, 'set')
		iq['to'] = self.jid
		q = iq.addElement('query', 'http://jabber.org/protocol/muc#admin')
		item = q.addElement('item')
		item['nick'] = nick
		item['affiliation'] = affiliation
		if reason :
			item.addElement('reason',  content = reason)
		#self.client.on_xml(iq.toXml())
		d = iq.send()
		self.client.disp(iq['id'])
		d.addCallback(self._affiliationResult)
		d.addErrback(self._affiliationFail,  nick)
	
	def _affiliationResult(self,  el):
		print 'affiliation change succesfull'
	
	def _affiliationFail(self,  err):
		try:
			el = err.value.getElement()
		except:
			print err
			return
		self.client.on_affiliationError(self.jid, el.firstChildElement().name,  nick)
	
	
	def join(self):
		self.client.getDiscoInfo(jidT.JID(self.jid).host)
		print 'joining MUC: ',  self.jid
		presence = domish.Element((None, 'presence'))
		presence['to'] = '%s/%s'%(self.jid,  self.nick)
		x = presence.addElement('x', 'http://jabber.org/protocol/muc')
		if self.password != None and self.password != '':
			x.addElement('password', content = self.password)
		#self.client.on_xml(presence.toXml())
		self.client.xmlstream.send(presence)

	
	def leave(self,  status = None):
		print 'leaving MUC: ',  self.jid
		presence = domish.Element((None, 'presence'))
		presence['to'] = self.jid+"/"+self.nick
		presence['type'] = 'unavailable'
		if status:
			presence['status'] = status
		presence.addElement('x', 'http://jabber.org/protocol/muc')
		#self.client.on_xml(presence.toXml())
		self.client.xmlstream.send(presence)

	
	def setStatus(self,  nick,  show,  status):
		if self.users.has_key(nick):
			self.users[nick].setStatus(show, status)
		else:
			self.users[nick] = MUCContact(self, nick, show, status)
	def setInfo(self,  nick,  affiliation,  role,  jid, features):
		self.users[nick].setInfo(affiliation,  role,  jid, features)
	

class MUCContact:
	def __init__(self,  muc, nick,  show,  status,  affiliation=None,  role = None,  jid = None):
		self.muc = muc
		self.nick = nick
		self.show = show
		self.status = status
		self.affiliation = affiliation
		self.role = role
		self.item=None
		self.truejid = jid
		self.features = []
	
	def hasFeature(self, feature):
		if feature in self.features:
			return True
		else:
			return False
			
	def setStatus(self,  show,  status):
		if show == 'offline':
			del  self.muc.users[self.nick]
			self.muc = None
		else:
			self.show = show
			self.status = status
	
	def setInfo(self,  affiliation,  role,  jid, features):
		self.affiliation = affiliation
		self.role = role
		self.truejid = jid
		self.features = features
	def getFeatures(self):
		return self.features
