import sys, time, random
import socks5, events
from twisted import names
from twisted.python import log
from twisted.internet import protocol, error
from twisted.names import client as dns
from twisted.names.dns import Record_TXT

from twisted.words.protocols import jabber
from twisted.words.protocols.jabber import client,jid
from twisted.words.xish import domish
from twisted.words.xish.domish import Element
from twisted.internet import reactor
from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.internet.protocol import Protocol, ClientFactory
from twisted.words.protocols.jabber.client import *

from twisted.words.protocols.jabber.client import *
from twisted.internet import reactor
try:
	import bosh.xmlstream
	from bosh import client as bclient
except:
	print "web2 is not installed"


def basicClientFactory(jid, secret):
    a = RegisteringAuthenticator(jid, secret)
    return xmlstream.XmlStreamFactory(a)

class RegisteringAuthenticator(BasicAuthenticator):
	def _registerResultEvent(self, iq):

		if iq["type"] == "result":
			# Registration succeeded -- go ahead and auth
			self.streamStarted(self.rootElement)
		else:
			# Registration failed
			if iq.error['code'] == '500':
				reactor.callLater(5,  self.registerAccount,  self.jid.user,  self.password)
				print 'wait error, trying in 5 seconds'
			self.xmlstream.dispatch(iq, self.REGISTER_FAILED_EVENT)

	def streamStarted(self, rootElement):
		self.rootElement = rootElement
		BasicAuthenticator.streamStarted(self, rootElement)




def RegisteringBOSHClientFactory(jid, password, bosh_url, bosh_attrs = {},  proxy = None):
    """
    @param jid: authenticatiing jis
    @param password: user's password
    """
    a = RegisteringAuthenticator(jid, password)
    f = bclient.BOSHFactory(a)
    f.bosh_url = bosh_url
    f.bosh_attrs = bclient._default_bosh_attrs.copy()
    f.bosh_attrs["to"] = jid.host.encode("utf-8")
    f.bosh_attrs.update(bosh_attrs)
    f.proxy = proxy
    return f

class RegisteringClient:
	def __init__(self, username, server, resource,password, port, reactor):
		self.jid = jid.JID('%s@%s/%s'%(username, server, resource))
		self.password  = password
		self.host = self.jid.host
		self.port = port
		self.factory = None
		self.connection = None
		self.reactor = reactor
		self.tryNum=0
		self.connections = []
		self.proxy = None
		self.IBBonly = False
		self.xmlLang = 'cs'
		pass

	def connect(self):
		log.msg('dns - ' + unicode(time.time()) + '_xmpp-client._tcp.'+self.jid.host)
		if sys.platform == 'win32':
			import IPConfig
			srv = IPConfig.IPConfig().get_dns()
			dnssrv = []
			for server in srv:
				if len(server.strip())>0 and server.strip() != '0.0.0.0':
					dnssrv.append((server, 53))
			if len(dnssrv) > 0:
				r = dns.Resolver(servers=dnssrv)
				d = r.lookupService('_xmpp-client._tcp.'+self.jid.host, timeout = [2,10])
				txt = r.lookupText('_xmppconnect.'+self.jid.host, timeout = [2,10])
			else:
				log.msg('using root resolver')
				d = dns.lookupService('_xmpp-client._tcp.'+self.jid.host, timeout = [2,10])
				txt = dns.lookupText('_xmppconnect.'+self.jid.host, timeout = [2,10])
		else:
			d = dns.lookupService('_xmpp-client._tcp.'+self.jid.host, timeout = [2,10])
			txt = dns.lookupText('_xmppconnect.'+self.jid.host, timeout = [2,10])

		defer.DeferredList([d, txt]).addCallback(self._dnsLookup)


	def _dnsLookup(self, results):
		self.connections = []
		resp = results[0][1]

		if not results[0][0] or len(resp[0]) == 0:
			self._dnsLookupErr(resp)
			return
		for r in resp[0]:
			self.connections.append((unicode(r.payload.target), int(r.payload.port)))

		if results[1][0]:
			txt = results[1][1]
			bind = None
			conn = None
			for r in txt[0]:
				if not isinstance(r.payload, Record_TXT):
					continue
				parts= r.payload.data[0].split('=')
				if parts[0] == '_xmpp-client-xbosh':
					bind = (parts[1], )
				if parts[0] == '_xmpp-client-alternative-port':
					host,port = parts[1].split(':')

					conn = (unicode(host), int(port))

			if conn != None:
				self.connections.append(conn)
			if bind != None:
				self.connections.append(bind)
		else:
			self._dnsLookupErr(resp)
			return


		self.doConnect()
#		self._connect(unicode(r[4][0]), int(r[4][1]))

	def _dnsLookupErr(self, resp):
		log.err('DNS err: '+ unicode(resp))

		self.connections.append((self.jid.host, 5222))
		self.connections.append(('conn443.netlab.cz', 443))
		self.connections.append(('http://bind.jabbim.cz:80/', )) #just give them chance
		self.doConnect()
	def doConnect(self):
		#pops first connection from list and tries to connect to it
		print 'do connect ',  self.connections
		if len(self.connections) == 0:
			self.main._disconnect(error = 'failed')
			self.reactor.callFromThread(self.on_disconnect)
			return
		pop = self.connections.pop(0)
		if len(pop) ==2:
			host = pop[0]
			port = pop[1]
			self._connect(host,port)
		elif len(pop) == 1:
			boshURL = pop[0]
			try:
				from urlparse import urlparse
				parts = urlparse(boshURL)[1].split(':')
				bhost = parts[0]
				if len(parts) ==1:
					bport = 80
				else:
					bport = parts[1]
			except:
				print 'bosh parse failure'
				self.doConnect()
			self._connect(bhost, int(bport), boshURL)



	def _connect(self, host, port,  boshURL = None):
		if boshURL == None:
			self.factory = basicClientFactory(self.jid,self.password)
			self.IBBonly = False
		else:
			self.IBBonly = True
			self.factory = RegisteringBOSHClientFactory(self.jid, self.password, unicode(boshURL), bosh_attrs = {"wait": "10", 'xml:lang':self.xmlLang},  proxy  = self.proxy)
#		self.factory.authenticator = RegisteringAuthenticator(self.jid,  self.password)
		self.factory.addBootstrap('//event/stream/start',self._streamstart)
		self.factory.addBootstrap('//event/stream/authd',self._authd)
#		self.factory.addBootstrap("//event/client/basicauth/invaliduser", self._invaliduser)
		self.factory.addBootstrap("//event/client/basicauth/authfailed", self._authfailed)
		self.factory.addBootstrap("//event/xmpp/initfailed", self._authfailed)
		self.factory.addBootstrap("//event/client/basicauth/registerfailed", self._regfailed)
		self.factory.addBootstrap('/iq[@type="result"]/bind', self._bind)
#		print dir(self.factory.protocol)


		self.factory.clientConnectionLost = self.connectionLost
		self.factory.clientConnectionFailed = self.connectionFailed
		self.connection = self.reactor.connectTCP(host,port,self.factory)
		log.msg('started - ' + unicode(time.time()))

	def _streamstart(self, xml):
		self.xmlstream = xml
		self.xmlstream.rawDataInFn = self.xml
		self.xmlstream.rawDataOutFn = self.xml

	def xml(self, buf):
#		log.msg(u'XML: ' + unicode(buf, 'utf8', 'replace'))
		pass

	def connectionLost(self, connector, reason=protocol.connectionDone):
		log.msg('connection lost!')
		if self.IBBonly:
			self.connection.connect()
			return
		self.tryNum+=1
		if self.tryNum<2:
			self.connect()



	def connectionFailed(self, connector, reason=protocol.connectionDone):
		log.msg('connection failed!')
		if len(self.connections)>0:
			self.doConnect()


	def _streamEnd(self, el):
		pass

	def _bind(self, el):
		#experimental
		log.msg('bind')
		bind = el.firstChildElement()
		jd = bind.firstChildElement().__str__()
		self.jid = jid.JID(jd)

	def disconnect(self):
		self.connection.disconnect()
		self.factory.stopTrying()
		self.connection = None
		self.factory = None

	def _regfailed(self, el):
		log.msg('reg failed')
		print el.toXml()

	#def _authd(self, el):

		log.msg('we are lucky, indeed')

	def _authfailed(self, el):
		log.msg('auth failed')
#		print el.toXml()
		print dir(self)
		self.factory.authenticator.registerAccount(self.jid.user, self.password)
		print 'trying to register'

	def _invaliduser(self, el):
		log.msg('invalid user')
		self.factory.authenticator.registerAccount(self.jid.user, self.password)
		print 'trying to register'
		print el.toXml()
