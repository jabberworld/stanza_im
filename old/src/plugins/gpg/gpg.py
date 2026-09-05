import sys,os,time,tempfile,string
sys.path.append('.')
from include import plugins
from PyQt4 import QtCore, QtGui
from urllib import quote, unquote
from twisted.python import log
from twisted.words.protocols.jabber import jid
from pyme import core, constants, errors

class config:
	def __init__(self,main):
		self.main=main
		self.config={}
		self.config['gpg_enabled_list']={'type':'jid-list','label':self.main.tr("GPG is enabled for:"),'value':''}

class Plugin(plugins.PluginBase):
	def __init__(self, main, homedir, plugindir):
		plugins.PluginBase.__init__(self, main, homedir, plugindir)
		self.fname = 'gpg'
		self.installTranslator()
		self.description = self.tr(
			'Plugin that allows you to use PGP/GPG (or similar engine supported by GPGME).\n\n' +
			'This plugin requires your gpg system to be setup already.\n' +
			'If you enable this plugin, you can receive gpg encrypted messages ' +
			'set gpg key ids for jids and select to which people you send encrypted messages.'
		)
		self.author = "Marek Hulan"
		self.name = self.tr('GPG plugin')
		self.version = '0.100'
		self.category = ['misc']
		self.url = 'http://dev.jabbim.cz/jabbim'
		self.configDialog=config(self)
		if main:
			self.registerHandler('on_message', self.on_message, priority = 4)

			self.loadConfig()
			self.key_dialog=self.loadDialog("%s/gpg_dialog_ui.py" % self.pluginDir,self.main)
		else:
			self.loadConfig(homedir)

	# potreba kvuli op_decrypt_cb, o frazi se stara agent (s pinentry programem)
	def passCallback(hint='', desc='', prev_bad='', hook=''):
		return True

	def on_message(self,msg):
		if not msg.getGpgEncryptedBody() is None:
			cipher = core.Data("-----BEGIN PGP MESSAGE-----\n\n" +
												 msg.getGpgEncryptedBody().encode('utf-8') +
											   "\n-----END PGP MESSAGE-----")
			cipher.seek(0,0)
			c = core.Context()
			c.set_armor(1)
			c.set_passphrase_cb(self.passCallback)

			try:
				plain = core.Data()
				c.op_decrypt(cipher, plain)
				plain.seek(0,0)
			except errors.GPGMEError, ex:
				print ex.getstring()
			
			message = unicode(plain.read(),'utf-8')
			print message

			if not message:
				msg.setBody(self.tr('Can not decrypt, agent problem? Here is original:') + "\n" +
					"\n-----BEGIN PGP MESSAGE-----\n\n" +
					msg.getGpgEncryptedBody() + "\n" + '-----END PGP MESSAGE-----')
			else:
				msg.setBody(message)
		return True

	def on_messageSend(self,msg):
		for jid_with_resource in self.config['gpg_enabled_list']:
			if (jid_with_resource == msg.to.userhost() or jid_with_resource == msg.to.full()) and self.config.has_key(msg.to.userhost()) and len(self.config[msg.to.userhost()]['long_key_id']) == 16:
				
				plain = core.Data(msg.getBody().encode('utf-8'))
				cipher = core.Data()
				c = core.Context()
				c.set_armor(1)
				c.op_keylist_start(self.config[msg.to.userhost()]['long_key_id'].encode(),0)
				r = c.op_keylist_next()
				if r == None:
					# TODO: upozornit uzivatele, ze klic nebyl dle id nalezen
					return False
				else:
					try:
						c.op_encrypt([r], 1, plain, cipher)
						cipher.seek(0,0)
						message = cipher.read()
					except errors.GPGMEError, ex:
						print ex.getstring()
						# TODO: upozornit uzivatele, ze sifrovani se nezdarilo
						return False

					# podle XEP 0027 je potreba odrezat hlavicky, lepsi zpusob?
					lines = string.split(message, '\n')
					message = string.join(lines[2:-2], '\n')

					msg.setGpgEncryptedBody(message)
		return msg

	def keyAccepted(self):
		key_id=unicode(self.key_dialog.ui.key_id.text())
		if not (self.config.has_key(self.jid) and self.config[self.jid].has_key('long_key_id')):
			self.config[self.jid]={'long_key_id':key_id}
		else:
			self.config[self.jid]['long_key_id']=key_id
		self.writeConfig()

	def showSlot(self,jid=None):
		self.key_dialog.show()
		self.jid=jid
		self.key_dialog.setWindowTitle(unicode(self.jid))
		if self.config.has_key(self.jid) and self.config[self.jid].has_key('long_key_id'):
			self.key_dialog.ui.key_id.setText(self.config[self.jid]['long_key_id'])
		else:
			self.key_dialog.ui.key_id.setText('')
		QtCore.QObject.connect(self.key_dialog,QtCore.SIGNAL("accepted ( )"),self.keyAccepted)

	def buildContactMenu(self,menu,contact):
		self.action=menu.addAction(self.tr("GPG key ID"))
		self.action.setData(QtCore.QVariant(unicode(contact.jid)))
		self.action.setObjectName("key_dialog")
		self.action.setIcon(QtGui.QIcon("%s/kgpg.png" % self.pluginDir))
		QtCore.QObject.connect(self.action,QtCore.SIGNAL("triggered ( bool )"),self.contactMenuToggled)
        
	def contactMenuToggled(self,b):
		"""
		User choose our QAction from contactMenu (menu above contact)
		"""
		jid=unicode(self.action.data().toString())
		log.err(jid)
		self.showSlot(jid)
		self.action.deleteLater()
