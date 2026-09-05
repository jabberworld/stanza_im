class preferences:
	def __init__(self,preferencesWindow):
		self.config={}
		self.config['sendByCtrl']={'type':'boolean','label':preferencesWindow.tr("Sends messages with ctrl+enter."),'value':'False', 'groupbox':preferencesWindow.tr('General')}
		self.config["useXHTML"]={'type':'boolean','label':preferencesWindow.tr("Use text formatting."),'value':'True', 'groupbox':preferencesWindow.tr('General')}
		self.config['showChatStatusChanges']={'type':'boolean','label':preferencesWindow.tr("Show status message."),'value':'True','groupbox':preferencesWindow.tr('Normal chat')}
		self.config["showMoodChanges"]={'type':'boolean','label':preferencesWindow.tr("Show messages about users mood."),'value':'True','groupbox':preferencesWindow.tr('Normal chat')}
		self.config["showTuneChanges"]={'type':'boolean','label':preferencesWindow.tr("Show messages about user tune."),'value':'True','groupbox':preferencesWindow.tr('Normal chat')}
		self.config['showReceipts']={'type':'boolean','label':preferencesWindow.tr("Show message receipts notifications."),'value':'True','groupbox':preferencesWindow.tr('Normal chat')}
		self.config['useMUCNames']={'type':'boolean','label':preferencesWindow.tr("Use names for tabs."),'value':'True','groupbox':preferencesWindow.tr('Groupchat')}
		self.config["askBeforeQuitMUC"]={'type':'boolean','label':preferencesWindow.tr("Ask before quit room."),'value':'True','groupbox':preferencesWindow.tr('Groupchat')}
		self.config["autochangenickMUC"]={'type':'boolean','label':preferencesWindow.tr("Auto change nick if there's a conflict when joining the room"),'value':'True','groupbox':preferencesWindow.tr('Groupchat'),"category":"advanced"}
		self.config["showMucStatus"]={'type':'boolean','label':preferencesWindow.tr("Show status changes in groupchat"),'value':'True','groupbox':preferencesWindow.tr('Groupchat'),"category":"advanced"}
		self.config["showMucJoinPart"]={'type':'boolean','label':preferencesWindow.tr("Show messages about join or part from room"),'value':'True','groupbox':preferencesWindow.tr('Groupchat'),"category":"advanced"}
		
