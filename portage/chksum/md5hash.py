# Copyright: 2004-2005 Gentoo Foundation
# License: GPL2
# $Id: md5hash.py 1911 2005-08-25 03:44:21Z ferringb $


# We _try_ to load this module. If it fails we do the slow fallback.
try:
	import fchksum
	
	def md5hash(filename):
		return fchksum.fmd5t(filename)[0]

except ImportError:
	import md5
	def md5hash(filename):
		f = open(filename, 'rb')
		blocksize=32768
		data = f.read(blocksize)
		size = 0L
		sum = md5.new()
		while data:
			sum.update(data)
			size = size + len(data)
			data = f.read(blocksize)
		f.close()

		return sum.hexdigest()

chksum_types = (("md5", md5hash),)
