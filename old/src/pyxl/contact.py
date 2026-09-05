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
class Contact:
	def __init__(self, client, jid, name, subscription, items=[], groups = [], status = (),  tag = None,  order = 1, ask = None):
		self.jid = jid
		self.name = name
		self.subscription = subscription
		self.groups = groups
		self.status = status
		self.rosterItems = items # user can be in many groups => more items
		self.resourcesItems={}
		self.metaItems=[]
		self.resources={} #resource:(show,status,priority)
		self.client = client
		self.tag = tag
		self.order = order
		self.vcard = {}
		self.avatar_file = ''
		self.avatar_hash = ''
		self.ask = ask
		self.pep = {}

	def setPEP(self, typ, payload):
		self.pep[typ] = payload
	
	def getPEP(self, typ):
		return self.pep.get(typ, None)

	def setStatus(self, resource, show, status):
		first = False
		if self.resources.has_key(resource):
			self.resources[resource].show = show
			self.resources[resource].status =  status
		else:
			self.resources[resource] = Resource(self, resource, show = show, status = status, priority = 0)
			first = True
		if self.resources.has_key(resource) and show == 'offline':
			del self.resources[resource]
			return
		if resource == self.getHighestResource():
			self.status = (show, status)
		return first
##	def getResource(self, resource):
##		resource = False
##		for res in self.resources:
##			if res.name == resource:
##				resource = res
##		return resource
	
	def setPriority(self, resource, priority):
		if self.resources.has_key(resource):
			self.resources[resource].priority =priority
		else:
			self.resources[resource] = Resource(self, resource, priority = priority)
			
	def setFeatures(self, resource, features, identity = 'client/pc'):
		if self.resources.has_key(resource):
			self.resources[resource].features = features
			self.resources[resource].identity = identity
		else:
			self.resources[resource] = Resource(self, resource)
			self.resources[resource].features = features
			self.resources[resource].identity = identity
			
	def getHighestResource(self):
		prio = 0
		try:
			highest = self.resources.keys()[0]
		except:
			highest = None
		for res,val in self.resources.iteritems():
				if val.priority>prio:
					highest = res
					prio = val.priority
		return highest

	def getUserItems(self):
		# get user QTreeWidget item from every group
		return self.rosterItems
		
	def setAvatar(self, file, hash):
		self.avatar_file = file
		self.avatar_hash = hash
		
class Resource:
	def __init__(self, contact, name, priority=0, show='offline', status=''):
		self.name = name
		self.priority = priority
		self.show = show
		self.status = status
		self.features = []
		self.identity = 'client/pc'
		self.contact = contact
	
	def hasFeature(self, feature):
		if feature in self.features:
			return True
		else:
			return False
	def getFeatures(self):
		return self.features
