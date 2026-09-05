#-*-coding:UTF-8-*-

from twisted.words.xish.domish import Element

class Field:
	def __init__(self, var, typ = None, label=None, desc=None, required=False, values=[], options=[]):
		self.var = unicode(var)
		self.typ = typ
		self.label = label
		self.desc = desc
		self.required = required
		self.values = values
		self.options = options

	def buildElement(self):
		el = Element((None,"field"))
		el["var"] = self.var
		if self.typ != None:
			el["type"] = self.typ
		if self.label:
			el["label"] = unicode(self.label)
		if self.desc:
			el.addElement("desc", content=unicode(self.desc))
		if self.required:
			el.addElement("required")
		for val in self.values:
			el.addElement("value", content=unicode(val))
		for option in self.options: # [[label, value]]
			op=el.addElement("option")
			op["label"] = option[0]
			op.addElement("value", content=unicode(option[1]))
		return el
class Item:
	def __init__(self, fields):
		self.fields = fields
	def buildElement(self):
		el = Element((None, "item"))
		for field in self.fields:
			el.addChild(field)
		return el

class Reported:
	def __init__(self, vars={}):
		self.vars = vars # {"var": {"label":description,"type":field-type}}
	def buildElement(self):
		el = Element((None, "reported"))
		for var in self.vars.keys():
			field = el.addElement("field")
			field["var"] = var
			for attr in self.vars[var]:
				field[attr] = self.vars[var][attr]
		return el

class Xform:
	def __init__(self, typ="result", instructions=[], title=None, reported=None, items=[], fields=[]):
		self.typ = typ
		self.instructions = instructions
		self.title = title
		self.reported = reported
		self.items = items
		self.fields = fields

	def buildElement(self):
		el = Element(("jabber:x:data", "x"))
		el["type"] = self.typ
		if self.title:
			el.addElement("title", content = unicode(self.title))
		for instruction in self.instructions:
			el.addElement("instructions", content = unicode(instruction))
		if self.reported:
			el.addChild(self.reported.buildElement())
		for item in self.items:
			el.addChild(item.buildElement())
		for field in self.fields:
			el.addChild(field.buildElement())
		return el

