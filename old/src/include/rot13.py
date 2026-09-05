# rot13 cypher, it is self-inverse, no need to use special decrypting method
def scramble (text=''): 
	rot13ed=''
	for letter in range(len(text)):
		byte = ord(text[letter])
		capital = (byte & 32) # is capital?
		byte = (byte & (~capital))
		if (byte >= ord('A')) and (byte <= ord('Z')):
			byte = ((byte - ord('A') + 13) % 26 + ord('A'))
		byte = (byte | capital)
		rot13ed=rot13ed+(chr(byte))
	return rot13ed