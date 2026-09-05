import help
class preferences:
	def __init__(self,preferencesWindow):
		self.config={}
		self.config['passwd']={'type':'text-private','label':preferencesWindow.tr("Password:"),'value':'','groupbox':preferencesWindow.tr('Connection')}
		self.config['jid']={'type':'text-single','disabled':'','label':preferencesWindow.tr("Jabber ID:"),'value':'','groupbox':preferencesWindow.tr('Connection')}
		self.config['autoJoin']={'type':'boolean','label':preferencesWindow.tr("Automatically join at startup."),'value':'False','groupbox':preferencesWindow.tr('Connection')}
		self.config['autoJoinMUC']={'type':'boolean','label':preferencesWindow.tr("Join groupchats at startup."),'value':'True','groupbox':preferencesWindow.tr('Connection'), "category":"advanced"}
		self.config['keepStatus']={'type':'boolean','label':preferencesWindow.tr("Recall the previous status message."),'value':'True','groupbox':preferencesWindow.tr("Connection"),"category":"advanced"}
		self.config['resource']={'type':'text-single','label':preferencesWindow.tr('Resource :'),'value':'jabbim','groupbox':preferencesWindow.tr('Advanced')}
		#self.config['priority']={'type':'number-spin','label':preferencesWindow.tr("Priority:"),'value':'0','groupbox':preferencesWindow.tr('Advanced')}
		self.config['specifyHost']={'type':'boolean','label':preferencesWindow.tr("Specify host for connection"),'value':'False','groupbox':preferencesWindow.tr('Advanced'), 'enable': ['connectHost', 'connectPort'], 'column':'right', 'tooltip':preferencesWindow.tr("Enable only if your server has broken DNS SRV record or if you REALLY know what are you doing."), "category":"advanced"}
		self.config['connectHost']={'type':'text-single','label':preferencesWindow.tr("Host:"),'value':'','groupbox':preferencesWindow.tr('Advanced'), "category":"advanced"}
		self.config['connectPort']={'type':'text-single','label':preferencesWindow.tr("Port:"),'value':'5222','groupbox':preferencesWindow.tr('Advanced'), "category":"advanced"}
		self.config['proxyHost']={'type':'text-single','label':preferencesWindow.tr("Host:"),'value':'','groupbox':preferencesWindow.tr('Proxy settings'), "category":"advanced"}
		self.config['proxyPort']={'type':'text-single','label':preferencesWindow.tr("Port:"),'value':'','groupbox':preferencesWindow.tr('Proxy settings'), "category":"advanced"}
		#self.config['autoPriority']={'type':'boolean','label':preferencesWindow.tr("Change priority automatically due to status."),'value':'True','groupbox':preferencesWindow.tr('Advanced'),'column':'right'}
		self.config['__sort__'] = ['jid', 'passwd','resource', 'autoJoin', 'autoJoinMUC', 'keepStatus', 'connectHost', 'connectPort', 'specifyHost', 'proxyHost',  'proxyPort' ]

	def getHelp(self,key):
		if help.help.has_key(key):
			return help.help[key]
		else:
			return ""
