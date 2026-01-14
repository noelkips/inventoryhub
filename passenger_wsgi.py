import os
import sys


sys.path = [p for p in sys.path if "alt-python" not in p]


from itinventory.wsgi import application