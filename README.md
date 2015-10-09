# thinapp-extract

A tool to extract contents from thinapp .dat files

usage example:

import thinapp
fs = thinapp.ThinAppContainer('thinapp.dat')
print(fs.listdir('/FS/%drive_C%'))
f = fs.open('/FS/%drive_C%/file.txt')
print(f.read(10))


To enable faster decompression compile the c program using gcc
