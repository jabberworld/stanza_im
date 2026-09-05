import os
import sys
fileList = []
rootdir = "../resources/images/"
for root, subFolders, files in os.walk(rootdir):
	if '.svn' in subFolders:
		subFolders.remove('.svn')
	for file in files:
		if (file.endswith('.png') or file.endswith('.gif') ):
			fileList.append(os.path.join(root,file).replace("../resources/",""))

file = open("../resources/jabbim.qrc", "w")
file.write('<!DOCTYPE RCC><RCC version="1.0"><qresource>')
for f in fileList:
	print f
	file.write("<file>%s</file>\n"%f)
file.write('</qresource></RCC>')
file.close()
