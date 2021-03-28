import os
import json
from ssl import PROTOCOL_TLSv1_2, CERT_REQUIRED

BASE_URL = os.environ.get('BASE_URL')

# Generate a secret random key for the session
SECRET_KEY = os.urandom(24)
DEBUG = os.environ.get('DEBUG')

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

SPACES_KEY = os.environ.get('SPACES_KEY')
SPACES_SECRET = os.environ.get('SPACES_SECRET')

ARANGODB_SETTINGS = json.loads(os.environ.get('ARANGODB_SETTINGS'))

ALGOLIA_CONFIG = json.loads(os.environ.get('ALGOLIA_CONFIG'))

FIREBASE_CONFIG = json.loads(os.environ.get('FIREBASE_CONFIG'))
print(os.getcwd())
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
