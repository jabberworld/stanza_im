import help

class preferences:
	def __init__(self,preferencesWindow):
		self.config={}
		self.config['allowChatstate']={'type':'boolean','label':preferencesWindow.tr("Send chatstate notifications."),'value':'True'}
		self.config['sendOSInfo']={'type':'boolean','label':preferencesWindow.tr("Send OS info."),'value':'True'}
#		self.config['sendTune']={'type':'boolean','label':preferencesWindow.tr("Send now playing."),'value':'True'}
#		self.config['sendMood']={'type':'boolean','label':preferencesWindow.tr("Send user mood."),'value':'True'}
#		self.config['sendActivity']={'type':'boolean','label':preferencesWindow.tr("Send user activity."),'value':'True'}
		self.config['sendRooms']={'type':'boolean','label':preferencesWindow.tr("Send rooms."),'value':'True'}

