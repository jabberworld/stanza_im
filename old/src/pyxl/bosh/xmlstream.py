from twisted.internet import reactor
from twisted.words.protocols.jabber.xmlstream import *
import boshstream

class XmlStream(boshstream.BOSHStream):
	"""
	XXX doc must be updated for reflecting BOSH stream

	XMPP XML Stream protocol handler.

	@ivar version: XML stream version as a tuple (major, minor). Initially,
				   this is set to the minimally supported version. Upon
				   receiving the stream header of the peer, it is set to the
				   minimum of that value and the version on the received
				   header.
	@type version: (L{int}, L{int})
	@ivar namespace: default namespace URI for stream
	@type namespace: L{str}
	@ivar thisHost: hostname of this entity
	@ivar otherHost: hostname of the peer entity
	@ivar sid: session identifier
	@type sid: L{str}
	@ivar initiating: Always true if this is the initiating stream
	@type initiating: L{bool}
	@ivar features: map of (uri, name) to stream features element received from
					the receiving entity.
	@type features: L{dict} of (L{str}, L{str}) to L{domish.Element}.
	@ivar prefixes: map of URI to prefixes that are to appear on stream
					header.
	@type prefixes: L{dict} of L{str} to L{str}
	@ivar initializers: list of stream initializer objects
	@type initializers: L{list} of objects that provide L{IInitializer}
	@ivar authenticator: associated authenticator that uses C{initializers} to
						 initialize the XML stream.
	"""

	version = (1, 0)
	namespace = 'invalid'
	thisHost = None
	otherHost = None
	sid = None
	initiating = True
	prefixes = {"xmpp": 'urn:xmpp:xbosh'}

	_headerSent = False     # True if the stream header has been sent

	def __init__(self, authenticator):
		boshstream.BOSHStream.__init__(self)

		self.authenticator = authenticator
		self.initializers = []
		self.features = {}

		# Reset the authenticator
		authenticator.associateWithStream(self)

		self.addOnetimeObserver(STREAM_CONNECTED_EVENT, self.connectionMade)
	def _callLater(self, *args, **kwargs):
		from twisted.internet import reactor
		return reactor.callLater(*args, **kwargs)
	def reset(self):
		"""
		Reset XML Stream.
		Not necessary for HTTP streams, kept for compatibility
		"""
		pass

	def onStreamError(self, errelem):
		"""
		Called when a stream:error element has been received.

		Dispatches a L{STREAM_ERROR_EVENT} event with the error element to
		allow for cleanup actions and drops the connection.

		@param errelem: The received error element.
		@type errelem: L{domish.Element}
		"""
		self.dispatch(failure.Failure(error.exceptionFromStreamError(errelem)),
					  STREAM_ERROR_EVENT)
		self.transport.loseConnection()
		
	def onFeatures(self, features,body=None):
		"""
		Called when a stream:features element has been received.

		Stores the received features in the C{features} attribute, checks the
		need for initiating TLS and notifies the authenticator of the start of
		the stream.

		@param features: The received features element.
		@type features: L{domish.Element}
		"""
		self.features = {}
		print "onFeatures"
		print unicode(features.toXml())
		if body:
			print unicode(body.toXml())
		for feature in features.elements():
			self.features[(feature.uri, feature.name)] = feature
		if body:
			self.authenticator.streamStarted(body)
		self.authenticator.initializeStream()
		#else:
		#	self.authenticator.streamStarted(features)

	def sendHeader(self):
		"""
		Send the stream header (the opening body).
		Just a place holder
		"""
		if self.initialized:
			self.restart()
		
	def sendFooter(self):
		"""
		Send stream footer.
		"""

	def sendStreamError(self, streamError):
		"""
		Send stream level error.

		If we are the receiving entity, and haven't sent the header yet,
		we sent one first.

		If the given C{failure} is a L{error.StreamError}, it is rendered
		to its XML representation, otherwise a generic C{internal-error}
		stream error is generated.

		After sending the stream error, the stream is closed and the transport
		connection dropped.
		"""
		print 'bug',streamError
		if not self._headerSent and not self.initiating:
			self.sendHeader()

		if self._headerSent:
			self.send(streamError.getElement())
			self.sendFooter()

		self.transport.loseConnection()


	#def send(self, obj):
	#    XXX I think we should keep this if we want to use this stream for
	#    something else than jabber:client
	#    """
	#    Send data over the stream.
	#
	#    This overrides L{xmlstream.Xmlstream.send} to use the default namespace
	#    of the stream header when serializing L{domish.IElement}s. It is
	#    assumed that if you pass an object that provides L{domish.IElement},
	#    it represents a direct child of the stream's root element.
	#    """
	#    boshstream.BOSHStream.send(self, obj)
		

	def connectionMade(self, _):
		"""
		Called when a connection is made.

		Notifies the authenticator when a connection has been made.
		"""
		#httpstream.HTTPStream.connectionMade(self)
		self.authenticator.connectionMade()

		self.addObserver("/features", self.onFeatures)

	def got_first_element(self, body):
		"""
		Called when the first ansawer from the BOSH server has been received.

		XXX check this part of the docs
		Extracts the header's C{id} and C{version} attributes from the root
		element. The C{id} attribute is stored in our C{sid} attribute and the
		C{version} attribute is parsed and the minimum of the version we sent
		and the parsed C{version} attribute is stored as a tuple (major, minor)
		in this class' C{version} attribute. If no C{version} attribute was
		present, we assume version 0.0.

		If appropriate (we are the initiating stream and the minimum of our and
		the other party's version is at least 1.0), a one-time observer is
		registered for getting the stream features. The registered function is
		C{onFeatures}.

		Ultimately, the authenticator's C{streamStarted} method will be called.

		@param rootelem: The root element.
		@type rootelem: L{domish.Element}
		"""
		
		httpstream.HTTPStream.got_first_element(self, body)

		# Extract stream identifier
		if self.initiating:
			#self.sid = rootelem.getAttribute("id")
			#self.otherHost = rootelem.getAttribute("from")
			pass
		else:
			# XXX not working yet, only client
			self.namespace = rootelem.defaultUri
			self.thisHost = rootelem.getAttribute("to")

		# Extract stream version and take minimum with the version sent
		#if rootelem.hasAttribute("version"):
		#    version = rootelem["version"].split(".")
		#    try:
		#        version = (int(version[0]), int(version[1]))
		#    except IndexError, ValueError:
		#        version = (0, 0)
		#else:
		#    version = (0, 0)
		# XXX I don't think this is the best way for getting the
		# stream version
		if len(body.children) > 0:
			version = (1, 0)
		else:
			version = (0, 0)

		self.version = min(self.version, version)

		# Setup observer for stream errors
		self.addOnetimeObserver("/error[@xmlns='%s']" % NS_STREAMS,
								self.onStreamError)

		# if this is a 1.0 stream the body should contain the features
		if self.initiating and self.version >= (1, 0):
			reactor.callLater(0, self.onFeatures, body.children[0],body)
		else:
			self.authenticator.streamStarted(body)
    

class XmlStreamFactory(boshstream.BOSHStreamFactory):
    """
    XXX rewrite 
    Note that this differs from L{xmlstream.XmlStreamFactory} in that
    it generates Jabber specific L{XmlStream} instances that have
    authenticators.
    """

    protocol = XmlStream

    def __init__(self, authenticator):
        boshstream.BOSHStreamFactory.__init__(self, authenticator)
        self.authenticator = authenticator

