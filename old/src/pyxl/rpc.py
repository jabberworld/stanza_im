from xmlrpclib import loads, dumps	
from twisted.internet import threads, defer, reactor
from twisted.words.xish.domish import Element
import traceback

class rpc:
	def __init__(self, client):
		self.client = client
		self.handlers = {}
	
	def registerHandler(self, name, function):
		self.handlers[name] = function
	
	def unregisterHandler(self, name):
		try:
			del self.handlers[name]
		except:
			print 'Handler not found'
	
	def onRPC(self, el):
		print 'received rpc'
		self.client.disp(el['id'])
		query = el.firstChildElement()
		call = loads(query.firstChildElement().toXml())
		if self.handlers.has_key(call[1]):
			try:
				d = self.handlers[call[1]](el['from'],call[0])
			except Exception, ex:
				self.chyba(ex,call[1], el['from'], el['id'])
				print traceback.format_exc()
				return
			if isinstance(d, defer.Deferred):
				d.addCallback(self.rpcResult, call[1], el['from'], el['id']).addErrback(self.chyba, call[1], el['from'], el['id'])
			elif type(d) == tuple:
				self.rpcResult(d, call[1], el['from'], el['id'])
			else:
				self.chyba(tuple(),call[1], el['from'], el['id'])
		pass

	def rpcResult(self, result, func, frm, id):
		iq = Element((None, 'iq'))
		iq['to'] = frm
		iq['type'] = 'result'
		iq['id'] = id
		q = iq.addElement('query', 'jabber:iq:rpc')
		q.addRawXml(unicode(dumps(result, methodresponse = True), 'utf8'))
		print iq.toXml()
		self.client.xmlstream.send(iq)
	
	def chyba(self, result, func, frm, id):
		print 'chyba: ',result
		iq = Element((None, 'iq'))
		iq ['to'] = frm
		iq['type'] = 'error'
		iq['id'] = id
		q = iq.addElement('query', 'jabber:iq:rpc')
#		q.addRawXml(unicode(dumps(result, methodresponse = True), 'utf8'))
		print iq.toXml()
		self.client.xmlstream.send(iq)
