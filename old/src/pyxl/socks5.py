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

from twisted.internet.interfaces import ITransport
from twisted.internet.base      import BaseConnector
from twisted.internet           import  tcp
##from twisted.internet           import  reactor
from twisted.internet           import protocol, defer
from twisted.python             import log, failure
import struct, re, socket, sys
from zope.interface import implements
from sockserror import *
from twisted.internet import interfaces
from twisted.words.xish.domish import Element
from twisted.words.protocols.jabber.xmlstream import IQ
# Used to distinguish IP address from domain name
# TODO: should this be optimized somehow?
#
_ip_regex = re.compile ("\d\d?\d?\.\d\d?\d?\.\d\d?\d?\.\d\d?\d?")
from twisted.protocols.basic  import FileSender
import  os.path, time
from base64 import b64encode, b64decode
from twisted.internet import protocol, reactor
import struct
try:
	from hashlib import sha1
except:
	log.msg('Please upgrade to python2.5')
	from sha import new as sha1
	
STATE_INITIAL = 0
STATE_AUTH    = 1
STATE_REQUEST = 2
STATE_READY   = 3
STATE_AUTH_USERPASS = 4
STATE_LAST    = 5

STATE_CONNECT_PENDING = STATE_LAST + 1

SOCKS5_VER = 0x05

ADDR_IPV4 = 0x01
ADDR_DOMAINNAME = 0x03
ADDR_IPV6 = 0x04

CMD_CONNECT = 0x01
CMD_BIND = 0x02
CMD_UDPASSOC = 0x03

AUTHMECH_ANON = 0x00
AUTHMECH_USERPASS = 0x02
AUTHMECH_INVALID = 0xFF

REPLY_SUCCESS = 0x00
REPLY_GENERAL_FAILUR = 0x01
REPLY_CONN_NOT_ALLOWED = 0x02
REPLY_NETWORK_UNREACHABLE = 0x03
REPLY_HOST_UNREACHABLE = 0x04
REPLY_CONN_REFUSED = 0x05
REPLY_TTL_EXPIRED = 0x06
REPLY_CMD_NOT_SUPPORTED = 0x07
REPLY_ADDR_NOT_SUPPORTED = 0x08

class SOCKSv5Factory(protocol.Factory):

	def __init__(self, client):
		self.client = client
		self.sessions = {}
		
		
	def buildProtocol(self, addr):
		
		p = SOCKSv5('neco')
		p.factory = self
		return p
        
class SOCKSv5(protocol.Protocol):
   def __init__(self, tr = 'nic'):
       self.state = STATE_INITIAL
       self.buf = ""
       self.supportedAuthMechs = [ AUTHMECH_ANON ]
       self.supportedAddrs = [ ADDR_IPV4, ADDR_DOMAINNAME ]
       self.enabledCommands = [ CMD_CONNECT, CMD_BIND ]
       self.peersock = None
       self.addressType = 0
       self.requestType = 0
       self.tr = tr
       
       

   def _parseNegotiation(self):
       try:
           # Parse out data
           ver, nmethod = struct.unpack('!BB', self.buf[:2])
           methods = struct.unpack('%dB' % nmethod, self.buf[2:nmethod+2])

           # Ensure version is correct
           if ver != 5:
               self.transport.write(struct.pack('!BB', SOCKS5_VER, AUTHMECH_INVALID))
               self.transport.loseConnection()
               return

           # Trim off front of the buffer
           self.buf = self.buf[nmethod+2:]
           
           # Check for supported auth mechs
           for m in self.supportedAuthMechs:
               if m in methods:
                   # Update internal state, according to selected method
                   if m == AUTHMECH_ANON:
                       self.state = STATE_REQUEST
                   elif m == AUTHMECH_USERPASS:
                       self.state = STATE_AUTH_USERPASS
                   # Complete negotiation w/ this method
                   self.transport.write(struct.pack('!BB', SOCKS5_VER, m))
                   return

           # No supported mechs found, notify client and close the connection
           self.transport.write(struct.pack('!BB', SOCKS5_VER, AUTHMECH_INVALID))
           self.transport.loseConnection()
       except struct.error:
           pass

   def _parseUserPass(self):
       try:
           # Parse out data
           ver, ulen = struct.unpack('BB', self.buf[:2])
           uname, = struct.unpack('%ds' % ulen, self.buf[2:ulen + 2])
           plen, = struct.unpack('B', self.buf[ulen + 2])
           password, = struct.unpack('%ds' % plen, self.buf[ulen + 3:ulen + 3 + plen])
           # Trim off fron of the buffer
           self.buf = self.buf[3 + ulen + plen:]
           # Fire event to authenticate user
           if self.authenticateUserPass(uname, password):
               # Signal success
               self.state = STATE_REQUEST
               self.transport.write(struct.pack('!BB', SOCKS5_VER, 0x00))
           else:
               # Signal failure
               self.transport.write(struct.pack('!BB', SOCKS5_VER, 0x01))
               self.transport.loseConnection()
       except struct.error:
           pass

   def sendErrorReply(self, errorcode):
       # Any other address types are not supported
       result = struct.pack('!BBBBIH', SOCKS5_VER, errorcode, 0, 1, 0, 0)
       self.transport.write(result)
       self.transport.loseConnection()

   def _parseRequest(self):
       try:
           # Parse out data and trim buffer accordingly
           ver, cmd, rsvd, self.addressType = struct.unpack('!BBBB', self.buf[:4])

           # Ensure we actually support the requested address type
           if self.addressType not in self.supportedAddrs:
               self.sendErrorReply(REPLY_ADDR_NOT_SUPPORTED)
               return

           # Deal with addresses
           if self.addressType == ADDR_IPV4:
               addr, port = struct.unpack('!IH', self.buf[4:10])
               self.buf = self.buf[10:]
           elif self.addressType == ADDR_DOMAINNAME:            
               nlen = ord(self.buf[4])
               addr, port = struct.unpack('!%dsH' % nlen, self.buf[5:])
               self.buf = self.buf[7 + len(addr):]
           else:
               # Any other address types are not supported
               self.sendErrorReply(REPLY_ADDR_NOT_SUPPORTED)
               return

           # Ensure command is supported
           if cmd not in self.enabledCommands:
               # Send a not supported error
               self.sendErrorReply(REPLY_CMD_NOT_SUPPORTED)
               return

           # Process the command
           if cmd == CMD_CONNECT:
               self.connectRequested(addr, port)
           elif cmd == CMD_BIND:
               self.bindRequested(addr, port)
           else:
               # Any other command is not supported
               self.sendErrorReply(REPLY_CMD_NOT_SUPPORTED)

       except struct.error, why:
           return None


   def connectRequested(self, addr, port):
       log.msg('on connect')
       
       if self.factory.sessions.has_key(addr):
	       self.transport.stopReading()
	       self.state = STATE_CONNECT_PENDING
	#       protocol.ClientCreator(reactor, SOCKSv5Outgoing, self).connectTCP(addr, port)

	       
	       
	       sid = self.factory.sessions[addr]
	       self.factory.client.ft[sid].protocol = Send()
	       self.factory.client.ft[sid].protocol.transport = self.transport
	       self.factory.client.ft[sid].protocol.ft = self.factory.client.ft[sid]
	       self.factory.client.ft[sid].ftstart = time.time()
	       self.connectCompleted(addr, port)
       else:
          self.sendErrorReply(REPLY_CONN_REFUSED)

   def connectCompleted(self, remotehost, remoteport):
       if self.addressType == ADDR_IPV4:
           result = struct.pack('!BBBBIH', SOCKS5_VER, REPLY_SUCCESS, 0, 1, remotehost, remoteport)
       elif self.addressType == ADDR_DOMAINNAME:
           result = struct.pack('!BBBBB%dsH' % len(remotehost), SOCKS5_VER, REPLY_SUCCESS, 0,
                                ADDR_DOMAINNAME, len(remotehost), remotehost, remoteport)
       self.transport.write(result)
       self.state = STATE_READY
       self.transport.startReading()
   
   def bindRequested(self, addr, port):
       pass
   
   def authenticateUserPass(self, user, passwd):
       log.msg("User/pass: " + unicode(user) + unicode(passwd))
       return True


   def dataReceived(self, buf):
       if self.state == STATE_READY:
           self.transport.write(buf)
           return

       self.buf = self.buf + buf
       if self.state == STATE_INITIAL:
           self._parseNegotiation()
       if self.state == STATE_AUTH_USERPASS:
           self._parseUserPass()
       if self.state == STATE_REQUEST:
           self._parseRequest()



class ClientProtocol (protocol.Protocol):
	""" This protocol that talks to SOCKS5 server from client side.
	"""
	__implements__ = ITransport,
	disconnecting = 0
	def __init__(self, sockshost, socksport, host, port, factory, otherProtocol,
		method="CONNECT", login=None, password=None, xmpp = None, xmpp_sid = None):
		""" Initializes SOCKS session
		
		@type sockshost: string
		@param sockshost: Domain name or ip address of intermediate SOCKS 
		server.
		
		@type socksport: int
		@param socksport: Port number of intermediate server.
		
		@type host: string
		@param host: Domain name or ip address where should connect or bind.
		
		@type port: int
		@param port: Port number where to connect or bind.
		
		@type otherProtocol: object
		@param otherProtocol: Initialised protocol instance, which will receive
			all I/O and events after SOCKS connected.
		
		@type login: string
		@param login: Sets user name if SOCKS server requires us to
			authenticate.
		
		@type password: string
		@param password: Sets user password if SOCKS server requires us
			to authenticate.
		
		@type method: string
		@param method: What to do: may be \"CONNECT\" only. Other
			methods are currently unsupported.
		"""
		# login and password are limited to 256 chars
		#
		if login is not None and len (login) > 255:
			raise LoginTooLongError()
		
		if password is not None and len (password) > 255:
			raise PasswordTooLongError()
		
		# save information
		#
		self.method         = method
		self.host           = host
		self.port           = port
		self.login          = login
		self.password       = password
		self.state          = "mustNotReceiveData"
		self.otherProtocol  = otherProtocol
		self.factory        = factory
		self.xmpp = xmpp
		self.xmpp_sid = xmpp_sid

	def connectionMade(self):
		# prepare connection string with available authentication methods
		#
	
		log.msg("SOCKS5.connectionMade")
		methods = "\x00"
		if not self.login is None: methods += "\x02"
	
		connstring = struct.pack ("!BB", 5, len (methods))
	
		self.transport.write (connstring + methods)
		self.state = "gotHelloReply"

	def dataReceived (self, data):
		#log.msg("SOCKS state=" + self.state)
		method = getattr(self, 'socks_%s' % (self.state), 
			self.socks_thisMustNeverHappen)
		method (data)

	def socks_thisMustNeverHappen (self, data):
		self.transport.loseConnection()
		raise UnhandledStateError ("This SOCKS5 self.state (%s) "\
			"must never happen %s" % (self.state, self))

	def socks_mustNotReceiveData (self, data):
		""" This error might occur when server tells something into connection
		right after connection is established. Server in this case is
		certainly not SOCKS.
		"""
		self.transport.loseConnection()
		self.factory.clientConnectionFailed (self, failure.Failure (
			UnexpectedDataError ("Server must not send data before client %s" % 
self)))

	def socks_gotHelloReply (self, data):
		""" Receive server greeting and send authentication or ask to
		execute requested method right now.
		"""
		if data == "\x05\xFF":
			# No acceptable methods. We MUST close
			#
			log.msg("No acceptable methods, closing connection")
			self.transport.loseConnection()
			return

		elif data == "\x05\x00":
			# Anonymous access allowed - let's issue connect
			#
			self.sendCurrentMethod()

		elif data == "\x05\x02":
			# Authentication required
			#
			self.sendAuth()

		else:
			self.transport.loseConnection()
			self.factory.clientConnectionFailed (self, failure.Failure (
				UnhandledData ("Server returned unknown reply in gotHelloReply")))

		# From now on SOCKS server considered alive - we've got reply
		#
		self.factory.status = "connected"

	def socks_gotAuthReply (self, data):
		""" Called when client received server authentication reply,
			we or close connection or issue "CONNECT" command
		"""
		if data == "\x05\x00":
			self.sendCurrentMethod()

	def sendAuth (self):
		""" Prepare login/password pair and send it to the server
		"""
		command = "\x05%s%s%s%s" % (chr (len (self.login)), self.login,
			chr (len (self.password)), self.password)
		self.transport.write (command)

		self.state = "gotAuthReply"

	def sendCurrentMethod (self):
		method = getattr(self, 'socks_method_%s' % (self.method), 
			self.socks_method_UNKNOWNMETHOD)
		method()

	def socks_method_UNKNOWNMETHOD (self):
		self.transport.loseConnection()
		self.factory.clientConnectionFailed (self, failure.Failure (
			UnknownMethod ("Method %s is unknown %s" % (self.method, self))))

	def socks_method_CONNECT (self):
		# Check if we have ip address or domain name
		#
		log.msg("socks_method_CONNECT host = " + self.host)

	# The FaceTime SOCKS5 proxy treats IP addr the same way as hostname
	   # if _ip_regex.match (self.host):
	   #     # we have dotted quad IP address
	   #     addressType = 1
	   #     address = socket.inet_aton (self.host)
	   # else:
	   #     # we have host name
	   #     address = self.host
	   #     addressType = 3

		address = self.host
		addressType = 3
		addressLen = len(address)

		#Protocol version=5, Command=1 (CONNECT), Reserved=0
		#command = struct.pack ("!BBBB", 5, 1, 0, addressType)

		command = struct.pack ("!BBBBB", 5, 1, 0, addressType,addressLen)
		portstr = struct.pack ("!H", self.port)

		self.transport.write (command + address + portstr)
		self.state = "gotConnectReply"

	def socks_gotConnectReply (self, data):
		""" Called after server accepts or rejects CONNECT method.
		"""
		if data[:2] == "\x05\x00":
			# No need to analyze other fields of reply, we are done
			#
			self.state = "done"
			self.factory.status = "established"

			self.otherProtocol.transport = self
			self.otherProtocol.connectionMade()
			self.otherProtocol.ft = self.xmpp.ft[self.xmpp_sid]
			self.xmpp.ftStart(self.xmpp_sid, self.otherProtocol)
			return 

		errcode = ord (data[1])

		if errcode < len (SOCKS_errors):
			self.transport.loseConnection()
			self.factory.clientConnectionFailed (self, failure.Failure (
				ConnectError ("%s %s" % (SOCKS_errors[errcode], self))))
		else:
			self.transport.loseConnection()
			self.factory.clientConnectionFailed (self, failure.Failure (
				ConnectError ("Unknown SOCKS error after CONNECT request issued %s" % (self))))
		
		self.otherProtocol.ft = self.xmpp.ft[self.xmpp_sid]
		self.otherProtocol.ft.connectFailure()

	def socks_done (self, data):
		""" Proxy received data to other protocol.
		"""
		self.otherProtocol.dataReceived (data)
	#
	# Transport relaying
	#
	def write(self, data):
		self.transport.write(data)

	def writeSequence(self, data):
		self.transport.writeSequence(data)

	def loseConnection(self):
		self.disconnecting = 1
		self.transport.loseConnection()

	def getPeer(self):
		return self.transport.getPeer()

	def getHost(self):
		return self.transport.getHost()
	
	def registerProducer(self, producer, streaming):
		self.transport.registerProducer(producer, streaming)

	def unregisterProducer(self):
		self.transport.unregisterProducer()

	def stopConsuming(self):
		self.transport.stopConsuming()

class ClientConnector (tcp.Connector):
	"""Object used to connect to some host using intermediate server
	supporting SOCKS5 protocol.

	This IConnector manages one connection.
	"""
	def __init__(self, sockshost, socksport, host, port, otherFactory,
		reactor=None, method="CONNECT", login=None, password=None,
		timeout=None, readableID=None):
		""" Creates IConnector to connect through SOCKS

		@type sockshost: string
		@param sockshost: SOCKS5 compliant server address.

		@type socksport: int
		@param socksport: Port to use when connecting to SOCKS.

		@type timeout: float
		@param timeout: Time to wait until client connects, then fail.

		@type readableID: string
		@param readableID: Some human readable ID for this connection.

		See ClientProtocol constructor for details on other params.
		"""
		factory = ClientFactory (method=method, sockshost=sockshost,
			socksport=socksport, host=host, port=port, login=login,
			password=password, otherFactory=otherFactory, timeout=timeout,
			readableID=readableID)

		tcp.Connector.__init__ (self, host=sockshost, port=socksport,
			factory=factory, timeout=timeout, bindAddress=None,
			reactor=reactor)

class ClientFactory (protocol.ClientFactory):
	def __init__(self, sockshost, socksport, host, port, otherFactory,
		method="CONNECT", login=None, password=None, timeout=60,
		readableID=None, xmpp = None, xmpp_sid = None):
		""" Factory creates SOCKS5 client protocol to connect through it.
		See ClientProtocol constructor for details on params.
		
		@type globalTimeout: int
		@param globalTimeout: Seconds before connection is completely and
			unconditionally closed as is.

		@type readableID: string
		@param readableID: Some human readable ID for this connection.
		"""
		self.sockshost      = sockshost
		self.socksport      = socksport
		self.host           = host
		self.port           = port
		self.method         = method
		self.login          = login
		self.password       = password
		self.otherFactory   = otherFactory
		self.timeout        = timeout
		self.readableID     = readableID
		self.xmpp = xmpp
		self.xmpp_sid = xmpp_sid

		# This variable contains current status of SOCKS connection,
		# useful for diagnosting connection, without knowing SOCKS
		# internal states. One of: "unconnected", "connected" (SOCKS
		# server replied and is alive), "established"
		#
		self.status = "unconnected"

	def startedConnecting (self, connector):
		# Set global timeout
		#
		if self.timeout is not None:
		   log.msg ("Set timeout %d sec" % self.timeout)
		   delayedcall = self.xmpp.reactor.callLater (self.timeout, self.onTimeout, connector)
		   setattr (self, "delayed_timeout_call", delayedcall)

		# inherited
		#
		protocol.ClientFactory.startedConnecting (self, connector)

	def onTimeout (self, connector):
		""" Timeout occured, can't continue and should stop immediately
		and unconditionally in the whatever state I am.
		"""
		connector.disconnect()
		log.msg ("%s timeout %d sec" % (self, self.timeout))
		self.clientConnectionFailed (self, failure.Failure (
			GlobalTimeoutError ("Timeout %s" % self)))

	def stopFactory(self):
		""" Do cleanups such as cancelling timeout
		"""
		try:
			if self.timeout is not None:
			   self.delayed_timeout_call.cancel()
		except:
			pass
		if not self.status == 'unconnected':
			if self.xmpp.ft.has_key(self.xmpp_sid):
				if self.xmpp.ft[self.xmpp_sid].transfered >= int(self.xmpp.ft[self.xmpp_sid].size):
					self.xmpp.ft[self.xmpp_sid].finish()
#				print 'stopFactory::finish'
				else:
					self.xmpp.ft[self.xmpp_sid].connectFailure()
			else:
				log.err('no sid')
#		protocol.ClientFactory.stopFactory (self)

	def buildProtocol (self, a):
		""" Connection is successful, create protocol and let it talk to peer.
		"""
		proto = ClientProtocol (sockshost=self.sockshost,
			socksport=self.socksport, host=self.host, port=self.port,
			method=self.method, login=self.login, password=self.password,
			otherProtocol=self.otherFactory.buildProtocol (self.sockshost),
			factory=self, xmpp = self.xmpp, xmpp_sid = self.xmpp_sid)

		proto.factory = self
		return proto

	def __repr__ (self):
		return "<SOCKS %s>" % self.readableID

	def clientConnectionLost(self, connector, reason):
		# If flag indicates that connection may not be lost
		#
		rmap = {"reason": reason, "socks": self.status}
		try:
			if self.xmpp.ft[self.xmpp_sid].size > 	self.xmpp.ft[self.xmpp_sid].transfered:
				pass
#				self.xmpp.ft[self.xmpp_sid].error = "Connection lost"
			else:
				self.xmpp.ft[self.xmpp_sid].connectFailure()
		except:
			log.err('sid doesn\'t exist?')
			
		try:
			if self.status != "established":
				# Tell about error
				#
				log.msg ("Connection LOST before SOCKS established %s" % self)
				self.otherFactory.clientConnectionFailed (connector, rmap)

			else:
				self.otherFactory.clientConnectionLost (connector, rmap)
			

		except:
			ei = sys.exc_info()
			if not str (ei[0]).count ("AlreadyCalled"):
				raise
	
	def clientConnectionFailed(self, connector, reason):
		# I can't know where to get deferred, let factory do this itself
		#
		rmap = {"reason": reason, "socks": self.status}

		try:
			if self.status != "established":
				log.msg ("Connection FAILED before SOCKS established %s" % self)
				self.otherFactory.clientConnectionFailed (connector, rmap)
#				self.stopFactory()
				self.xmpp.ft[self.xmpp_sid].connectFailure()
				self.xmpp.ft[self.xmpp_sid].error = "Can't connect."
			else:
				self.otherFactory.clientConnectionFailed (connector, rmap)
		except:
			ei = sys.exc_info()
			if not str (ei[0]).count ("AlreadyCalled"):
				raise


class ProxyClientCreator(protocol.ClientCreator):

	def connectSocks5Proxy(self,remotehost,remoteport,proxy,proxyport,id):
	   d = defer.Deferred()
	   f = protocol._InstanceFactory(self.reactor, self.protocolClass(*self.args, **self.kwargs),d)
	   self.reactor.connectWith(ClientConnector,	host=remotehost,port=remoteport, sockshost=proxy, socksport=proxyport, otherFactory=f, readableID=id)
	   return d


class Send(protocol.Protocol):
	implements(interfaces.IConsumer)
	
	def __init__(self):
		self.last = time.time()
		log.msg('send >> init')
		pass
	
	def registerProducer(self, producer, streaming):
		log.msg('send >> registerProducer')
		self. producer = producer
		return self.transport.registerProducer(producer, streaming)
	
	def unregisterProducer(self):
		log.msg('send >>unregisterProducer')
		self.transport.unregisterProducer()
		self.transport.loseConnection()
		

	def write(self, data):
#		print 'prenasim: ', len(data)
		cekej = 0
		kolik = float(len(data))
		ted = time.time()
		doba = ted - self.last
		if doba == 0:
			doba = 0.001 #dostatecne male cislo?
		try:
			limit = self.ft.getLimit('upload')/2
		
		except:
			limit = 0
			
		if kolik/doba >limit and limit >0:
			
			cekej = (kolik/limit)
			
			if cekej <0:
				cekej = 0
		
		reactor.callLater(cekej,  self.doWriteToTransport, data)
		self.last = ted
		
	def doWriteToTransport(self, data):
		self.transport.write(data)
		try:
			self.ft.connector.factory.delayed_timeout_call.cancel()
		except:
#			print 'delayed_timeout_call'
			pass
		if self.ft:
			self.ft.transfered = self.ft.transfered + len(data)
			self.ft.client.dispatcher.publishEvent('on_ftTransfered', self.ft.sid, len(data))
			if self.ft.transfered >= self.ft.size:
				self.ft.finish()
				log.msg('sending finished')
				self.unregisterProducer()


	
class Receive(protocol.Protocol):

	def unregisterProducer(self):
		self.transport.unregisterProducer()
		self.transport.loseConnection()

	def dataReceived(self, data):
		
		if self.ft.fp != None:
			self.ft.fp.write(data)
			self.ft.transfered = self.ft.transfered + len(data)
			try:

				self.ft.client.dispatcher.publishEvent('on_ftTransfered', self.ft.sid, len(data))
			except:
				pass
		try:
			self.ft.connector.factory.delayed_timeout_call.cancel()
		except:
			pass
		if self.ft.transfered == self.ft.size:
#			self.ft.finish()
			try:
				self.ft.connector.factory.stopFactory()
			except:
				pass

class FTSend:
	def __init__(self, client, sid, filename, tojid, file, description= None, frmjid = None):
		self.sid = sid
		self.filename = filename
		self.file=filename
		self.fp = open(file, 'rb')
		self.size = os.path.getsize(file)
		self.description = description
		self.client = client
		self.tojid = tojid
		self.protocol = None
		self.transfered = 0
		self.streamhost = None
		self.connector = None
		self.error = None	
		self.fs = None	
		self.ibbSeq = 0
		self.frmjid = frmjid


	
	def activate(self):
		log.msg('received activate for '+self.filename)
		iq = IQ(self.client.xmlstream, 'set')
		iq['to'] = self.streamhost
		if self.frmjid != None:
			iq['from'] = self.frmjid
		q = iq.addElement('query', 'http://jabber.org/protocol/bytestreams')
		q['sid'] = self.sid
		q.addElement('activate', content = self.tojid)
		self.client.on_xml(iq.toXml())
		d = iq.send()
		self.client.disp(iq['id'])
		d.addCallback(self._activated).addErrback(self._activateFailed)
	
	def _activateFailed(self, err):
		log.msg('activate failed with: ' + unicode(err))
		self.client.on_ftEnd(self.sid, 'activate error')
		
	def _activated(self, el = None):
		print self.fp
		FileSender().beginFileTransfer(self.fp, self.protocol)#. addCallback(self._finished)
	
	def _finished(self, last):
		log.msg('finished transfer for ' + self.filename)
		log.msg('times: %i - %i - %i - %i'%(self.start, self.medium, self.ftstart, time.time())) 
	
	def finish(self):
		log.msg("konec prenosu")
		if self.fp != None:
			self.fp.close()
		addr = sha1("%s%s%s" % (self.sid, self.client.jid.full(), self.tojid)).hexdigest()
		try:
			self.protocol.transport.loseConnection()
			del self.client.socks5Srv.factory.sessions[addr]
			if len(self.client.socks5Srv.factory.sessions)==0:
				self.client.socks5Srv.loseConnection()
		except:
			log.err('unable to finish socks5')
			log.err(unicode(self.client.socks5Srv.factory.sessions))
			pass

		self.client.on_ftEnd(self.sid, self.error)

	def connectFailure(self):
		pass
		

class FTReceive:
	def __init__(self, client,jid, sid, file, methods, frmjid,answerId=None):
		self.client = client
		self.tojid = jid
		self.sid = sid
		self.fileprops = file
		self.methods = methods
		self.fp = None
		self.method = None
		self.file = None #sem to chceme ulozit
		self.streamhosts = []
		self.streamhostsID = None
		self.activeStreamhost = None
		self.size = int(self.fileprops['size'])
		self.transfered = 0
		self.ibbSeq = 0
		self.ibbCache = {}
		self.connector = None
		self.error = None
		self.frmjid = frmjid
		self.answerId=answerId
	
	def connectStreamHost(self):
		log.msg(self.streamhosts)
		streamhost = self.streamhosts.pop(0)
		self.activeStreamhost = streamhost
		f = protocol.ClientFactory()
		f.protocol = Receive
		addr = sha1("%s%s%s" % (self.sid,  self.tojid, self.frmjid)).hexdigest()
		factory = ClientFactory(streamhost['host'], int(streamhost['port']),addr, 0,  f, xmpp = self.client, xmpp_sid = self.sid) 
		self.connector = self.client.reactor.connectTCP(streamhost['host'], int(streamhost['port']), factory)
	
	def connectFailure(self):
		log.msg('connect failed')

		if len(self.streamhosts)>0:
			self.connector = None
			self.activeStreamhost = None
			self.connectStreamHost()
		else:
			log.msg('nemuzu se spojit')
	
	def activate(self):
		log.msg('activate!')
		iq = Element((None,'iq'))
		iq['to'] = self.tojid
		iq['from'] = self.frmjid
		iq['id'] = self.streamhostsID
		iq['type'] = 'result'
		query = iq.addElement('query', 'http://jabber.org/protocol/bytestreams')
		used = query.addElement('streamhost-used')
		used['jid'] = self.activeStreamhost['jid']
		
		self.streamhosts = []
		self.error = None
		self.fp = open(self.file, 'wb')
		self.client.xmlstream.send(iq)
	
	def ibbProcess(self):
		c = True
		while c:
			if self.ibbCache.has_key(self.ibbSeq):
				
				data = b64decode(self.ibbCache[self.ibbSeq])
				self.transfered = self.transfered + len(data)
				self.client.on_ftTransfered(self.sid, len(data))
				self.fp.write(data)
				self.ibbSeq = self.ibbSeq + 1
			else:
				c = False
			
		
	
	def finish(self):
		
		if len(self.streamhosts) == 0:
			log.msg("konec prenosu")
			if self.fp != None:
				self.fp.close()
				self.fp = None
				self.client.on_ftEnd(self.sid, self.error)
