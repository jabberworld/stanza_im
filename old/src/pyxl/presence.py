import sys
from twisted.python import log
import jid
from twisted.words.xish import domish
from twisted.words.xish.domish import Element

class PresenceInit:
	def __init__(self,  client):
		self.client = client
		self.dispatcher = self.client.dispatcher

	def send(self,  xml):
		self.client.xmlstream.send(xml)

	def onSubscribe(self, el):
		log.msg( 'on subscribe')
		status = ''
		for child in el.elements():
			if child.name == 'status':
				status = unicode(child)
		self.client.on_subscribe(el['from'], status)

	def onSubscribed(self, el):
		log.msg( 'on subscribed')
		self.client.on_subscribed(el['from'])

	def onUnSubscribe(self, el):
		log.msg('on unsubscribe')
		self.client.on_unsubscribe(el['from'])

	def onUnSubscribed(self, el):
		log.msg( 'on unsubscribed')
	##		self.sendRosterUpdate(jid, '', 'remove', [])
		self.client.on_unsubscribed(el['from'])


	def onFirstPresence(self):
		log.msg( 'first presences')
		self.client.first_wait = False
		self.client.reactor.callFromThread(self.client.on_firstpresence, self.client.first_presence)
		self.dispatcher.publishEvent('first presence')

	def onPresence(self, el):
		#log.msg('presence > ')
		try:
			frm = jid.JID(el['from'])
		except:
			try:
				log.err("onPresence, jid mallformed" + unicode([el['from']]))
			except:
				log.err("onPresence, jid mallformed")
			return
		fromjid = frm.userhost()
		resource = frm.resource
		show = status = priority = nick = typ = affiliation = role = truejid = error = reason = actor = identity = None
		codes = []
		hash = 'None'
		if el.hasAttribute('type'):
		#	if el['type'] != 'unavailable':
		#		return
		#	else:
		#		typ = 'unavailable'
			typ = el['type']
		if typ == 'error':
			error = 'error'

		features = self.client.getFeaturesByJid(frm)
		for child in el.elements():
			if child.name == 'error':
				error = 'error'
				for x in child.elements():
					if x.name != 'text':
						error = x.name
			if child.name == 'show':
				show = child.__str__()
			elif child.name == 'status':
				status = child.__str__()
				pass
			elif child.name == 'priority':
				priority = child.__str__()
				if priority == None:
					log.msg( el.toXml())
			elif child.name == 'c':
				caps_node = child.getAttribute('node')
				ext = child.getAttribute('ver')

				if self.client.caps_cache.has_key(ext) and ext != None:
					features = self.client.caps_cache[ext][1]
					identity = self.client.caps_cache[ext][0]
				elif ext == None:
					if typ !='unavailable' and not self.client.hasFeature(frm.full(), 'http://jabber.org/protocol/disco#info'):
						features = 'asked'
						log.msg('nocaps ' + unicode(self.client.getIdentity(frm.host)))

						if  self.client.hasIdentity(frm.host, 'conference'):
							features = ['-']
						elif len(features)>0:
							log.msg(unicode(features))
						else:
							self.client.getFeatures(frm, ext)
							pass
				else:
					features = 'asked'
					self.client.getFeatures(frm, ext)
			if child.name == 'x' and child.defaultUri == 'http://jabber.org/protocol/muc#user':
				for item in child.elements():
					if item.name == 'item':
						if item.hasAttribute('affiliation'):
							affiliation = item['affiliation']
						else:
							affiliation = 'none'
						if item.hasAttribute('role'):
							role = item['role']
						else:
							role = 'none'
						if item.hasAttribute('nick'):
							nick=unicode(item['nick'])
						if item.hasAttribute('jid'):
							truejid = item['jid']
						for itm in item.elements():
							if itm.name == 'reason':
								reason = unicode(itm)
							elif itm.name == 'actor':
								actor = itm.getAttribute('jid')

					if item.name == 'status' :
						codes.append(item['code'])
			elif child.name == 'x' and child.defaultUri == 'vcard-temp:x:update':
				hash = unicode(child.firstChildElement())

		if show == None and not el.hasAttribute('type'):
			show = 'online'
		elif el.hasAttribute('type'):
			if el['type'] =='unavailable':
				show = 'offline'
			else:
				return

		#hack
		del el

		if features == None or len(features) == 0:
			if  self.client.hasIdentity(frm.host, 'conference') or self.client.hasIdentity(frm.host, 'gateway'):
				features = ['-']
			else:
				self.client.getFeatures(frm, None)

		if features == 'asked':
			features = []

		#avatars
		if show=="offline":
			wantAvatar=False
		else:
			wantAvatar=True
			if self.client.groupchats.has_key(fromjid):
				if self.client.disco.has_key(frm.host):
					if self.client.disco[frm.host][(frm.host,None)].has_key("identities"):
						if self.client.disco[frm.host][(frm.host,None)].has_key("identities"):
							for identity,values in self.client.disco[frm.host][(frm.host,None)]["identities"].iteritems():
								if values['type']=='irc':
									wantAvatar=False

		if wantAvatar:
			if self.client.groupchats.has_key(fromjid):
				# want avatar for room@conf.server/somebody
				avatarjid = frm.full()
			else:
				# want avatar for somebody@server
				avatarjid = fromjid

			if self.client.main.avatarDef.has_key(avatarjid):
				if self.client.main.avatarDef[avatarjid] == hash:
					# good, we already have the right avatar
					pass
				elif hash != 'None':
					self.client.getVCard(avatarjid)
			else:
				self.client.getVCard(avatarjid)

		if self.client.groupchats.has_key(fromjid):
			if show=="offline":
				codes.append('PART')
				self.dispatcher.publishEvent('on_GCpresence',fromjid, resource,  show,  status,  codes, reason, actor, nick)

			if self.client.groupchats[fromjid].users.has_key(resource):
				self.client.groupchats[fromjid].setInfo(resource,  affiliation,  role,  truejid, features)
				self.client.groupchats[fromjid].setStatus(resource,  show,  status)

			else:
				codes.append('JOIN')
				self.client.groupchats[fromjid].setStatus(resource,  show,  status)
				self.client.groupchats[fromjid].setInfo(resource,  affiliation,  role,  truejid, features)
			if show!="offline":
				self.dispatcher.publishEvent('on_GCpresence',fromjid, resource,  show,  status,  codes, reason, actor, nick)
			return

		elif self.client.roster['users'].has_key(fromjid):
			first = self.client.roster['users'][unicode(fromjid)].setStatus(resource, show,status)
			if self.client.roster['users'][fromjid].resources.has_key(resource):
				self.client.roster['users'][fromjid].setPriority(resource, priority)
				self.client.roster['users'][fromjid].setFeatures(resource, features, identity)


			if first and self.client.first_wait:
				self.client.first_presence.append((frm,show, error))
			else:
				self.dispatcher.publishEvent('on_presence',frm,show, error)

	def onPresenceError(self,  el):
		#zatim jenom GC errory .. ani nevim jestli ma smysl zachytavat i jine ..
	#		self.on_xml(el.toXml())
		try:
			frm = jid.JID(el['from'])
		except:
			try:
				log.err("onPresenceError, jid mallformed "+ unicode([el['from']]))
			except:
				log.err("onPresenceError, jid mallformed")
			return

		fromjid = frm.userhost()
		resource = jid.JID(el['from']).resource
		if self.client.groupchats.has_key(fromjid):

			del self.client.groupchats[fromjid]
			for child in  el.elements():
				if child.name == 'error':
					text = name = ""
					for elm in child.elements():

						if elm.name == 'text':
							text = unicode(elm)
						else:
							text = unicode(elm.name)
					self.dispatcher.publishEvent('on_GCpresenceError',fromjid,child.getAttribute('code'),  child.getAttribute('type'),  name , text, resource)

