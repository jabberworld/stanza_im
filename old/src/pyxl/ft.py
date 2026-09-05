import sys,  re,  time,  random,  os
from calendar import timegm
from twisted.python import log
import jid
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1
from base64 import b64encode, b64decode
from twisted.protocols import socks
from twisted.words.protocols.jabber.xmlstream import IQ, TimeoutError
from twisted.internet.protocol import Protocol, ClientFactory, Factory
from socket import getaddrinfo
import socks5, events, base64
from twisted.internet import threads, defer, reactor
from twisted.protocols.basic  import FileSender
import jingle

class FTInit:
	def __init__(self,  client):
		self.client = client
		self.dispatcher = self.client.dispatcher
		self.groupchats = self.client.groupchats
		self.ft = self.client.ft
		self.socks5Srv = None
		self.socks5IP = self.client.socks5IP
		self.socks5Port = self.client.socks5Port
		self.main = self.client.main
		self.ft_proxies = self.client.ft_proxies
		self.client.sendFile = self.sendFile
		self.client.declineFT = self.declineFT
		self.client.receiveFile = self.receiveFile
		self.disp = self.client.disp
		self.xmlLang = self.client.xmlLang
		self.chyba = self.client.chyba
		self.getIPAddr = self.client.getIPAddr
		self.client.ftStart = self.ftStart
		self.client.sendFiles = self.sendFiles
		self.client.receiveFiles = self.receiveFiles
		self.client.declineFiles = self.declineFiles
		self.client.getSIPUBFile = self.getSIPUBFile
		self.ftEndQueue = {}
	
	def send(self,  xml):
		self.client.xmlstream.send(xml)
	
	def sendFiles(self, tojid,  files): #files = {name:abs. path, ..}
		def _received(el,  outfiles):
			
			return el,  outfiles
		iq = IQ(self.client.xmlstream, 'set')
		self.client.disp(iq['id'])
		iq['to'] = tojid
		iq.addElement('tree',  'http://dev.jabbim.cz/jabbim/treeft')
		outfiles = {}#{name:(abs. path, SID),  ..}
		for k, v in files.iteritems():
			sid = 'tree'+ str(random.randint(1000, sys.maxint))
			item =iq.tree.addElement('item',  content = k)
			item['sid'] = sid
			item['size'] = unicode(os.stat(v).st_size)
			outfiles[k] = (v, sid)
		
		d = iq.send().addCallback(_received,  outfiles)
		return d
	
	def onReceiveFiles(self,  el):
		self.client.disp(el['id'])
		log.msg('multiple files offer')
		outfiles = {}#{name:SID,  ..}
		size = 0
		for item in el.tree.elements():
			outfiles[item['sid']] = unicode(item)
			size += int(item['size'])
		self.dispatcher.publishEvent('on_receivedFiles', el['id'], el['from'], outfiles,  size)
	
	def receiveFiles(self,  id,  frm):
		iq = Element((None,'iq'))
		iq['to'] = frm
#		iq['from'] = self.ft[sid].tojid.full()
		iq['id'] = id
		iq['type'] = 'result'
		self.send(iq)
	
	def declineFiles(self,  id,  frm):
		iq = Element((None,'iq'))
		iq['to'] = frm
#		iq['from'] = self.ft[sid].tojid.full()
		iq['id'] = id
		iq['type'] = 'error' #este to chce typ chyby asi
		self.send(iq)
	
	def sendFile(self, outjid, filename, fp, desc = None, preview = None, previewType = 'image/jpeg', typ = None,  sid = None, transport = 'socks'): #typ = None/ft/jingle, transport = socks5/ibb
#		(self,  tojid,  fromjid,  init,  fileprops,  filepath=None, sid = None, typ='ft'):
		fileprops = {}
		fileprops['name'] = filename
		fileprops['desc'] = unicode(desc)
		
		jd = jid.JID(outjid)
		if preview != None:
			fileprops['preview'] = preview
			fileprops['previewType'] = previewType
		if typ == None:
			typ = 'ft'
			if self.client.hasFeature(outjid,  'urn:xmpp:tmp:jingle:apps:file-transfer'):
				typ = 'jingle'
			elif self.client.hasFeature(outjid,  'http://jabber.org/protocol/si/profile/file-transfer'):
				typ = 'ft'
			else:
				if self.client.groupchats.has_key(jd.userhost()):
					typ='jingle'
				else:
					return False # should be checked somewhere
			
		
		
		ftObj = FT(outjid,  self.client.jid.full(),  self, fileprops,  fp, sid,  typ = typ)
		self.ft[ftObj.sid] = ftObj
		ftObj.setTransport(transport)
		ftObj.send()
		return ftObj.sid
		
	def getSIPUBFile(self,  jid,  id,  path):
		def _gotSid(el,  path,  id):
			sid = el.starting['sid']
			if path != None:
				self.client.main.allowedSids[sid] = path
				d = defer.Deferred()
				self.ftEndQueue[sid] = (d,  path)
				return d
		iq = IQ(self.client.xmlstream, 'get')
		self.client.disp(iq['id'])
		iq['to'] = jid
		iq.addElement('start',  'http://jabber.org/protocol/sipub')
		iq.start['id'] = id
		if path != None:
			if self.client.bobDef.has_key(id):
				log.msg('cache hit!!')
				d = defer.Deferred()
				d.callback(self.client.bobDef[id])
				return d
			self.client.bobDef[id] = path
		return iq.send().addCallback(_gotSid,  path,  id)
	
	def onSIPUB(self,  el):
		self.client.disp(el['id'])
		id = el.start['id']
		if self.client.bobDef.has_key(id): #propably not the best thing to do, but it fit's our usecase now
			path = self.client.bobDef[id]
			sid = 'sipub' + str(random.randint(1000, sys.maxint))
			iq = Element((None,'iq'))
			iq['type'] = 'result'
			iq['to'] = el['from']
			iq['id'] = el['id']
			iq.addElement('starting', 'http://jabber.org/protocol/sipub')
			iq.starting['sid'] = sid
			self.send(iq)
			self.sendFile(el['from'],  id, path, sid = sid, typ = 'ft', transport = 'ibb')
		else:
			el.swapAttributeValues('to',  'from')
			el['type'] = 'error'
			self.send(el)

	
	def _onIPAddr(self, addr):
		if not (unicode(addr),self.socks5Port) in self.socks5IP:
			self.socks5IP.append((unicode(addr),self.socks5Port))
		if self.main.config['FTHost'] != '':
			if self.main.config['FTPort'] != '' :
				if not (self.main.config['FTHost'],self.main.config['FTPort'] ) in self.socks5IP:			
					self.socks5IP.append((self.main.config['FTHost'],self.main.config['FTPort'] ))
			else:
				if not (self.main.config['FTHost'],self.socks5Port ) in self.socks5IP:
					self.socks5IP.append((self.main.config['FTHost'], self.socks5Port))
		
		
#		try:
#			from nattraverso.portmapper import get_port_mapper
#		except:
#			log.msg('nattraverso not found, UPnP mapping is not available')
#			return
#		
#		return get_port_mapper().addCallbacks(self.got_port_mapper, self.error_occured)

	def got_port_mapper(self, mapper):
		log.msg("\tGot port mapper:" + unicode(mapper))
		log.msg("Retreiving existing mappings")
		return mapper.get_port_mappings().addCallback(self.got_mappings).addErrback(self.error_occured)
	
	def error_occured(self, err):
		log.err("\tError occured:" + unicode( err))
	
	def got_mappings(self, mappings):
		log.msg('\tExisting mappings:\n\t' + unicode(mappings))
		
	def _checkProxies(self):
		log.msg('checking list of proxies ' + unicode(self.ft_proxies))
		dlist = []
		for proxy, data in self.ft_proxies.iteritems():
			if len(data) != 2:
				dlist.append(self.getProxyInfo(proxy))
		if len(dlist) != 0:
			d = defer.DeferredList(dlist).addCallback(self._updatedProxyInfo)
			return d
		return None
	
	def _updatedProxyInfo(self, results):
		log.msg('proxy list updated ' +unicode( self.ft_proxies))
	
	def getProxyInfo(self, proxy):
		iq = IQ(self.client.xmlstream, 'get')
		iq['xml:lang'] = self.xmlLang
		iq['type'] = 'get'
		iq['to'] = proxy
		q = iq.addElement('query')
		q['xmlns']='http://jabber.org/protocol/bytestreams'
		self.disp(iq['id'])
		d = iq.send()
		d.addCallback(self._onProxyInfo).addErrback(self.chyba)
		return d
	
	def _onProxyInfo(self, el):
		q = el.firstChildElement()
		info = q.firstChildElement()
		self.ft_proxies[el['from']] = [info.getAttribute('host'), info.getAttribute('port')]
	
	def _ftFailed(self, err, sid):
		log.err(unicode( err))
		self.on_ftEnd(sid, 'Canceled')
	
	def _ftstreamhostquery(self, el):
		log.msg('proxy rika: '+ el.toXml())
	
	def _ftreplyReceived(self, el, sid):
		typ = None
		si = el.firstChildElement()
		offset = 0
		for elem in si.elements():
			if elem.name == 'feature':
				typ = unicode(elem.firstChildElement().firstChildElement().firstChildElement())
			elif elem.name == 'file':
				if len(elem.children)==1:
					r = elem.firstChildElement()
					offset = int(r.getAttribute('offset', 0))
					self.ft[sid].fp.seek(offset)
					
		log.msg('FT: ' + typ)
		if typ == 'http://jabber.org/protocol/ibb':
			self.ibbSend(sid)
		elif typ == 'http://jabber.org/protocol/bytestreams':
			self.socksSend(sid)

	def socksSend(self,  sid):
			frm = self.client.ft[sid].tojid.full()
			if self.socks5Srv == None:
				port = int(self.socks5Port)
				connected = False
				while not connected:
					try:
						factory = socks5.SOCKSv5Factory(self)
						self.socks5Srv = self.client.reactor.listenTCP(port, factory)
						self.socks5IP = []
#						self.socks5IP.append(('127.0.0.1', str(port)))
						connected = True
					except:
						log.err('unable to connect to port:'+ unicode(port))
						port +=1
				self.socks5Port = str(port)
			d = self._checkProxies()
			def _doSend(self, client):
				iq = IQ(client.client.xmlstream, 'set')
				iq['to'] = frm
				q = iq.addElement('query', 'http://jabber.org/protocol/bytestreams')
				q['sid'] = sid
				q['mode'] = 'tcp'
					
				addr = sha1("%s%s%s" % (sid, client.client.jid.full(), frm)).hexdigest()
				client.socks5Srv.factory.sessions[addr] = sid
				for data in client.socks5IP:
					streamhost = q.addElement('streamhost')
					streamhost['host'] = data[0]
					streamhost['jid'] = client.client.jid.full()
					streamhost['port'] = data[1]
	
				for proxy, data in client.ft_proxies.iteritems():
					streamhost = q.addElement('streamhost')
					streamhost['host'] = data[0]
					streamhost['jid'] = proxy
					streamhost['port'] = data[1]

				
				d = iq.send()
				client.disp(iq['id'])
				d.addCallback(client._ftreplyhostReceived, sid)
				d.addErrback(client._ftreplyhostErrReceived, sid)
			
			if d != None:
				d.addCallback(self.getIPAddr).addCallback(self._onIPAddr).addCallback(_doSend, self)
			else:
				self.getIPAddr().addCallback(self._onIPAddr)
				_doSend(None, self)

	
	def _ftreplyhostReceived(self, el, sid):
		
		q = el.firstChildElement()
		streamhost = q.firstChildElement()
		host = streamhost['jid']
		self.ft[sid].streamhost = host
		self.ft[sid].medium = time.time()
		addr = sha1("%s%s%s" % (sid, self.client.jid.full(), el['from'])).hexdigest()
		if host != self.client.jid.full():
			try:
				if len(self.socks5Srv.factory.sessions)==0:
					self.socks5Srv.loseConnection()
			except:
				pass
			f = ClientFactory()
			f.protocol = socks5.Send

			factory = socks5.ClientFactory(self.ft_proxies[host][0], int(self.ft_proxies[host][1]),addr, 0,  f, xmpp = self.client, xmpp_sid = sid) 
			self.ft[sid].connector = self.client.reactor.connectTCP(self.ft_proxies[host][0], int(self.ft_proxies[host][1]), factory)
		else:
			
			self.ft[sid].activate(True)
		

	def _ftreplyhostErrReceived(self, err, sid):
		log.err('replyhost err ' + unicode(err))
#		self.on_ftEnd(sid, 'replyhost error')
	
	def ftStart(self, sid, protocol):
		log.msg(sid)
		if self.ft.has_key(sid):
			self.ft[sid].ftstart = time.time()
			self.ft[sid].protocol = protocol
			if self.ft[sid].mode == 'send':
				self.ft[sid].activate()
			elif self.ft[sid].mode == 'receive':
				self.ft[sid].activateReceive()

	def onFileReceive(self, el):
		
		self.disp(el['id'])
		file = {}
		methods = []
		si = el.firstChildElement()
		for e in si.elements():
			if e.name == 'file':
				file = e.attributes
				for elm in e.elements():
					if elm.name == 'preview':
						file['preview'] = unicode(elm)
						file['previewType'] = elm.getAttribute('type', 'image/jpeg')
					elif elm.name == 'desc':
						file['desc'] = unicode(elm)
					elif elm.name == 'range':
						file['range'] = True
			elif e.name == 'feature':
				x = e.firstChildElement()
				for field in x.elements():
					if field.getAttribute('var') == 'stream-method':
						for option in field.elements():
							methods.append(unicode(option.firstChildElement()))
		sid = si['id']
		self.ft[sid] = FT( self.client.jid.full(), el['from'] , self,  file,  filepath=None, sid =sid, typ='ft')
		self.ft[sid].sessionObj = SI(self.ft[sid] ,  methods)
		
		self.client.on_fileReceived(sid, el['id'])
		self.dispatcher.publishEvent('FTStartedEvent', sid, el['id'])
	
	def on_ftEnd(self, sid, error = None):
		self.client.dispatcher.publishEvent('on_ftEnd', sid, error)
		if self.ft.has_key(sid):
			self.ft[sid].delete(error)
		if error == None and self.ftEndQueue.has_key(sid):
			self.ftEndQueue[sid][0].callback(self.ftEndQueue[sid][1])
			del self.ftEndQueue[sid]
	
	def declineFT(self, sid,  id):
		if not self.ft.has_key(sid):
			return False
		else:
			return self.ft[sid].decline(id)

	
	def receiveFile(self, sid, id, filepath,  rang = False):
		self.ft[sid].receive(id, filepath)
		return
		
	
	def onStreamhosts(self, el):
		log.msg('streamhosts received!')
		self.disp(el['id'])
		query = el.firstChildElement()
		sid = query['sid']
		if self.ft.has_key(sid):
			for streamhost in query.elements():
				if streamhost.name == 'streamhost':
					self.ft[sid].streamhosts.append(streamhost.attributes)
			self.ft[sid].streamhostsID = el['id']
			self.ft[sid].connectStreamHost()


	def ibbSend(self, sid):
		iq = IQ(self.client.xmlstream, 'set')
		iq['to'] = self.ft[sid].tojid.full()
		#iq['from'] = self.ft[sid].fromjid.full()
		opn = iq.addElement('open', 'http://jabber.org/protocol/ibb')
		opn['sid'] = sid
		opn['block-size'] = '4096'
		d = iq.send()
		self.disp(iq['id'])
		d.addCallback(self._ftIBBStart, sid)
		d.addErrback(self._ftIBBError, sid)
	
	def _ftIBBError(self, err, sid):
		log.err('IBB error: '+ unicode(err))
		self.ft[sid].error = 'IBB error.'
		self.ft[sid].finish()
	
	def _ftIBBStart(self,el, sid):
		obj =self.ft[sid]
		ready = obj.sessionObj.ready()
		log.msg('waiting for  IBB start')
		if obj.typ == 'jingle':
			if obj.sessionObj.br:
				return
		if ready:
			
			iq = IQ(self.client.xmlstream, 'set')
			iq['to'] = self.ft[sid].tojid.full()
#			iq['from'] = self.ft[sid].fromjid.full()
			data = iq.addElement('data', 'http://jabber.org/protocol/ibb')
			data['sid'] = sid
			data['seq'] = unicode(self.ft[sid].ibbSeq)
			dt = ''
			dt = self.ft[sid].fp.read(4096)
			if not dt:
				self.ft[sid].error = 'IBB cannot start.'
				self.ft[sid].finish()
				return
			data.addContent(b64encode(dt))		
	#		self.on_xml(iq.toXml())
			d = iq.send()
			self.disp(iq['id'])
			self.ft[sid].ibbSeq = self.ft[sid].ibbSeq +1
			self.ft[sid].transfered = self.ft[sid].transfered + len(dt)
			self.client.dispatcher.publishEvent('on_ftTransfered',sid, len(dt))
			d.addCallback(self._ftIBBContinue, sid)
			d.addErrback(self._ftIBBError, sid)
		else:
			reactor.callLater(1, self._ftIBBStart, el, sid)
		
	def _ftIBBContinue(self,el, sid):
		iq = IQ(self.client.xmlstream, 'set')
		iq['to'] = self.ft[sid].tojid.full()
#		iq['from'] = self.ft[sid].fromjid.full()
		data = iq.addElement('data', 'http://jabber.org/protocol/ibb')
		data['sid'] = sid
		data['seq'] = unicode(self.ft[sid].ibbSeq)
		dt = ''
		dt = self.ft[sid].fp.read(4096)
		if not dt:
			
			iq = IQ(self.client.xmlstream, 'set')
			iq['to'] = self.ft[sid].tojid.full()
#			iq['from'] = self.ft[sid].fromjid.full()
			opn = iq.addElement('close', 'http://jabber.org/protocol/ibb')
			opn['sid'] = sid
#			self.on_xml(iq.toXml())
			d = iq.send()
			self.disp(iq['id'])

			self.ft[sid].finish()
			return
		data.addContent(b64encode(dt))		
#		self.on_xml(iq.toXml())
		d = iq.send()
		self.disp(iq['id'])
		self.ft[sid].ibbSeq = self.ft[sid].ibbSeq +1
		self.ft[sid].transfered = self.ft[sid].transfered + len(dt)
		self.client.dispatcher.publishEvent('on_ftTransfered',sid, len(dt))
		d.addCallback(self._ftIBBContinue, sid)
		d.addErrback(self._ftIBBError, sid)
		
	
	def onIBBStart(self, el):
		log.msg('IBB start')
		self.disp(el['id'])
		opn = el.firstChildElement()
		sid = opn['sid']
		iq = Element((None,'iq'))
		iq['to'] = self.ft[sid].fromjid.full()
#		iq['from'] = self.ft[sid].tojid.full()
		iq['id'] = el['id']
		iq['type'] = 'result'
		self.send(iq)
		
	def onIBBData(self, el):
		log.msg('on data')
		for e in el.elements():
			if e.name == 'data':
				sid = e['sid']
				seq = int(e['seq'])
				self.ft[sid].ibbCache[seq] = unicode(e)
				self.ft[sid].ibbProcess()
		if el.name == 'iq':
			self.disp(el['id'])
			iq = Element((None,'iq'))
			iq['to'] = self.ft[sid].fromjid.full()
#			iq['from'] = self.ft[sid].tojid.full()
			iq['id'] = el['id']
			iq['type'] = 'result'
			self.send(iq)

	
	def onIBBEnd(self, iq):
		self.disp(iq['id'])
		close = iq.firstChildElement()
		log.msg('IBB end')
		sid = close['sid']
		self.ft[sid].ibbProcess()
		id = iq['id']
		
		iq = Element((None,'iq'))
		iq['to'] = self.ft[sid].fromjid.full()
#		iq['from'] = self.ft[sid].tojid.full()
		iq['id'] = id
		iq['type'] = 'result'
		self.send(iq)
		self.ft[sid].finish()


class SI:
	def __init__(self, ft,  methods = []):
		self.ft = ft
		self.tojid = ft.tojid
		self.fromjid = ft.fromjid
		self.fileprops = {}
		self.state = 'init'
		self.methods = methods

	def getState(self):
		return self.state

	def setState(self, state):
		self.state = state
	
	def send(self,  fileprops):
		self.fileprops = fileprops
		iq = IQ(self.ft.init.client.xmlstream, 'set')
		outjd = self.fromjid
		if self.ft.init.groupchats.has_key(outjd.userhost()):
			if self.ft.init.groupchats[outjd.userhost()].users[outjd.resource].truejid == None:
				frmjid = outjd.userhost() + '/' + self.ft.init.groupchats[outjd.userhost()].nick
#				iq['from'] = self.fromjid.full()
				typ = 'ibb'
			else:
				outjd = self.ft.init.groupchats[outjd.userhost()].users[outjd.resource].truejid
				
		iq['to'] = self.tojid.full()
#		self.fromjid = jid.JID(outjd)
		si = iq.addElement('si', 'http://jabber.org/protocol/si')
		si['id'] = self.ft.sid
		si['profile'] = 'http://jabber.org/protocol/si/profile/file-transfer'
		si['mime-type'] = 'text/plain'
		file = si.addElement('file', 'http://jabber.org/protocol/si/profile/file-transfer')
		for k, v in self.fileprops.iteritems():
			if k == 'desc':
				file.addElement('desc',  content = unicode(v))
			elif k == 'preview':
				prev = file.addElement('preview', 'http://kopete.kde.org/protocol/file-preview', content = v[0])
				prev['type'] = v[1]
			else:
				file[k] = unicode(v)
		file.addElement('range')
		feature = si.addElement('feature', 'http://jabber.org/protocol/feature-neg')
		x = feature.addElement('x', 'jabber:x:data')
		x['type'] = 'form'
		field = x.addElement('field')
		field['var'] = 'stream-method'
		field['type'] = 'list-single'
		if not self.ft.init.client.IBBonly and self.ft.getTransport() == 'socks':
			field.addRawXml('<option><value>http://jabber.org/protocol/bytestreams</value></option>')
			field.addRawXml('<option><value>http://jabber.org/protocol/ibb</value></option>')
		else:
			field.addRawXml('<option><value>http://jabber.org/protocol/ibb</value></option>')

		self.ft.init.client.disp(iq['id'])
		d = iq.send()
		d.addCallback(self._ftreplyReceived, self.ft.sid).addErrback(self._ftFailed, self.ft.sid)
		self.state = 'offer'
	
	def _ftreplyReceived(self, el, sid):
		typ = None
		si = el.firstChildElement()
		offset = 0
		for elem in si.elements():
			if elem.name == 'feature':
				typ = unicode(elem.firstChildElement().firstChildElement().firstChildElement())
			elif elem.name == 'file':
				if len(elem.children)==1:
					r = elem.firstChildElement()
					offset = int(r.getAttribute('offset', 0))
					self.ft.fp.seek(offset)
					
		log.msg('FT: ' + typ)
		self.state = 'accepted'
		if typ == 'http://jabber.org/protocol/ibb':
			self.ft.init.ibbSend(sid)
		elif typ == 'http://jabber.org/protocol/bytestreams':
			self.ft.init.socksSend(sid)

	def _ftFailed(self, err, sid):
		log.err('ftFailed: '+ unicode(err))
		self.state = 'declined'
		self.ft.init.on_ftEnd(sid, 'Canceled')

	def receive(self,  id,  rang = False):
		self.state = 'accepted'
		if 'http://jabber.org/protocol/bytestreams' in self.methods and not self.ft.init.client.IBBonly:
			method = 'http://jabber.org/protocol/bytestreams'
		elif self.ft.init.client.IBBonly :
			method = 'http://jabber.org/protocol/ibb'
		else:
			method = self.methods[0]
		if method == 'http://jabber.org/protocol/ibb':
			self.ft.setTransport('ibb')
		elif method == 'http://jabber.org/protocol/bytestreams':
			self.ft.setTransport('socks')

		iq = Element((None,'iq'))
		iq['to'] = self.fromjid.full()
#		iq['from'] = self.tojid.full()
		iq['id'] = id
		iq['type'] = 'result'
		si = iq.addElement('si', 'http://jabber.org/protocol/si')
		f = si.addElement('file', 'http://jabber.org/protocol/si/profile/file-transfer')
		if rang == True:
			size = self.ft.size
			r = f.addElement('range')
			r['offset'] = size
		feature = si.addElement('feature', 'http://jabber.org/protocol/feature-neg')
		x = feature.addElement('x', 'jabber:x:data')
		x['type'] = 'submit'
		field = x.addElement('field')
		field['var'] = 'stream-method'
		value = field.addElement('value', content = method)
		self.ft.init.send(iq)
	
	def decline(self,  id):
		self.state = 'declined'
		iq = Element((None, 'iq'))
#		iq['xml:lang'] = self.xmlLang
		iq['to'] = self.ft.fromjid.userhost()
		iq['id'] = id
		iq['type'] = 'error'
		err = iq.addElement('error', content = 'Declined')
		err['code'] = '403'
		self.ft.init.send(iq)
		return True

	def ready(self):
		return True
	
	def delete(self,  error):
		print 'on delete ',self.ft.getTransport(), self.state
		if self.ft.getTransport() != 'socks':
			self.state = 'finished'
		if self.state == 'accepted':
			if self.ft.protocol:
				self.ft.protocol.unregisterProducer()
				self.state = 'finished'
				self.ft.finish()
		return False
	

class Jingle:
	def __init__(self,  ft):
		self.ft = ft
		self.fileprops = {}
		self.state = 'init'
		self.humanReady = False
		self.transportReady = False
		self.br = False
		try:
			self.jingleSession = self.ft.init.client.jingle.sessions[self.ft.sid]
		except:
			pass

	def getState(self):
		return self.state

	def setState(self, state):
		self.state = state
	
	def send(self, fileprops):
		
		jingleSession = jingle.JingleSession(self.ft.init.client.jingle,self.ft.tojid,  self.ft.fromjid, self.ft.sid)
		self.jingleSession = jingleSession
		if self.ft.getTransport() == 'socks':
			jingleSession.createFTContent('urn:xmpp:tmp:jingle:transports:bytestreams',  fileprops)
		elif self.ft.getTransport() == 'ibb':
			jingleSession.createFTContent('urn:xmpp:tmp:jingle:transports:ibb',  fileprops)
		else:
			raise TypeError
		
		jingleSession.initSession()
		self.ft.init.client.jingle.sessions[self.ft.sid] = jingleSession
	
	def receive(self,  id,  rang = False):
		log.msg('doing jingle receive '+self.ft.sid)
		self.humanReady = True
		if self.transportReady:
			self.jingleSession.acceptSession()
		elif self.br:
			return
		else:
			reactor.callLater(1, self.receive, id, rang)
	
	def ready(self):
		self.transportReady = True
		return self.humanReady
			
	def decline(self,  id):
		self.jingleSession.terminateSession('decline')
		self.br = True
		
	
	def delete(self,  error):

		if error == 'activate error' or error == 'connect failed' or error == "Connection lost":
			if self.ft.fp == None:
				if self.jingleSession.role == 'initiator':
					mode = 'rb'
				else:
					mode = 'wb'
				self.ft.setFilePath(self.ft.filepath, mode)
			props = self.fileprops
			props['type'] = 'request'
			trans = jingle.FTTransport()
			trans.fromString('urn:xmpp:tmp:jingle:transports:ibb')
			content = jingle.Content('initiator',  'file offer',  'urn:xmpp:tmp:jingle:apps:file-transfer', trans ,  props)
			if self.jingleSession.role != 'initiator':
				self.jingleSession.contentReplace(content)
			self.transportReady = True
			return True
		self.br = True
		if error != 'decline':
			error = None
		if self.jingleSession.state != 'ENDED':
			if self.jingleSession.role != 'initiator':
				self.jingleSession.terminateSession(error)
		#HACK!
		if self.ft.protocol:
			self.ft.protocol.unregisterProducer()
		return False

class FT:
	def __init__(self,  tojid,  fromjid,  init,  fileprops,  filepath=None, sid = None, typ='ft'):
		if sid != None:
			self.sid = sid
		else:
			self.sid = typ + str(random.randint(1000, sys.maxint))
		
		self.init = init
		self.tojid = jid.JID(tojid)
		self.fromjid = jid.JID(fromjid)
		self.fileprops = fileprops
		self.filepath = filepath
		self.fp = None
		if filepath != None:
			self.setFilePath(filepath)
		self.transfered = 0
#		self.size = 0
		if not self.fileprops.has_key('size'):
			self.fileprops['size'] = self.size
#		else:
#			self.size = int(self.fileprops['size'])
		self.sessionObj = None
		self.typ = typ
		self.client = init.client
		self.streamhosts = []
		self.mode = 'send'
		self.error = None
		self.ibbSeq = 0
		self.ibbCache = {}
		self.protocol = None
		self.uplimit = 0
		self.downlimit = 0
		
		self.transport = 'socks' # socks or ibb, used for forcing type of underlying transport method
	
	def setTransport(self, transport):
		if transport == 'socks' or transport == 'ibb':
			self.transport = transport
		else:
			raise TypeError
	
	def getTransport(self):
		return self.transport
	
	def setLimit(self,  limit = 0, typ = 'upload'):
		if typ =='upload':
			self.uplimit = limit
		elif typ == 'download':
			self.downlimit = limit
	
	def getLimit(self,  typ = 'upload'):
		if typ == 'upload':
			return self.uplimit
		else:
			return self.downlimit
		
	
	def setFilePath(self,  filepath,  mode = 'rb'):
		self.filepath = filepath
		try:
			self.fp = open(filepath, mode)
		except:
			self.fp = None
			self.error = 'Wrong path'
			self.finish()
			return
		self.size = os.path.getsize(filepath)
		log.msg('filepath set')
	
	def send(self):
		self.mode = 'send'
		
		if self.typ == 'ft':
			self.sessionObj = SI(self)
			self.sessionObj.send(self.fileprops)
		elif self.typ == 'jingle':
			self.sessionObj = Jingle(self)
			self.sessionObj.send(self.fileprops)
	
	def delete(self,  error):
		print self.fp
		if self.sessionObj != None:
			ret = self.sessionObj.delete(error)
			if not ret:
				del self.init.client.ft[self.sid]
				self = None
		else:
			del self.init.client.ft[self.sid]
			self = None
	
	
	def activate(self,  activated = False):
		log.msg('doing activate for '+self.sid)
		ready = self.sessionObj.ready()
		
		if self.typ == 'jingle':
			if self.sessionObj.br:
				return
		if ready == True:
			if activated:
				FileSender().beginFileTransfer(self.fp, self.protocol)#. addCallback(self._finished)
				
			else:
				iq = IQ(self.init.client.xmlstream, 'set')
				iq['to'] = self.streamhost
				q = iq.addElement('query', 'http://jabber.org/protocol/bytestreams')
				q['sid'] = self.sid
				q.addElement('activate', content = self.tojid.full())
				d = iq.send()
				self.init.client.disp(iq['id'])
				d.addCallback(self._activated).addErrback(self._activateFailed)
		else:
			reactor.callLater(1,self.activate, activated)
	
	def _activateFailed(self, err):
		log.msg('activate failed with: ' + unicode(err))
		self.init.on_ftEnd(self.sid, 'activate error')
		
	def _activated(self, el = None):
		print self.fp, 'activated'
		
		FileSender().beginFileTransfer(self.fp, self.protocol)#. addCallback(self._finished)
	
	def _finished(self, last):
		log.msg('finished transfer for ' + self.filepath)
		log.msg('times: %i - %i - %i - %i'%(self.start, self.medium, self.ftstart, time.time())) 
	
	def finish(self):
		if self.sessionObj == None:
			return
		if self.sessionObj.getState() == 'finished':
			log.msg('ft already finished')
			return
		else:
			self.sessionObj.setState('finished')
		log.msg("konec prenosu")
		if self.fp != None:
			self.fp.close()
		addr = sha1("%s%s%s" % (self.sid, self.fromjid.full(), self.tojid.full())).hexdigest()
		try:
			self.protocol.transport.loseConnection()
			del self.init.client.socks5Srv.factory.sessions[addr]
			if len(self.init.client.socks5Srv.factory.sessions)==0:
				self.init.client.socks5Srv.loseConnection()
		except:
			log.err('unable to finish socks5')
			#self.delete(None)
#			print self.init.client.socks5Srv.factory.sessions
			pass

		self.init.on_ftEnd(self.sid, self.error)



	def receive(self,  id,  filepath,  range = False):
		self.mode = 'receive'
		self.setFilePath(filepath,  'wb')
		self.size = int(self.fileprops['size'])
		self.sessionObj.receive(id,  range)
	
	def decline(self,  id):
		self.sessionObj.decline(id)
	
	def connectStreamHost(self):
		
		streamhost = self.streamhosts.pop(0)
		self.activeStreamhost = streamhost
		f = ClientFactory()
		f.protocol = socks5.Receive
		addr = sha1("%s%s%s" % (self.sid,  self.fromjid.full(), self.tojid.full())).hexdigest()
		factory = socks5.ClientFactory(streamhost['host'], int(streamhost['port']),addr, 0,  f, xmpp = self.init.client, xmpp_sid = self.sid) 
		self.connector = self.client.reactor.connectTCP(streamhost['host'], int(streamhost['port']), factory)
	
	def connectFailure(self):
		log.msg('connect failed')
		
		if len(self.streamhosts)>0:
			self.connector = None
			self.activeStreamhost = None
			self.connectStreamHost()
		else:
			if self.transfered == 0:
				log.msg('nemuzu se spojit')
				self.delete('connect failed')
	
	def activateReceive(self):
		
		iq = Element((None,'iq'))
		iq['to'] = self.fromjid.full()
#		iq['from'] = self.tojid.full()
		iq['id'] = self.streamhostsID
		iq['type'] = 'result'
		query = iq.addElement('query', 'http://jabber.org/protocol/bytestreams')
		used = query.addElement('streamhost-used')
		used['jid'] = self.activeStreamhost['jid']
		
		self.streamhosts = []
		self.error = None
		self.client.xmlstream.send(iq)
		self.sessionObj.ready()

	def ibbProcess(self):
		c = True
		while c:
			if self.ibbCache.has_key(self.ibbSeq):
				
				data = b64decode(self.ibbCache[self.ibbSeq])
				
				self.transfered = self.transfered + len(data)
				self.client.dispatcher.publishEvent('on_ftTransfered',self.sid, len(data))
				self.fp.write(data)
				del self.ibbCache[self.ibbSeq]
				self.ibbSeq = self.ibbSeq + 1
			else:
				c = False
			
	
	
	
