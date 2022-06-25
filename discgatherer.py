# This is the DiscGatherer software. Its purpose is to help you manage your collection of CD DVD and Bluray dics. Stay tuned.

#-------------------------------------------------------------------------------
# Imports

# For a start, there are a few dependencies. Use `pip install xxx`.
import bson
# Following are standard library imports. They should not fail, ever.
import os, argparse, subprocess, pprint, stat, datetime

#-------------------------------------------------------------------------------
# The disc collection is loaded in its entirety.

# By default, the collection is stored in `default.db` but you could change that if you want. If the database file does not exist, the program just assumes that the database is empty.
collection = {}
databasename = "./default.db"
autosave = False

if os.path.exists(databasename):
	with open(databasename, "r+b") as f:
		serializeddata = f.read()
	collection = bson.loads(serializeddata)

#-------------------------------------------------------------------------------
# CLI syntax is extensive.

description = "This is the DiscGatherer software. Its purpose is to help you manage your collection of CD DVD and Bluray dics. The default way of using this program is through the CLI command-line. This covers both listing your discs, adding them, searching for specific files, etc. Most operations can only be done using CLI syntax. Learn it."
parser = argparse.ArgumentParser(description=description, add_help=False)
parser.add_argument("-h", "--help", action="help", help="Display documentation.")
parser.add_argument("-a", "--add", action="store_true", help="Add /dev/sr0 disc to your collection. Can be verbose, in which case you should use less command.")
parser.add_argument("-L", "--label", action="store", help="Use provided label instead of detecting it from the actual disc. Note that the provided label must be in quotes.")
parser.add_argument("-b", "--brief", action="store_true", help="Briefly list all discs. Can be verbose.")
parser.add_argument("-l", "--list", action="store_true", help="List all discs, folders, and files in your collection. Ideal for grep. Can be verbose. Whether you use verbose mode or not, you should use less or grep command.")
parser.add_argument("-r", "--remove", action="store", help="Remove a disc under given ID. The IDs are displayed in both brief and listing modes.")
parser.add_argument("-s", "--search", action="store", help="Search for given case insensitive words in your collection. More than one word needs to be provided in quotes.")
parser.add_argument("-S", "--strict", action="store_true", help="Modify how search mode works. Strict search should yield less false positives than a normal search mode.")
parser.add_argument("-v", "--verbose", action="store_true", help="Print additional information when adding or listing discs.")
args = parser.parse_args()

#-------------------------------------------------------------------------------
# Common functions that are used by more than one mode.

# This function converts file sizes into a human readable format like "123.4 KB"
def formatsize(size):
	magnitude = 0
	suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
	for s in suffixes:
		if size > 1000:
			size /= 1000
			magnitude += 1
		else:
			break
	if magnitude == 0:
		return f"{size} bytes"
	else:
		return f"{size:.1f} {suffixes[magnitude]}"

# This function computes the indentation, four spaces per level.
def indent(level):
	return " " * 4 * level

# This function prints out folders, recursively.
def walk_print(entries, indentlevel):
	# Displays sub-files before sub-folders.
	for (entryname,entry) in entries.items():
		if entry["type"] == "file":
			if args.verbose:
				size = formatsize(entry["size"])
				mtime = datetime.datetime.utcfromtimestamp(entry["mtime"]).isoformat(sep=" ")
				print(f"{indent(indentlevel)}a file {entryname} [size: {size}] [modified: {mtime}]")
			else:
				print(f"{indent(indentlevel)}a file {entryname}")
	# Displays sub-files before sub-folders.
	for (entryname,entry) in entries.items():
		if entry["type"] == "folder":
			if args.verbose:
				size = formatsize(entry["size"])
				print(f"{indent(indentlevel)}a folder {entryname} [size: {size}]:")
			else:
				print(f"{indent(indentlevel)}a folder {entryname}:")
			walk_print(entry["entries"], indentlevel+1)

# This function decides whether a file or folder name matches a search criteria.
def contains(subwords, searchin, strict):
	subwords = subwords.lower()
	searchin = searchin.lower()
	if strict:
		separators = "`~!@#$%^&*()-_=+[{]}\\|;:\'\",<.>/?"
		for sep in separators:
			searchin = searchin.replace(sep, " ")
		searchinparts = searchin.split()
		return all(subword in searchinparts for subword in subwords.split())
	else:
		return all(subword in searchin for subword in subwords.split())

def walk_search(entries):
	# The `entries` formal parameter is a dictionary. Its keys are file/folder names, while the dict values are either dict(type="file", ...) or dict(type="folder", ...).
	output = {}
	for (entryname,entry) in entries.items():
		# A file is included in search results on a simple basis: either the file names contains all search words or not. This is rather straightforward.
		if entry["type"] == "file":
			if contains(args.search, entryname, args.strict):
				output[entryname] = entry
		# A folder is included in search results if either (1) its name contains all search words, or (2) there exists a file or folder somewhere down its subentries whos name is a match.
		if entry["type"] == "folder":
			if contains(args.search, entryname, args.strict):
				output[entryname] = entry
			else:
				walked = walk_search(entry["entries"])
				if walked:
					# Note that not all info is preserved (like ctime atime are missing) but that is beside the point. Those info are not displayed anyway.
					output[entryname] = dict(type="folder", size=entry["size"], mtime=entry["mtime"], entries=walked)
	return output

#-------------------------------------------------------------------------------
# Adding a disc mode.

if args.add:
	# Before the disc is scanned, there must be at least one drive present.
	if not os.path.exists("/dev/sr0"):
		print("There seems to be no drive present, aborting.")
		print()
		exit(1)

	# First thing: lets interrogate `udevadm info` about the `/dev/sr0` disc. This command interrogates both the optical drive as well as the optical disc inside of it. It returns a lot of data about both, that needs to be parsed and sifted through.
	sp = subprocess.run(["udevadm","info","-q","property","-x","-n","sr0"], stdout=subprocess.PIPE)
	output = sp.stdout.decode()
	outputlines = output.splitlines()
	def parse(line):
		parts = line.partition("=")
		return (parts[0], parts[2].strip("'"))
	def select(kv):
		(k,v) = kv
		return k in ["DEVNAME", "DEVTYPE", "ID_CDROM_MEDIA_BD", "ID_CDROM_MEDIA_STATE", "ID_CDROM_MEDIA_SESSION_COUNT", "ID_FS_LABEL", "ID_FS_LABEL_ENC", "ID_FS_TYPE", "ID_FS_VERSION", "ID_FS_USAGE", "ID_FS_UUID", "ID_FS_UUID_ENC", "ID_FS_VOLUME_SET_ID", "ID_FS_VOLUME_ID", "ID_FS_LOGICAL_VOLUME_ID", "ID_FS_APPLICATION_ID", "ID_FS_BOOT_SYSTEM_ID"]
	# TODO: Remove this later on.
	items = {k:v for (k,v) in map(parse, outputlines)}
	if args.verbose:
		print("Interrogating the disc drive yielded following (ALL ENTRIES): ")
		pprint.pprint(items)
		print()
	# END TODO
	items = {k:v for (k,v) in filter(select, map(parse, outputlines))}
	if args.verbose:
		print("Interrogating the disc drive yielded following (among others): ")
		pprint.pprint(items)
		print()
	if len(items) <= 2:
		print("There seems to be no disc present, aborting.")
		print()
		exit(1)
	disclabel = items.get("ID_FS_LOGICAL_VOLUME_ID", None) or items.get("ID_FS_VOLUME_SET_ID", None) or items.get("ID_FS_LABEL_ENC", None) or "[unknown label]"
	disclabel = disclabel.encode().decode("unicode-escape")
	if args.label is not None:
		disclabel = args.label
	if args.verbose:
		print("The label used for the disc: ")
		print(repr(disclabel))
		print()

	# Second thing: walk over the corresponding mounted filesystem. The entire directory tree rooted at the disc filesystem is cataloged, every file and folder stat-ed and recorded in the database. 
	fsname = items["ID_FS_LABEL_ENC"]
	fsname = fsname.encode().decode("unicode-escape")
	fspath = f"/media/{os.getlogin()}/{fsname}/"
	if args.verbose:
		print("Path up to the mountpoint should be: ")
		print(repr(fspath))
		print()

	def walk_adding(path):
		entries = {}
		for entryname in os.listdir(path):
			pathname = os.path.join(path, entryname)
			entrystat = os.lstat(pathname)
			if stat.S_ISREG(entrystat.st_mode):
				entries[entryname] = dict(type="file", size=entrystat.st_size, atime=entrystat.st_atime, mtime=entrystat.st_mtime, ctime=entrystat.st_ctime)
			if stat.S_ISDIR(entrystat.st_mode):
				branch = walk_adding(pathname)
				size = sum(f["size"] for f in branch.values())
				entries[entryname] = dict(type="folder", size=size, entries=branch, atime=entrystat.st_atime, mtime=entrystat.st_mtime, ctime=entrystat.st_ctime)
			# TODO: You should index symlinks as well.
		return entries

	tree = walk_adding(fspath)
	size = sum(f["size"] for f in tree.values())
	disc = dict(type="disc", label=disclabel, items=items, content=tree, size=size)
	if args.verbose:
		print("The disc content was found as follows: ")
		walk_print(disc["content"], 1)
		print()

	nextid = 1 if len(collection)==0 else max(map(int, collection.keys()))+1
	collection[nextid] = disc
	autosave = True
	print("The disc was successfully scanned and added under ID/label: ")
	print(f"{nextid} -> {disclabel}")
	print()

#-------------------------------------------------------------------------------
# Brief listing mode.

if args.brief:
	# Displays all discs briefly (only IDs and labels and optionally sizes).
	for (entryid,entry) in collection.items():
		if args.verbose:
			size = formatsize(entry["size"])
			print(f"[ID {entryid}] {entry['type']} {entry['label']} [size: {size}]:")
		else:
			print(f"[ID {entryid}] {entry['type']} {entry['label']}")
	print()

#-------------------------------------------------------------------------------
# Listing discs mode.

if args.list:
	# Displays all discs, recursively.
	for (entryid,entry) in collection.items():
		if args.verbose:
			size = formatsize(entry["size"])
			print(f"[ID {entryid}] {entry['type']} {entry['label']} [size: {size}]:")
			walk_print(entry["content"], 1)
			print()
		else:
			print(f"[ID {entryid}] {entry['type']} {entry['label']}")
			walk_print(entry["content"], 1)
			print()

# TODO: How about using colorama to display names in bold or color?

#-------------------------------------------------------------------------------
# Searching recursively for substrings/subwords.

if args.search:
	for (entryid,entry) in collection.items():
		filtered = walk_search(entry["content"])
		if filtered:
			size = formatsize(entry["size"])
			print(f"[ID {entryid}] {entry['type']} {entry['label']} [size: {size}]:")
			walk_print(filtered, 1)
			print()

#-------------------------------------------------------------------------------
# Removing an entry.

if args.remove:
	entryid = args.remove
	if entryid not in collection.keys():
		print("There is no such disc ID in your collection.")
		print()
		exit(1)

	disclabel = collection[entryid]["label"]
	del collection[entryid]
	autosave = True
	print(f"Entry under following ID/label was successfully removed.")
	print(f"{entryid} -> {disclabel}")
	print()

#-------------------------------------------------------------------------------
# TODO: Renaming an entry label.

#-------------------------------------------------------------------------------
# Here be dragons?

# TODO: What to do when there is more than one optical drive or disc?
# Possible answer: Maybe just ignore the other drives and use the first?
# TODO: What does happen when there is no disc in the optical drive?
# Already handled. It just aborts.
# TODO: What does happen when there is no optical drive at all?
# Needs testing.
# TODO: What does happen when you try to add Audio CD instead?
# Needs testing.

#-------------------------------------------------------------------------------
# Storing disc collection to disk.

# TODO: It should only be saved using atomic file replacement. Stay tuned.
if autosave:
	serializeddata = bson.dumps(collection)
	with open(databasename, "w+b") as f:
		f.write(serializeddata)
