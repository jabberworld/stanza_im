from twisted.words.protocols.jabber import jid
import copy
InvalidFormat = jid.InvalidFormat

def JID(jidstring):
	if isinstance(jidstring, jid.JID):
		jidstring = jidstring.full()
	if jidstring.startswith('@'):
		raise InvalidFormat
		return
	try:
		j =  jid.internJID(jidstring.strip())
	except:
			raise InvalidFormat
			return
	return copy.copy(j)
