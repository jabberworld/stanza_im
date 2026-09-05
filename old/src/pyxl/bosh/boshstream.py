from twisted.web2.client.http import HTTPClientProtocol, ClientRequest
from twisted.web2.client.interfaces import IHTTPClientManager
from twisted.internet import reactor, protocol, defer
from twisted.words.xish import domish, utility, xmlstream
from twisted.web2 import http_headers
from twisted.python import log
from zope.interface import implements
import urlparse
import random
from hashlib import sha1
import time

STREAM_CONNECTED_EVENT = intern("//event/stream/connected")
STREAM_START_EVENT = intern("//event/stream/start")
STREAM_END_EVENT = intern("//event/stream/end")
STREAM_ERROR_EVENT = intern("//event/stream/error")

FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def dump(src, length=8):
	N=0; result=''
	while src:
	   s,src = src[:length],src[length:]
	   hexa = ' '.join(["%02X"%ord(x) for x in s])
	   s = s.translate(FILTER)
	   result += "%04X   %-*s   %s\n" % (N, length*3, hexa, s)
	   N+=length
	return result


class BOSHParser:
	"""
	Wrapping an element stream for parsing <body/> documents
	"""

	def parse(self, buf):
		self._reset()
		self.stream.parse(buf)
		return self.body, self.xmpp_elements
	
	def onDocumentStart(self, rootelem):
		if rootelem.name == 'body':
			self.body = rootelem
		else:
			log.err('rootelem is not body >> %s,%s '%(rootelem.name, rootelem))

	def onElement(self, element):
		if isinstance(element, domish.Element):
			self.xmpp_elements.append(element)
		else:
			pass

	def _reset(self):
		self.stream = domish.elementStream()
		self.stream.DocumentStartEvent = self.onDocumentStart
		self.stream.ElementEvent = self.onElement
		self.stream.DocumentEndEvent = self.onDocumentEnd
		self.body = domish.Element((None,""))
		self.xmpp_elements = []

	def onDocumentEnd(self):
		pass


class BOSHStream(utility.EventDispatcher):
	"""
	Transport implementing a bidirectional stream over an HTTP channel
	as in XEP-0124 (http://www.xmpp.org/extensions/xep-0124.html)
	"""

	implements(IHTTPClientManager)

	MAX_RECONNECT_INTERVAL = 10

	def __init__(self):
		utility.EventDispatcher.__init__(self)
		self.connected=False
		self.parser = BOSHParser()
		self.rawDataOutFn = None
		self.rawDataInFn = None
		self.sid = None
		self.rid = random.randint(0, 1000000)
		self.send_queue = [] # objects awaiting for being sent
		self.out_queue = [] # objects awaiting for ack
		self.out_queue2 = [] # objects awaiting for ack
		self.resend_queue = [] # bodies that must be resent
		self.initialized = False
		self.reconnect_interval = 0
		self.firstSent=False
		self.seed=random.randint(1000, 1000000)
		self.n=random.randint(0, 1000000)
		self.timestamp=time.time()
		self.ready=False
		self.proto=None
		self.empty=False
		self.emptysck=0


	def _build_first_request(self):
		url = urlparse.urlparse(self.factory.bosh_url)
		try:
			self.host, port = url[1].split(":")
			self.port = int(port)
		except:
			self.host = url[1]
			self.port = 80
		self.path = url[2].encode("utf-8")

		self.bosh_attrs = self.factory.bosh_attrs
		print self.factory.proxy
		if self.factory.proxy != None:
			self.host = self.factory.proxy['host']
			self.port = int(self.factory.proxy['port'])
			self.path = self.factory.bosh_url.replace(':80',  '').encode("utf-8") #hack!
	
		
		if not self.path.endswith('/'):
			self.path += '/'
		print self.host , 	self.port , self.path
		# now queue the first body for initializing the session
		body = domish.Element(("http://jabber.org/protocol/httpbind", "body"))
		#body["rid"] = `self.rid`
		#body['newkey'] = str(sha1(str(self.seed)).hexdigest())
		
		#self.rid += 1
		for k,v in self.factory.bosh_attrs.items():
			body[k.encode('utf-8')] = v.encode("utf-8")
		body['route']="xmpp:"+body['to']+":5222"
		body['wait']="40"
		body['hold']="2"
		self.resend_queue.append(body)
		print 'first request'
		


	def send(self, obj):
		"""
		Send some payload to the server
		@param obj: a valid xml chunk or a L{domish.Element} that must be sent to the server
		"""
		#if domish.IElement.providedBy(obj):
		#    obj = obj.toXml()

		#if self.rawDataOutFn:
		#    self.rawDataOutFn(obj)
		
		self.send_queue.append(obj)
		self._try_to_send()


	def _try_to_send(self):
		"""
		"""
		# check if there are too many packets out
		if time.time()-self.timestamp<2:
			if not self.ready:
				self.ready=True
				reactor.callLater(2,self._try_to_send)
			return
		

		print 'to send',self.proto,self.proto2,len(self.out_queue),len(self.out_queue2)
		if not (len(self.out_queue2)<1 and self.proto2) and not (len(self.out_queue)<1 and self.proto):
			for b in self.out_queue + self.out_queue2:
				print [b.toXml().encode("utf-8")]
			reactor.callLater(2,self._try_to_send)
			return
		
			
		print 'to send1'
		if not self.resend_queue and len(self.send_queue) == 0 and len(self.out_queue)!=0 and len(self.out_queue2)!=0:
			return

		print 'to send2'

		for b in self.send_queue:
			print "send_queue",[b.toXml().encode("utf-8")]

		self.ready=False
		self.timestamp=time.time()
		isBody=False
		#force_proto=False
		if self.resend_queue:
			body = self.resend_queue.pop(0)
			if self.firstSent:
				print "EMPTY BODY WILL BE SENT0"
				isBody=True
			#force_proto=True
		else:
			# ok, we can send a request
			body = domish.Element(("http://jabber.org/protocol/httpbind", "body"))
		
			if self.sid: body["sid"] = self.sid
			#body["rid"] = `self.rid`
			#self.rid += 1
			if len(self.send_queue)==0:
				#force_proto=True
				if self.empty:
					return
				isBody=True
				self.firstSent=True
				reactor.callLater(0.5,self._try_to_send)
				print "EMPTY BODY WILL BE SENT1"
			if not self.empty and self.firstSent:
				isBody=True
				reactor.callLater(0.5,self._try_to_send)
				print "EMPTY BODY WILL BE SENT2",self.send_queue
			else:
				if len(self.out_queue2)<1 and self.proto2 and not isBody:
					while self.send_queue:
						obj = self.send_queue.pop(0)
						if domish.IElement.providedBy(obj):
							body.addChild(obj)
						else:
							body.addRawXml(obj)
				else:
					print "can't send this body, because there is something in queue",self.out_queue2
					reactor.callLater(2,self._try_to_send)
					return
					
		if self.rawDataOutFn:
			self.rawDataOutFn(body.toXml())
		thead = http_headers.Headers()
		thead.addRawHeader("Content-Type", "text/xml; charset=utf-8")
		#thead.addRawHeader("Accept-Encoding", "gzip, deflate")
		thead.addRawHeader("Host", self.host.encode("utf-8"))
#		thead.addRawHeader("Proxy-Connection", "Keep-Alive")
#		thead.addRawHeader("Connection", "Keep-Alive")
		#print body.toXml().encode("ascii")
		#print dump(buffer(body.toXml().encode("ascii"),0))
		

		print "QUEUE DUMP",self.out_queue2,self.out_queue
		if len(self.out_queue)<1 and self.proto and isBody:
			body["rid"] = `self.rid`
			self.rid += 1
			req = ClientRequest(
				"POST", 
				self.path, 
				thead,
				unicode(body.toXml()).encode("utf-8")
			)
			self.proto.submitRequest(req, False).addCallback(self.got_response,True).addErrback(self.got_error)
			self.out_queue.append(body)
			print [body.toXml().encode("utf-8")]
			print 'send1'
			if isBody:
				self.empty=1
		elif len(self.out_queue2)<1 and self.proto2 and not isBody:
			body["rid"] = `self.rid`
			self.rid += 1
			req = ClientRequest(
				"POST", 
				self.path, 
				thead,
				unicode(body.toXml()).encode("utf-8")
			)
			self.proto2.submitRequest(req, False).addCallback(self.got_response,False).addErrback(self.got_error)
			self.out_queue2.append(body)
			print [body.toXml().encode("utf-8")]
			print 'send2'
			if isBody:
				self.empty=2
		print "QUEUE DUMP AFTER",self.out_queue2,self.out_queue
		if len(self.send_queue)!=0:
			reactor.callLater(2,self._try_to_send)

	def got_response(self, resp, first):
		print 'read the body'
		print dir (resp)
		print resp.headers
		temp=resp.stream.read()
		print temp
		if temp:
			temp.addCallback(self.got_data,resp,"",first).addErrback(self.got_error)
		else:
			print "None readed?!"
			if first:
				print self.out_queue.pop(0)
			else:
				print self.out_queue2.pop(0)
		return

	def got_data(self, d, resp,data="",first=None): 
		if d:
			data+=d
		temp=resp.stream.read()
		if temp:
			temp.addCallback(self.got_data,resp,data,first)
			return
	
		try:
			if self.rawDataInFn: self.rawDataInFn(data)
			print [data]
			body, xmpp_elements = self.parser.parse(data)
			if not self.initialized:
				self.session_created(body)
			for el in xmpp_elements:
				print  "received:",[el.toXml().encode("utf-8")]
				if domish.IElement.providedBy(el):
					self.dispatch(el)    
			# this is an ack for the outgoing packets
			if first:
				self.out_queue.pop(0)
			else:
				self.out_queue2.pop(0)
			reactor.callLater(0.5,self._try_to_send)
			if len(self.out_queue2)==0 and len(self.out_queue)==0:
				self.empty=False
		except domish.ParserError:
			# i'm unsure about this because if we receive only part
			# of the message we send it (but in this case I'm not sure that
			#got_data is called)
			print "dispatch error"
			print resp.code
#			self.dispatch(self, STREAM_ERROR_EVENT)
#			self.transport.loseConnection()

	def got_error(self, fault):
		print "FUCK",fault,unicode(fault),dir(fault)
#		self.dispatch(self, STREAM_ERROR_EVENT)
#		self.transport.loseConnection()

	def session_created(self, body):
		print "session created"
		print type(body)
		if body.hasAttribute("sid"):
			self.sid = body["sid"]
			self.dispatch(self, STREAM_START_EVENT)
			self.initialized = True
		else:
			self.dispatch(self, STREAM_ERROR_EVENT)

	def clientBusy(self, proto):
		pass

	def clientIdle(self, proto):
		reactor.callLater(0, self._try_to_send)

	def clientPipelining(self, proto):
#		print "PIPELINE",proto
		reactor.callLater(0, self._try_to_send)

	def clientGone(self, proto):
		""" try to reconnect """
#		reactor.callLater(0, self.connect)
		self.reset()

	def connect(self):
		#d = protocol.ClientCreator(
			#reactor, HTTPClientProtocol, manager = self
		#).connectTCP(self.host, self.port)
		#d.addCallback(self.connect_done)
		#d.addErrback(self.connect_failed)
		reactor.connectTCP(self.host, self.port, self.factory)
		#reactor.connectTCP(self.host, self.port, self.factory)
		#HTTPClientProtocol(manager = self
		#d1 = protocol.ClientCreator(D
			#reactor, HTTPClientProtocol, manager = self
		#).connectTCP(self.host, self.port)
		#d1.addCallback(self.connect_done)
		#d1.addErrback(self.connect_failed)
		print 'connect!'

	def connect_done(self, proto):
		print "connection DONE"
		#if not self.initialized:
			#self._build_first_request()
		if not self.connected:
			if not self.proto:
				self.proto = proto
			else:
				self.proto2 = proto
				self._build_first_request()
				reactor.callLater(0, self._try_to_send)
				
				self.connected=True
				if not self.initialized:
					self.dispatch(self, STREAM_CONNECTED_EVENT)
				# XXX I don't like this: we should find some more elegant way
				#if hasattr(self, "connectionMade"):
				#    self.connectionMade()
		else:
			if not self.proto:
				self.proto = proto
			else:
				self.proto2 = proto
			reactor.callLater(0, self._try_to_send)
		self.reconnect_interval = 0

	def _connectionLost(self,proto):
		if proto == self.proto:
			print "proto1 closed"
			self.proto=None
			self.out_queue=[]
			if self.firstSent:
				body = domish.Element(("http://jabber.org/protocol/httpbind", "body"))
			
				if self.sid: body["sid"] = self.sid
				#body["rid"] = `self.rid`
				#self.rid += 1
				self.resend_queue.append(body)
			self.factory.connectors[0].disconnect()
			reactor.callLater(0,self._connect,self.factory.connectors[0])
		elif proto == self.proto2:
			self.proto2=None
			if self.out_queue2!=[]:
				body=self.out_queue2[0]
				#body["rid"] = `self.rid`
				#self.rid += 1
				self.send_queue.insert(0,body)
				self.out_queue2=[]
			#if self.firstSent and (not self.empty or self.empty==2):
				#body = domish.Element(("http://jabber.org/protocol/httpbind", "body"))
			
				#if self.sid: body["sid"] = self.sid
				#body["rid"] = `self.rid`
				#self.rid += 1
				#self.resend_queue.append(body)
			print "proto2 closed"
			self.factory.connectors[1].disconnect()
			reactor.callLater(0,self._connect,self.factory.connectors[1])
		#if self.proto or self.proto2:
			#reactor.connectTCP(self.host, self.port, self.factory)
			#reactor.callLater(self.reconnect_interval+1, self.connect)
			#if self.reconnect_interval < self.MAX_RECONNECT_INTERVAL:
				#self.reconnect_interval += 1

	def _connect(self,connector,t=0):
		print connector.state
		if connector.state=="disconnected":
			connector.connect()
		elif t<6:
			print "trying to reconnect...."
			reactor.callLater(1,self._connect,connector,t+1)
		else:
			print "was trying 5 times... that's enough"


	def connect_failed(self, fault):
		log.msg('connect faled in boshstream')
		reactor.callLater(self.reconnect_interval, self.connect)
		if self.reconnect_interval < self.MAX_RECONNECT_INTERVAL:
			self.reconnect_interval += 1

	def restart(self):
		body = domish.Element(("http://jabber.org/protocol/httpbind", "body"))
		
		body["xmlns:xmpp"] = "urn:xmpp:xbosh"
		body["xmpp:restart"] = "true"
		body["sid"] = self.sid
		#body["rid"] = `self.rid`
		#self.rid += 1
		self.resend_queue.append(body)
		self._try_to_send()
 
class XmlStreamFactoryMixin(object):  
	""" 
	XmlStream factory mixin that takes care of event handlers.  
	 
	To make sure certain event observers are set up before incoming data is  
	processed, you can set up bootstrap event observers using C{addBootstrap}.  
	 
	The C{event} and C{fn} parameters correspond with the C{event} and  
	C{observerfn} arguments to L{utility.EventDispatcher.addObserver}.  
	""" 
# 	protocol = BOSHStream
 
	def __init__(self, *args, **kwargs):  
		self.bootstraps = []  
		self.args = args  
		self.kwargs = kwargs  
 
	def buildProtocol(self, addr):  
		""" 
		Create an instance of XmlStream.  
		 
		The returned instance will have bootstrap event observers registered  
		and will proceed to handle input on an incoming connection.  
		""" 
		
		xs = self.protocol(*self.args, **self.kwargs)  
		xs.factory = self  
		for event, fn in self.bootstraps:  
			xs.addObserver(event, fn)  
		return xs 
	def addBootstrap(self, event, fn):  
		""" 
		Add a bootstrap event handler.  
		""" 
		self.bootstraps.append((event, fn))  
 
	def removeBootstrap(self, event, fn):  
		""" 
		Remove a bootstrap event handler.  
		""" 
		self.bootstraps.remove((event, fn))
		
class BOSHTTPClient(HTTPClientProtocol):
	
	def connectionMade(self):
		print "connectionMade"
		self.manager.connect_done(self)
		print "connectionMade end"
	
	def connectionLost(self,reason):
		self.manager._connectionLost(self)

	def connectionFailed(self,reason):
		print "CONNECTION FAILED"
		self.manager._connectionLost(self)

class BOSHStreamFactory(XmlStreamFactoryMixin, protocol.ClientFactory):
	bosh_client = None
	xs=None
	connectors=[]
	connectionFailedCount=0
	def buildProtocol(self, addr):
		print "buildProtocol",addr
		#if self.bosh_client != None:
			#return self.bosh_client
		if not self.xs:
			self.xs = XmlStreamFactoryMixin.buildProtocol(self, addr)
		bosh_client = BOSHTTPClient(manager = self.xs)
		bosh_client.factory = self
		self.connectionFailedCount=0
		#self.bosh_client = bosh_client
		
		return bosh_client

	def startedConnecting(self, connector):
		print "startedConnecting"
		if not connector in self.connectors:
			self.connectors.append(connector)

