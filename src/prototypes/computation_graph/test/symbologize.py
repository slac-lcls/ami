#
# symbologize [<wordfilePath>]
#
# converts a log file that contains lines like this
# xppcspad    <AMI_common.WorkerOperation object at 0x7f7b3f231fd0>
# to this
# xppcspad    <AMI_common.WorkerOperation object at Armadillo>
#
# where each hex address is converted to a word from a dictionary.
# The conversion is consistent throughout the log file.
#
# The default wordfile is /usr/share/dict/american-english.
# On Ubuntu this is installed by the package wamerican-large.
#

import sys

if len(sys.argv) > 1:
  wordfile = sys.argv[1]
else:
  wordfile = '/usr/share/dict/american-english'

wordlist = open(wordfile, 'r').readlines()

addressDict = {}
for line in sys.stdin.readlines():
  words = line.strip().split(' ')
  hexAddresses = []
  for word in words:
    if word.startswith('0x'): hexAddresses.append(word)
  for hexAddress in hexAddresses:
    if not hexAddress in addressDict:
      addressDict[hexAddress] = len(addressDict)
    wordIndex = addressDict[hexAddress]
    line = line.strip().replace(hexAddress, wordlist[wordIndex].strip())
  print(line.strip())
  assert(len(wordlist) >= len(addressDict))


