# This is the DiscGatherer software. Its purpose is to help you manage your collection of CD DVD and Bluray dics. If the CLI interface is not to your liking, your collection may be also exposed through FUSE. Stay tuned.

# For a start, there are a few dependencies. Use `pip install xxx`.
import bson

# Following are standard library imports. They should not fail, ever.
import os, argparse

# By default, the collection is stored in `default.db` but you could change that if you want. If the database file does not exist, the program just assumes that the database is empty.
collection = {}
databasename = "./default.db"
autosave = True

if os.path.exists(databasename):
	with open(databasename, "r+b") as f:
		serializeddata = f.read()
	collection = bson.loads(serializeddata)

# The dafualt way of using this program is through the CLI commandline. Even if there is a way of exposing the collection through FUSE, adding new discs to your collection still requires you to use CLI syntax. Learn it.
description = "This is the DiscGatherer software. Its purpose is to help you manage your collection of CD DVD and Bluray dics. The dafualt way of using this program is through the CLI commandline. Even if there is a way of exposing the collection through FUSE, adding new discs to your collection still requires you to use CLI syntax. Learn it."
parser = argparse.ArgumentParser(description=description, add_help=False)
parser.add_argument("-h", "--help", action="help", help="Display documentation.")
parser.add_argument("-a", "--add", action="store_true", help="Add /dev/sr0 disc to your collection.")
args = parser.parse_args()

# TODO: For now the entire database is auto-saved. It should only save if changed, and only using atomic file replacement. Stay tuned.
if autosave:
	serializeddata = bson.dumps(collection)
	with open(databasename, "w+b") as f:
		f.write(serializeddata)
