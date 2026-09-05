from twisted.words.protocols.jabber.client import *
from twisted.internet import reactor
import xmlstream

_default_bosh_attrs = {
	"wait": "40",
	"hold": "2",
	#    "inactivity": "60",
	"content": "text/xml; charset=utf-8",
	"xml:lang": "en",
	"xmpp:version": "1.0",
	"xmlns:xmpp": "urn:xmpp:xbosh",
	"secure":"false",
	"ver":"1.6"
}

class BOSHFactory(xmlstream.XmlStreamFactory):
    """
    Note that this differs from L{xmlstream.XmlStreamFactory} in that
    it generates Jabber specific L{XmlStream} instances that have
    authenticators.
    """

    def stopTrying(self):
        print 'tak ja to balim'
    

def BOSHClientFactory(jid, password, bosh_url, bosh_attrs = {},  proxy = None):
    """
    @param jid: authenticatiing jis
    @param password: user's password
    """
    a = XMPPAuthenticator(jid, password)
    f = BOSHFactory(a)
    f.bosh_url = bosh_url
    f.bosh_attrs = _default_bosh_attrs.copy()
    f.bosh_attrs["to"] = jid.host.encode("utf-8")
    f.bosh_attrs.update(bosh_attrs)
    f.proxy = proxy
    return f
    
