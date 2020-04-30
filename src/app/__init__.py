import firebase_admin
from flask import Flask
from firebase_admin import credentials
from flask_cors import CORS
import boto3

app = Flask(__name__)
app.config.from_object('config')
app.debug = app.config['DEBUG']
cred = credentials.Certificate(app.config['FIREBASE_CONFIG'])
fb_app = firebase_admin.initialize_app(cred)
CORS(app, resources={r"/v1/*": {"origins": "*"}})
app.config['CORS_HEADERS'] = 'Content-Type'


boto3Session = boto3.session.Session()
botoSession = boto3Session.client('s3',
                                  region_name='nyc3',
                                  endpoint_url='https://onestoop00001.nyc3.digitaloceanspaces.com',
                                  aws_access_key_id=app.config['SPACES_KEY'],
                                  aws_secret_access_key=app.config['SPACES_SECRET'])

cos = boto3.resource('s3',
                     region_name='nyc3',
                     endpoint_url='https://onestoop00001.nyc3.digitaloceanspaces.com',
                     aws_access_key_id=app.config['SPACES_KEY'],
                     aws_secret_access_key=app.config['SPACES_SECRET'])


try:
    buckets = cos.buckets.all()
    for bucket in buckets:
        print("Bucket Name: {0}".format(bucket.name))
except ClientError as be:
    print("CLIENT ERROR: {0}\n".format(be))
except Exception as e:
    print("Unable to retrieve list buckets: {0}".format(e))

if (app.debug):
    from werkzeug.debug import DebuggedApplication
    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)

from .api.views import apiView as apiView
CORS(apiView)
app.register_blueprint(apiView)

for rule in app.url_map.iter_rules():
    print(rule)
