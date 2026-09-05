#-*-coding:UTF-8-*-

from twisted.words.protocols.jabber.xmlstream import IQ
from twisted.python import log
# iq
# | querry
# | attr: xmlns == "jabber:iq:privacy"
# |
# `--| list
#    | attr: name == string
#    |
#    `--| item
#       | attr: action == string("allow"|"deny")
#       | attr: order == unsigned unique int
#       | [attr: type == string("jid"|"group"|"subscription")]
#       | [attr: value == string]
#       |
#       `--| [message]
#       `--| [iq]
#       `--| [presence-in]
#       `--| [presence-out]

class PrivacyListItem:
	"""Simple privacy rule class"""
	def __init__(self, action, order, typ = None, value = None, stanzas = []):
		"""@type action: str
@param action: "allow" or "deny"
@type order: unsigned int
@param order: should be genereated automaticaly, bacause it must be unique within list
@type typ: str
@param typ: "jid", "group" or "subscription"
@type value: unicode
@param value: According to typ param
@type stanzas: list
@param stanzas: "message", "iq", "presence-in" and/or "presence-out" are allowed values in the list"""
		self.action	= action
		self.order	= int(order)
		if self.order < 0:
			raise ValueError("Order must be unsigned int")
		self.typ	= typ
		self.value	= value
		self.stanzas	= stanzas # stanzas = [] denies|allows all communication

class PrivacyList:
	"""Class that manages one privacy list"""
	def __init__(self, name, items, main, rev=True):
		"""@type name: unicode
@param name: Name of the list
@type items: list
@param items: list of PrivacyListItem instances
@type main: MainWindow
@param main: main instance"""
		self.name	= name
		self.items	= items
		self.main	= main
		if rev:
			self._reviseOrders()

		self.invisible	= None
		if len(items)>0:
			lastitem = self.getItem(self._getOrders()[-1])
			if lastitem.action == "deny" and (lastitem.stanzas == [] or "presence-out" in lastitem.stanzas) and lastitem.typ == None:
				self.invisible = lastitem

			for item in self.items:
				if item.value and item.typ == "jid":
					for useritem in self.main.ui.roster.getUserItems(item.value):
						useritem.privacy["block"] = self.isBlockedJID(item.value)
						useritem.privacy["allow"] = self.isAllowedJID(item.value)
						useritem.privacy["hide"] = self.isHiddenJID(item.value)
				

	def _getOrders(self):
		"""@rtype: list
@return: sorted list of used orders in privacy list"""
		orders = [int(item.order) for item in self.items]
		orders.sort()
		return orders

	def _reviseOrders(self): # ejabberd je pyca, jednodussi prace s itemama
		"""Reordes items in privacy list to have unique orders, because some servers don't handle it correctly :("""
		orders = self._getOrders()
		while orders:
			i = orders.pop()
			if i in orders:
				self._advance(self.getItem(i), False)
				self._reviseOrders()
		self.update()

	def update(self, sm = False):
		"""Sends the list to server
		
@type sm: bool
@param sm: used to handle invisiblity"""
		iq	= IQ(self.main.client.xmlstream, "set")
		query	= iq.addElement("query", "jabber:iq:privacy")
		list_	= query.addElement("list")
		list_.attributes = {"name": self.name}
		for rule in self.items:
			item = list_.addElement("item")
			item.attributes = {"action":rule.action, "order":unicode(rule.order)}
			if rule.typ and rule.value:
				item.attributes["type"] = rule.typ
				item.attributes["value"] = rule.value
			for stanza in rule.stanzas:
				item.addElement(stanza)

		#self.main.client.on_xml(iq.toXml())
		d=iq.send()
		if sm:
			d.addCallback(self._showme)
		self.main.client.disp(iq["id"])
		log.msg("privacy list %s updated" % self.name)

	def addItem(self, item, sm = False):
		"""Adds new rule to list
@type item: PrivacyListItem
@param item: item you want to add
@type sm: bool
@param sm: used to handle invisibility, see _showme"""
		self.items.append(item)
		self.update(sm)
		log.msg("added privacy list item to list %s with order %s" % (self.name, item.order))

	def delItem(self, item, sm = False):
		"""Removes item from list
@type item: PrivacyListItem
@param item: item you want to remove
@type sm: bool
@param sm: used to handle invisibility, see _showme"""
		if item in self.items:
			log.msg("removing privacy list item from list %s with order %s" % (self.name, item.order))
			self.items.remove(item)
			self.update(sm)

	def mkItem(self, action, typ = None, value = None, stanzas = [],
			to_zero = True, # True - lowest possible (more important), False - current highest + 1 (less important)
			sm = False):
		"""Creates a new PrivacyListItem, automaticaly assignig order

action, typ, value and stanzas attributes are the same as for PrivacyListItem.__init__

@type to_zero: bool
@param to_zero: Assign zero order and reorder other items - lower order = higher importance (True), or uses the highest order otherwise
@type sm: bool
@param sm: used to handle invisibility, see _showme
"""
		orders = self._getOrders()
		if to_zero:
			zitem = self.getItem(0)
			if zitem:
				self._advance(zitem, False)
			order = 0
		else:
			order = orders[-1] + 1
		item = PrivacyListItem(action, order, typ, value, stanzas)
		self.addItem(item, sm)
		return item

	def getItem(self, order):
		"""@rtype: PrivacyListItem
@return: returns the item with requested order

@type order: int
@param order: ."""
		for item in self.items:
			if item.order == order:
				return item

	def _advance(self, item, update=True):
		"""Used in _reviseOrders and changeOrder

Selected item's order and evry directly following items' (+1) orders are incremented by one

@type item: PrivacyListItem
@param item: item to advance
@type update: bool
@param update: use the update method or not?"""
		orders = self._getOrders()
		to_advance = None
		if item.order + 1 in orders:
			to_advance = self.getItem(item.order + 1)
		item.order += 1
		if to_advance:
			self._advance(to_advance)
		if update:
			self.update()
			
	def changeOrder(self, old, new):
		"""Changes order of an item.

@type old: int
@param old: old order of item
@type new: int
@param new: new order of item"""
		orders = self._getOrders()
		item = getItem(old)
		if new in orders:
			self._advance(self.getItem(new))
		item.order = new
	
	######## ^   BASE   ^ #######
	######## v ADVANCED v #######
	
	def isBlockedJID(self, jid):
		r = False
		order = None
		for item in self.items:
			item.stanzas.sort()
			if item.typ == "jid" and item.value == jid and item.action == "deny" and  (item.stanzas == [] or item.stanzas == ["iq","message","presence-out"]):
				r = item
				order = item.order

			if	(item.typ == "jid" and item.value == jid) and (item.action == "allow" and item.order < order) and (item.stanzas == [] or item.stanzas == ["iq","message","presence-out"]):
				r = False
		return r
	def blockJID(self, jid): # Block all communication
		self.mkItem("deny", "jid", jid)#, ["message", "iq", "presence-out"])
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["block"] = True
	def unBlockJID(self, jid):
		item = self.isBlockedJID(jid)
		if item:
			self.delItem(item)
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["block"] = False
	

	def isAllowedJID(self, jid):
		r = False
		order = None
		for item in self.items:
			if item.typ == "jid" and item.value == jid and item.action == "allow" and (item.stanzas == [] or "presence-out" in item.stanzas):
				r = item
				order = item.order
			if	(item.typ == "jid" and item.value == jid) and (item.action == "deny" and item.order < order) and (item.stanzas == [] or "presence-out" in item.stanzas):
				r = False
		return r
	def allowJID(self, jid): 
		self.mkItem("allow", "jid", jid, ["presence-out"])
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["allow"] = True
	def disAllowJID(self, jid):
		item = self.isAllowedJID(jid)
		if item:
			self.delItem(item)
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["allow"] = False

	def isHiddenJID(self, jid):
		r = False
		order = None
		for item in self.items:
			if item.typ == "jid" and item.value == jid and item.action == "deny" and item.stanzas == ["presence-out"]:
				r = item
				order = item.order
			if	(item.typ == "jid" and item.value == jid) and (item.action == "allow" and item.order < order) and (item.stanzas == [] or "presence-out" in item.stanzas):
				r = False
		return r
	def hideJID(self, jid): 
		self.mkItem("deny", "jid", jid, ["presence-out"])
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["hide"] = True
	def unHideJID(self, jid):
		item = self.isHiddenJID(jid)
		if item:
			self.delItem(item)
		for x in self.main.ui.roster.getUserItems(jid.split("/", 1)[0]):
			x.privacy["hide"] = False
	
	def _showme(self, *a):
		sc = self.main.client.roster['users'][self.main.client.jid.userhost()].resources[self.main.client.jid.resource]
		self.main.client.sendPresence(typ="available", show=sc.show, status=sc.status)

	def setInvisible(self, globaly = False):
		"""Become invisible wihin the list

@type globaly: bool
@param globaly: Become invisible globaly, not selectively"""
		if not self.invisible:
			self.main.client.sendPresence(typ="unavailable")
			self.invisible = self.mkItem("deny", stanzas = ["presence-out"], to_zero = globaly, sm = True)
			log.msg("we are now invisible")

	def unsetInvisible(self, available = True):
		"Become visible"
		if self.invisible:
			self.delItem(self.invisible, available)
			self.invisible = None
			log.msg("we are now visible")

	
class Privacy:
	"""Class for multiple privacy lists management

Use self.lists["name"] for access to single privacy lists instances"""
	def __init__(self, main):
		self.main	= main
		self.lists	= {}
		self.active	= None
		self.default	= None
	
	def setActive(self, name):
		"""Set the privacy list as active

@type name: unicode
@param name: chosen list's name"""
		if name not in self.lists.keys() and name != None:
			self.lists[name] = None
		iq = IQ(self.main.client.xmlstream, "set")
		query = iq.addElement("query", "jabber:iq:privacy")
		active = query.addElement("active")
		if name != None:
			active.attributes = {"name":name}
		iq.send()
	#	self.main.client.on_xml(iq.toXml())
		self.main.client.disp(iq["id"])
		if name != None:
			self.active = self.lists[name]	
		else:
			self.active = None

	def setDefault(self, name):
		"""Set the privacy list as default.

@type name: unicode
@param name: chosen list's name"""
		if name not in self.lists.keys() and name != None:
			self.lists[name] = None
		iq = IQ(self.main.client.xmlstream, "set")
		query = iq.addElement("query", "jabber:iq:privacy")
		default = query.addElement("default")
		if name != None:
			default.attributes = {"name":name}
		iq.send()
		#self.main.client.on_xml(iq.toXml())
		self.main.client.disp(iq["id"])
		if name != None:
			self.default = self.lists[name]
		else:
			self.default = None
