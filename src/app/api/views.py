import io
import pytz
import urllib
import uuid
import time
from flask import Blueprint, request, jsonify, make_response, redirect
from PIL import Image
from datetime import datetime, timedelta, timezone
from itertools import chain
from firebase_admin import auth
from jsonschema import validate
from app import app, gcsClient, DB #searchIndex #cos, botoSession,
#from pyArango.connection import *
#import pyArango
from app.api.modules.Timeline import Feed, TimelineJSON
from google.auth import compute_engine
from google.cloud import storage
from google.oauth2 import service_account
from algoliasearch.search_client import SearchClient


class objdict(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError("No such attribute: " + name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError("No such attribute: " + name)


session = None


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def epoch_to_datetime(epoch):
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=int(epoch))).replace(tzinfo=pytz.utc)


def datetime_to_epoch(dt):
    return int(dt.timestamp())

def getVisibility(user, q_user):
    if user is None or q_user is None:
        return None

    try:
        user = user.to_dict()
    except:
        pass

    try:
        q_user = q_user.to_dict()
    except:
        pass

    if user['uid'] == q_user['uid']:
        return "self"
    else:
        return "friends"

def add_user(email, uid, name):
    app.logger.debug("Reached add_user")

    created = datetime_to_epoch((datetime.utcnow().replace(tzinfo=pytz.utc)))
    data = {}
    data['uid'] = uid
    data['email'] = email
    data['name'] = name
    data['created_date'] = created
    newUser = DB.collection(u'Users').document(uid)
    newUser.set(data)
    return newUser


def format_user_response(user, visibility):
    #convert user to dict if needed
    #if type(user) == pyArango.document.Document:
        #user = user.getStore()
    try:
        user = user.to_dict()
    except:
        pass

    # make sure the user object has all the keys we need
    if "displayName" not in user.keys():
        user["displayName"] = ""
    if "created_date" not in user.keys():
        user["created_date"] = 0
    if "email" not in user.keys():
        user["email"] = ""
    if "visibility" not in user.keys():
        user["visibility"] = None
    if "_id" not in user.keys():
        user["_id"] = None

    if visibility == 'self' or visibility == 'friends':
        responseData = {
            'created_date': user['created_date'],
            'email': user['email'],
            'name': user['name'],
            'displayName': user['displayName'],
            'visibility': visibility,
            '_id': user['_id'],
            'uid': user['uid']
            }
    else:
        responseData = {
            'displayName': user['displayName'],
            'visibility': visibility,
            '_id': user['_id'],
            'uid': user['uid']
            }
    return responseData


def get_user_by_id(uid):
    app.logger.debug('starting get_user_by_id')
    app.logger.debug(uid)

    try:
        user = DB.collection(u'Users').document(uid).get()
    except Exception:
        app.logger.debug("some error")
        user = None

    app.logger.debug(user)
    app.logger.debug('done get_user_by_id')
    return user


def get_user(email):
    app.logger.debug('starting get_user')
    app.logger.debug(email)

    #user = Users.fetchFirstExample({'email': email}, 1)
    userQuery = DB.collection(u'Users').where(u'email', u'==', email).get()
    if len(userQuery) == 1:
        app.logger.debug('done get_user')
        return userQuery[0]
    else:
        app.logger.debug('done get_user')
        return None


def delete_file_from_cos(bucketName, key):
    app.logger.debug("starting delete")
    try:
        #cos.Object(bucket, key).delete()
        bucket = gcsClient.get_bucket(bucketName)
        blob = bucket.blob(key)
        blob.delete()
    except Exception as e:
        app.logger.debug(e)
        return None
    app.logger.debug("done delete")
    return 1


def upload_file_to_cos(imgFile, bucketName, user):
    app.logger.debug("starting upload")
    filename = imgFile.filename
    fileType = filename.rsplit('.', 1)[1].lower()

    if fileType.lower() == 'jpg':
        fileType = 'JPEG'

    key = str(uuid.uuid4()) + '.jpg'
    app.logger.debug('loading image')
    try:
        im = Image.open(imgFile)
    except Exception as e:
        print("Error: ", e)
        return None

    app.logger.debug('image loaded, now resizing')
    newFile = io.BytesIO()

    if im.width > 2048:
        newHeight = round((im.height / im.width) * 2048)
        newIm = im.resize((2048, newHeight))
        newIm.save(newFile, fileType)
    elif im.width > 960:
        newHeight = round((im.height / im.width) * 960)
        newIm = im.resize((960, newHeight))
        newIm.save(newFile, fileType)
    else:
        newHeight = round((im.height / im.width) * 720)
        newIm = im.resize((720, newHeight))
        newIm.save(newFile, fileType)

    app.logger.debug('done resizing')
    try:
        newFile.seek(0)
        ExtraArgs = {'Metadata': {'owner': user['uid'], 'filename': filename}}
        #cos.Object(bucket, key).upload_fileobj(newFile,
                                               #ExtraArgs=ExtraArgs
                                               #)
        bucket = gcsClient.get_bucket(bucketName)
        blob = bucket.blob(key)
        #nf1 = newFile.read()
        #nf = nf1.decode("utf-8")
        blob.upload_from_file(newFile)

    except Exception as e:
        print("Error: ", e)
        return None

    app.logger.debug("done upload")
    return {'key': key, 'blob': blob}


def validate_firebase_token(token):
    app.logger.debug(token)
    try:
        decoded_token = auth.verify_id_token(token)
    except Exception as e:
        if e == ConnectionError:
            decoded_token = False
        else:
            app.logger.debug(e.args[0])
            if 'expired' in e.args[0]:
                app.logger.debug('expired')
                decoded_token = 'expired'
            else:
                decoded_token = False
    app.logger.debug(decoded_token)
    return decoded_token


def validate_firebase_token_return_user(request):
    app.logger.debug('starting validate_firebase_token_return_user')
    token = request.headers.get('Authorization') or False
    app.logger.debug(request.headers)
    if token is False:
        app.logger.debug('didnt find auth token in header')
        token = request.args.get('token') or False
        app.logger.debug(request.headers)
    if token:
        decoded_token = validate_firebase_token(token)
        app.logger.debug('decoded_token')
        app.logger.debug(decoded_token)
        if decoded_token and decoded_token != 'expired':
            try:
                user = get_user(decoded_token['email'])
            except Exception as e:
                app.logger.debug(e)
                app.logger.debug("not decoded")
                user = None
        elif decoded_token == 'expired':
            app.logger.debug('decoded expired')
            user = 'expired'
        else:
            app.logger.debug('some other decode error?')
            user = None
    else:
        user = None
    app.logger.debug(user)
    app.logger.debug('done validate_firebase_token_return_user')
    return user


def get_image_url(image):
    app.logger.debug(app.config['GOOGLE_APPLICATION_CREDENTIALS'])
    credentials = service_account.Credentials.from_service_account_file(app.config['GOOGLE_APPLICATION_CREDENTIALS'])
    storage_client = storage.Client(credentials=credentials)
    #storage_client = storage.Client()
    bucket = storage_client.bucket(image['bucket'])
    blob = bucket.blob(image['key'])

    url = blob.generate_signed_url(
        version="v4",
        # This URL is valid for 15 minutes
        expiration=timedelta(hours=24),
        # Allow GET requests using this URL.
        method="GET",
    )

    imagePath = url
    data = {'url': imagePath,
            'id': str(image['uid']),
            'key': image['key']
            }
    return data


def deleteImage(imageObj):
    imageID = imageObj['id']
    try:
        imageObj = DB.collection(u'Images').document(imageID).get()
        image = imageObj.to_dict()
    except Exception:
        return False

    try:
        credentials = service_account.Credentials.from_service_account_file(app.config['GOOGLE_APPLICATION_CREDENTIALS'])
        storage_client = storage.Client(credentials=credentials)
        bucket = storage_client.bucket(image['bucket'])
        blob = bucket.blob(image['key'])
        blob.delete()
    except Exception:
        return False

    try:
        imageObj.delete()
    except Exception:
        return False

    return True

apiView = Blueprint('api', __name__)


@app.before_request
def before_request():
    global searchIndex

    client = SearchClient.create(app.config['ALGOLIA_CONFIG']["appId"],
                                 app.config['ALGOLIA_CONFIG']["searchKey"])
    searchIndex = client.init_index(app.config['ALGOLIA_CONFIG']["index"])
    searchIndex.set_settings({'attributesForFaceting': ['visibility']})


@app.teardown_request
def teardown_request(error=None):
    pass

@apiView.route('/', methods=['GET'])
def root():
    return make_response(jsonify({'status': 'ok'}), 200)

@apiView.route('/version', methods=['GET'])
def version():
    return make_response(jsonify({'version': 'dev'}), 200)


#
# Need a way to NOT hard code the image bucket
# Need a put method to add/remove tags
@apiView.route('/v1/images', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_images():
    if request.method == "GET":
        return "images"
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_images")
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            bucket = "onestoopimages01"

            if 'file' not in request.files:
                app.logger.debug('file not in request.files')
                responseData = jsonify({'status': 'missing file'})
                return make_response(responseData, 400)

            imgFile = request.files['file']

            if imgFile.filename == '':
                app.logger.debug('file name is blank')
                responseData = jsonify({'status': 'missing file'})
                return make_response(responseData, 400)

            if imgFile and allowed_file(imgFile.filename):
                imgBlob = upload_file_to_cos(imgFile, bucket, user)
                key = imgBlob['key']
                uid = key.split('.')
                blob = imgBlob['blob']

                if key:
                    #newImage = Images.createDocument()
                    data = {'user_id': user['uid'],
                            'created_date': int(datetime.utcnow().timestamp()),
                            'bucket': bucket,
                            'key': key,
                            'tags': None}

                    #for k,v in data.items():
                      #newImage[k] = v

                    newImageObj = DB.collection(u'Images').document()
                    newImageObj.set(data)

                    #newImage.save()

                    url = blob.generate_signed_url(
                        version="v4",
                        # This URL is valid for 24 hours
                        expiration=timedelta(hours=24),
                        # Allow GET requests using this URL.
                        method="GET",
                    )
                    imagePath = url
                    responseData = jsonify({'status': 'success',
                                            'imageID': newImageObj.id,
                                            'url': imagePath
                                            }
                                           )
                    return make_response(responseData, 201)
                else:
                    return make_response(jsonify({'status': 'failed'}), 400)
            else:
                return make_response(jsonify({'status': 'bad file'}), 400)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)

    elif request.method == "PUT":
        return "images"
    elif request.method == "DELETE":
        app.logger.debug("Reached DELETE in v1_images")
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            app.logger.debug("got user")

            key = request.args.get("key", default=None)
            if key is None:
                responseData = jsonify({'status': 'missing key param'})
                return make_response(responseData, 400)

            app.logger.debug("key")
            app.logger.debug(key)

            try:
                #image = Images[key]
                imageObj = DB.collection(u'Images').document(key).get()
                image = imageObj.to_dict()
                #post = Posts.fetchFirstExample({"_key": key, "author_id": user["uid"]})
            except Exception:
                responseData = jsonify({'status': 'image not found'})
                return make_response(responseData, 404)

            app.logger.debug("image")
            app.logger.debug(image)
            if image is None:
                app.logger.debug("image was None")
                responseData = jsonify({'status': 'image not found'})
                return make_response(responseData, 404)

            app.logger.debug("trying to delete from cos")
            d = delete_file_from_cos(image['bucket'], image['key'])
            if d:
                imageObj.delete()
                return make_response(jsonify({'status': 'success'}), 200)
            else:
                return make_response(jsonify({'status': 'failed'}), 400)
        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)


@apiView.route('/v1/status', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_status():
    return make_response(jsonify({'status': 'up'}), 200)


#
# Need a delete method that cleans up all data
# Need a put method to update user
@apiView.route('/v1/users', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_users():
    if request.method == "GET":
        app.logger.debug("Reached GET in v1_user")
        app.logger.debug(request.headers)

        displayName = request.args.get("displayName", default=None)
        q_id = request.args.get("userId", default=None)
        q_email = request.args.get("email", default=None)

        if displayName and q_id:
            userObj = get_user_by_id(q_id)
            user = userObj.to_dict()
            if user and 'displayName' in user.to_dict().keys():
                responseData = {'status': 'ok', 'user': {"displayName": user['displayName'], 'uid': user['uid']}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 200)
            elif user:
                responseData = {'status': 'ok', 'user': {"displayName": '', 'uid': user['uid']}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 200)
            else:
                responseData = {'status': 'not found', 'user': {"displayName": '', 'uid': user['uid']}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 404)

        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            if q_email is None:
                return make_response(jsonify({'status': 'not found'}), 404)
            else:
                q_userObj = get_user(q_email)
                q_user = q_userObj.to_dict()
                if q_user:
                    visibility = getVisibility(user, q_user)
                    responseData = format_user_response(q_user, visibility)
                    return make_response(jsonify(responseData), 200)
                else:
                    responseData = {'status': 'not found'}
                    return make_response(jsonify(responseData), 400)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_User")
        token = request.headers.get('Authorization') or False
        if token is False:
            app.logger.debug('didnt find auth token in header')
            token = request.args.get('token') or False
            app.logger.debug(request.headers)
        if token:
            app.logger.debug("Here is your token!!!!!")
            app.logger.debug(token)
            decoded_token = validate_firebase_token(token)
        else:
            decoded_token = False

        if decoded_token and decoded_token != 'expired':
            app.logger.debug("decoded_token")
            app.logger.debug(decoded_token)
            email = decoded_token['email']
            uid = decoded_token['uid']
            name = request.args.get('name') or None

            existingUser = get_user(email)

            if existingUser:
                app.logger.debug("existingUser")
                return make_response(jsonify({'status': 'ok'}), 200)
            else:
                user = add_user(email,
                                uid,
                                name)
                return make_response(jsonify({'status': 'ok'}), 200)

        elif decoded_token == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    else:
        return make_response(jsonify({'status': 'failed'}), 400)


@apiView.route('/v1/users/<userId>', methods=['GET', 'PATCH', 'POST', 'PUT', 'DELETE'])
def v1_users_id(userId):
    #global Users

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_users_userId")
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        qUser = get_user_by_id(userId)
        visibility = getVisibility(user, qUser)
        responseData = format_user_response(qUser, visibility)
        return make_response(jsonify(responseData), 200)


###########################
def loadRecipe(r, recipes):
    app.logger.debug("doign loadRecipe")
    images = []
    for iNum, imageObj in enumerate(r['images']):
        imageID = imageObj['id']
        #try:
        #image = Images[imageID]
        imageDoc = DB.collection(u'Images').document(imageID).get()
        image = imageDoc.to_dict()
        image['uid'] = imageDoc.id
        image = get_image_url(image)
        #images.append(image)
        images.append({"image": image, "position": int(imageObj['position'])})
        #r['images'] = images
        r['images'] = sorted(images, key = lambda i: i['position'])
        app.logger.debug('this is images')
        app.logger.debug(images)
        #except Exception as e:
            #app.logger.debug(e)

    #rId = r['_id'].split('/')
    #r['_id'] = rId[1]
    recipes['recipes'].append(r)
    return recipes


@apiView.route('/v1/recipes', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes():
    #global Recipes
    #global db
    #global cookingDB
    #global Images

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes")
        app.logger.debug(request.url)
        app.logger.debug(request.headers)

        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        authorEmail = request.args.get("author", default=None)

        recipeType = request.args.get("recipeType", default=None)
        if recipeType:
            recipeType = recipeType.lower()

        limit = request.args.get("limit", default=10)
        limit = int(limit)
        #nextOffset = request.args.get("nextOffset", default=0)
        #nextOffset = int(nextOffset)
        nextId = request.args.get("nextId", default=None)

        if authorEmail:
            q_userObj = get_user(authorEmail)
            q_user = q_userObj.to_dict()
        else:
            q_user = None

        if int(limit) > 100:
            limit = 100

        fRecipes = DB.collection(u'Recipes')
        query = fRecipes.where(u'created_date', u'>', 1).order_by(u'created_date')
        if q_user:
            app.logger.debug("got q_user")
            query = query.where(u'authorId', u'==', q_user['uid'])

        if user == None or user == 'expired':
            app.logger.debug("user expired or none")
            query = query.where(u'visibility', u'==', u'public')
        elif q_user == None:
            app.logger.debug("q_user is none")
            query = query.where(u'visibility', u'==', u'public')
        elif q_user['uid'] != user['uid']:
            app.logger.debug("q_user and user not matched")
            query = query.where(u'visibility', u'==', u'public')
        elif q_user['uid'] == user['uid']:
            app.logger.debug("must be users recipes")
            pass
        else:
            app.logger.debug("something else?")
            app.logger.debug(q_user)
            app.logger.debug(user)
            query = query.where(u'visibility', u'==', u'public')

        if recipeType:
            app.logger.debug("got recipeType")
            query = query.where(u'recipeType', u'==', recipeType)

        if nextId:
            app.logger.debug("got nextId")
            nextDoc = fRecipes.document(nextId)
            snapShot = nextDoc.get()
            query = query.start_at(snapShot)\
                .limit(limit + 1)
        else:
            app.logger.debug("doing else")
            query = query.limit(limit + 1)

        docs = query.stream()
        recipes = {"recipes": []}
        for doc in docs:
            app.logger.debug(doc.id)
            d = doc.to_dict()
            d['_id'] = doc.id
            d['uid'] = doc.id
            recipes = loadRecipe(d, recipes)

        if len(recipes['recipes']) <= limit:
            app.logger.debug("no more results")
            recipes['moreResults'] = False
        else:
            app.logger.debug("must be more")
            lastDoc = recipes['recipes'].pop()
            recipes['nextId'] = lastDoc['_id']
            recipes['moreResults'] = True

        app.logger.debug("from firestore")
        #app.logger.debug(recipes)
        return make_response(jsonify(recipes), 200)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            try:
                data = request.get_json()
                app.logger.debug(data)
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

            schema = {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "prepTime": {"type": "number"},
                    "cookTime": {"type": "number"},
                    "servings": {"type": "number"},
                    "recipeType": {"type": "string"},
                    "recipeSubType": {"type": "string"},
                    "cusine": {"type": "string"},
                    "mealTime": {"type": "string"},
                    "ingredients": {"type": "array"},
                    "description": {"type": "string"},
                    "directions": {"type": "string"},
                    "visibility": {"type": "string"},
                    "images": {"type": "array"}
                }
            }

            try:
                validate(instance=data, schema=schema)
            except Exception:
                app.logger.debug("JSON validating failed")
                return make_response(jsonify({'status': 'bad JSON'}), 400)

            data['authorId'] = user['uid']
            data['bookmarked'] = 0
            data['rating'] = 0
            data['ratingCount'] = 0
            data['shares'] = 0
            data['visibility'] = data['visibility'].lower()
            data['cusine'] = data['cusine'].lower()
            data['recipeType'] = data['recipeType'].lower()
            data['recipeSubType'] = data['recipeSubType'].lower()
            data["created_date"] = int(time.time())

            newImages = []
            for i, image in enumerate(data['images']):
                newImages.append({"id": image, "position": i})
            data['images'] = newImages

            #try:
                #newRecipe = Recipes.createDocument(data)
                #newRecipe.save()
            #try:
            doc = DB.collection(u'Recipes').document()
            doc.set(data)
            #except Exception:
                #return make_response(jsonify({'status': 'fail'}), 400)

            return make_response(jsonify({'status': 'ok'}), 200)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif  request.method == "PUT":
        return
    elif  request.method == "DELETE":
        return
    else:
        return

@apiView.route('/v1/recipes/search', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes_search():
    if request.method == "GET":
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        q = request.args.get("q", default=None)

        if q == None:
            return make_response(jsonify({'status': 'q is required'}), 400)


        hits = searchIndex.search(q, {'filters': "visibility:'public'"})

        recipes = {"recipes": []}
        for doc in hits['hits']:
            app.logger.debug(doc['objectID'])
            #d = doc.to_dict()
            doc['_id'] = doc['objectID']
            doc['uid'] = doc['objectID']
            recipes = loadRecipe(doc, recipes)

        recipes['moreResults'] = False

        return make_response(jsonify(recipes), 200)


@apiView.route('/v1/recipes/<recipeId>', methods=['GET', 'PATCH', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id(recipeId):
    #global Recipes
    #global db
    #global cookingDB
    #global Images

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if '/' in recipeId:
            r = recipeId.split('/')
            recipeId = r[1]

        #try:
            #recipe = Recipes[recipeId]
        try:
            docRef = DB.collection(u'Recipes').document(recipeId)
            doc = docRef.get()
            recipe = doc.to_dict()
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)

        if recipe['visibility'].lower() == 'private':
            if user == None or user == 'expired':
                app.logger.debug("this should be private")
                return make_response(jsonify({'status': 'not found'}), 401)
            if user['uid'] != recipe['authorId']:
                app.logger.debug("this should be private")
                return make_response(jsonify({'status': 'not found'}), 401)

        recipes = {"recipes": []}
        #recipes = loadRecipe(recipe.getStore(), recipes)
        recipes = loadRecipe(recipe, recipes)
        app.logger.debug(recipes)

        return make_response(jsonify(recipes),200)
    elif request.method == "PATCH":
        app.logger.debug("Reached PATCH in v1_recipes_id")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if '/' in recipeId:
            r = recipeId.split('/')
            recipeId = r[1]

        #try:
            #recipe = Recipes[recipeId]
        try:
            docRef = DB.collection(u'Recipes').document(recipeId)
            doc = docRef.get()
            recipe = doc.to_dict()
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)

        if user['uid'] != recipe['authorId']:
            return make_response(jsonify({'status': 'Unauthorized'}), 401)

        try:
            data = request.get_json()
            app.logger.debug(data)
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)

        goodKeys = ["cookTime",
                    "cusine",
                    "description",
                    "directions",
                    "images",
                    "ingredients",
                    "mealTime",
                    "notes",
                    "prepTime",
                    "recipeSubType",
                    "recipeType",
                    "servings",
                    "source",
                    "title",
                    "visibility"
                    ]

        for key, value in data.items():
            if key not in goodKeys:
                continue

            if key == "images":
                pass
            else:
                recipe[key] = value

        #try:
            #recipe.save()
        try:
            DB.collection(u'Recipes').document(recipeId).set(recipe)
        except Exception:
            return make_response(jsonify({'status': 'database error'}), 500)

        return make_response(jsonify({'status': 'ok'}), 200)

    elif request.method == "POST":
        return
    elif request.method == "PUT":
        return
    elif request.method == "DELETE":
        app.logger.debug("Reached DELETE in v1_recipes_id")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if '/' in recipeId:
            r = recipeId.split('/')
            recipeId = r[1]

        #try:
            #recipe = Recipes[recipeId]
        try:
            docRef = DB.collection(u'Recipes').document(recipeId)
            recipeObj = docRef.get()
            recipe = recipeObj.to_dict()
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)

        if user['uid'] != recipe['authorId']:
            return make_response(jsonify({'status': 'Unauthorized'}), 401)

        # delete the reviews
        #try:
            #aql = 'FOR r in Reviews FILTER r.recipeId == "' + recipeId + '" ' \
                #' REMOVE r in Reviews'
            #r = cookingDB.AQLQuery(aql, rawResults=True, batchSize=100)
        try:
            fRecipes = DB.collection(u'Reviews')
            query = fRecipes.where(u'recipeId', u'==', recipeId)
            docs = query.stream()
            for doc in docs:
                DB.collection(u'Reviews').document(doc.id).delete()
        except Exception:
            app.logger.debug("failed reviews delete")
            return make_response(jsonify({'status': 'Error'}), 500)

        # delete the images
        for image in recipe['images']:
            deleteImage(image)

        # delete recipe
        try:
            DB.collection(u'Recipes').document(recipeId).delete()
        except Exception:
            app.logger.debug("failed recipe delete")
            return make_response(jsonify({'status': 'Error'}), 500)

        return make_response(jsonify({'status': 'ok'}), 200)
    else:
        return

@apiView.route('/v1/recipes/<recipeId>/reviews', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id_reviews(recipeId):
    #global Recipes
    #global db
    #global cookingDB
    #global Reviews
    #global Users

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id_reviews")

        limit = request.args.get("limit", default=10)
        limit = int(limit)
        #offset = request.args.get("offset", default=0)
        nextId = request.args.get("nextId", default=None)

        #aql = 'FOR r in Reviews FILTER r.recipeId == "' + recipeId + '" ' \
            #' sort r.created_date DESC LIMIT ' + str(offset) \
            #+ ', ' + str(limit) + ' RETURN r'

        #aqlCount = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT WITH COUNT INTO length RETURN length'

        #app.logger.debug(aql)
        #try:
            #r = cookingDB.AQLQuery(aql, rawResults=True, batchSize=100)
            #c = cookingDB.AQLQuery(aqlCount, rawResults=True, batchSize=100)
            #q = r.response['result']
            #count = c.response['result'][0]
        #except:
            #q = []

        fReviews = DB.collection(u'Reviews')
        countObj = fReviews.where(u'recipeId', u'==', recipeId).get()
        count = len(countObj)
        query = fReviews.where(u'created_date', u'>', 1).order_by(u'created_date')
        query = query.where(u'recipeId', u'==', recipeId)

        if nextId:
            app.logger.debug("got nextId")
            nextDoc = fReviews.document(nextId)
            snapShot = nextDoc.get()
            query = query.start_at(snapShot)\
                .limit(limit + 1)
        else:
            app.logger.debug("doing else")
            query = query.limit(limit + 1)

        reviewsList = query.get()
        reviews = {"reviews": reviewsList}
        if len(reviews['reviews']) <= limit:
            app.logger.debug("no more results")
            reviews['moreResults'] = False
        else:
            app.logger.debug("must be more")
            lastDoc = reviews['reviews'].pop()
            reviews['nextId'] = lastDoc['uid']
            reviews['moreResults'] = True

        #reviews = {'reviews': q}
        reviews['total'] = count

        #if len(q) < int(limit):
            #reviews['nextOffset'] = int(offset)
            #reviews['moreResults'] = False
        #else:
            #reviews['nextOffset'] = int(offset) + int(limit)
            #reviews['moreResults'] = True

        for i, review in enumerate(reviews['reviews']):
            #app.logger.debug(review['authorId'])
            #u = Users[review['authorId'].split('/')[1]]
            #reviews['reviews'][i]['authorId'] = u.displayName
            uObj = DB.collection(u'Users').document(review['authorId']).get()
            uDict = uObj.to_dict()
            reviews['reviews'][i]['authorId'] = uDict['name']

        app.logger.debug(reviews)
        return make_response(jsonify(reviews), 200)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes_id_reviews")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            try:
                data = request.get_json()
                app.logger.debug(data)
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)

        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "score": {"type": "number"}
                }
            }

        try:
            validate(instance=data, schema=schema)
        except Exception:
            app.logger.debug("JSON validating failed")
            return make_response(jsonify({'status': 'bad JSON'}), 400)

        if data['recommend'].lower() == 'true' or data['recommend'].lower() == 'yes':
            data['recommend'] = 'Yes'
        elif data['recommend'].lower() == 'false' or data['recommend'].lower() == 'no':
            data['recommend'] = 'No'
        else:
            data['recommend'] = None

        #data['authorId'] = user['_id']
        data['authorId'] = user['uid']
        data["created_date"] = int(time.time())
        data["recipeId"] = recipeId

        #try:
            #newReview = Reviews.createDocument(data)
            #newReview.save()
        try:
            newReview = DB.collection(u'Reviews').document()
            newReview.set(data)
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)

        #update the recipe with Metadata
        #try:
            #aqlScore = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT AGGREGATE score = AVG(doc.score) RETURN score'
            #aqlCount = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT WITH COUNT INTO length RETURN length'
            #s = cookingDB.AQLQuery(aqlScore, rawResults=True)
            #c = cookingDB.AQLQuery(aqlCount, rawResults=True)
            #score = round(s.response['result'][0],2)
            #count = c.response['result'][0]
            #recipe = Recipes[recipeId]
            #recipe['rating'] = score
            #recipe['ratingCount'] = count
            #recipe.save()
        try:
            fReviews = DB.collection(u'Reviews')
            reviewsObj = fReviews.where(u'recipeId', u'==', recipeId).get()
            count = len(reviewsObj)
            docRef = DB.collection(u'Recipes').document(recipeId)
            doc = docRef.get()
            recipe = doc.to_dict()
            reviews = reviewsObj.to_dict()

            score = 0
            for review in reviews:
                score += int(review['score'])

            score = score/count
            recipe['rating'] = score
            recipe['ratingCount'] = count

            DB.collection(u'Recipes').document(recipeId).set(recipe)
        except Exception:
            pass

        review = {"reviews": [newReview.to_dict()]}
        app.logger.debug(review)
        #try:
        #u = Users[review['reviews'][0]['authorId'].split('/')[1]]
        #review['reviews'][0]['authorId'] = u.displayName
        #except:
            #pass
        return make_response(jsonify(review), 200)
    elif request.method == "PUT":
        return
    elif request.method == "DELETE":
        return
    else:
        return


@apiView.route('/v1/recipes/<recipeId>/bookmarks', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id_bookmarks(recipeId):
    #global Recipes
    #global db
    #global cookingDB
    #global Users

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id_bookmarks")
        return
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes_id_bookmarks")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if user and user != 'expired':
            try:
                data = request.get_json()
                app.logger.debug(data)
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

            schema = {
                "type": "object",
                "properties": {
                    "recipeId": {"type": "string"},
                    "bookmarked": {"type": "string"},
                    }
                }

            try:
                validate(instance=data, schema=schema)
            except Exception:
                app.logger.debug("JSON validating failed")
                return make_response(jsonify({'status': 'bad JSON'}), 400)





        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
        return
    elif request.method == "PUT":
        return
    elif request.method == "DELETE":
        return
    else:
        return

@apiView.route('/v1/recipeTypes', methods=['GET'])
def v1_recipeTypes():
    app.logger.debug("Reached GET in v1_recipeTypes")
    qtype = request.args.get("type", default="jim")
    app.logger.debug(request)
    app.logger.debug(qtype)

    if qtype.lower() == "appetizers":
        types = {"types":
                     ["Appetizers - Other",
                      "Beans and Legumes",
                      "Canapes and Bruschetta",
                      "Cheese",
                      "Deviled Eggs",
                      "Dips and Spreads",
                      "Fruit",
                      "Grilled",
                      "Meat",
                      "Mushrooms",
                      "Nuts and Seeds",
                      "Olives",
                      "Pastries",
                      "Pickles",
                      "Seafood",
                      "Snacks",
                      "Spicy",
                      "Vegetable",
                      "Wraps and Rolls"
                      ]
                     }
        app.logger.debug('this should be right')
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "breads":
        types = {"types":
                     ["Breakfast Pastries",
                      "Challah",
                      "Cornbread",
                      "Flat Bread",
                      "Fruit Bread",
                      "Holiday Bread",
                      "Muffins",
                      "Popovers and Puddings",
                      "Pumpkin Bread",
                      "Quick Bread",
                      "Rolls and Buns",
                      "Rye Bread",
                      "Sourdough and Starters",
                      "Tortillas",
                      "White Bread",
                      "Whole Grain Bread",
                      "Yeast Bread",
                      "Zucchini Bread"
                      ]
                     }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "desserts":
        types = {"types":
                     ["Cakes",
                      "Candies",
                      "Chocolate",
                      "Cobblers",
                      "Cookies and Bars",
                      "Custards and Puddings",
                      "Dessert Gelatins",
                      "Dessert Sauces",
                      "Dessert - Other",
                      "Frozen Treats",
                      "Fruit Crisps",
                      "Fruit Crumbles",
                      "Liqueur Flavored Desserts",
                      "Meringues",
                      "Mousse",
                      "Pies",
                      "Tiramisu",
                      "Trifles"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "drinks":
        types = {"types":
                     ["Drinks - Other",
                      "Beer",
                      "Chocolate",
                      "Cider",
                      "Cocktails",
                      "Coffee",
                      "Eggnog",
                      "Hot Chocolate",
                      "Kahlua",
                      "Lemonade",
                      "Liqueurs",
                      "Mocktails",
                      "Punch",
                      "Sangria",
                      "Shakes and Floats",
                      "Smoothies",
                      "Tea"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "main dishes":
        types = {"types":
                     ["Burgers",
                      "Casseroles",
                      "Deep Fried",
                      "Fish and Shellfish",
                      "Grill and BBQ",
                      "Main Dish - Other",
                      "Meat - Steaks and Chops",
                      "Meatless",
                      "Meatloaf",
                      "Pasta",
                      "Pizza and Calzones",
                      "Poultry",
                      "Ribs",
                      "Roasts",
                      "Sandwiches and Wraps",
                      "Slow Cooker",
                      "Stir-Fries",
                      "Stuffed Peppers",
                      "Tacos, Burritos and Enchilladas",
                      "Wild Game"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "salads":
        types = {"types":
                     ["Bean",
                      "Coleslaw",
                      "Croutons and Toppings",
                      "Dressings and Vinaigretts",
                      "Egg Salads",
                      "Fruit Salads",
                      "Grains",
                      "Green Salads",
                      "Meat and Seafood",
                      "Pasta Salads",
                      "Potato Salads",
                      "Salads - Other",
                      "Vegetable Salads"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "side dishes":
        types = {"types":
                     ["Bean and Peas",
                      "Casseroles",
                      "Dumplings",
                      "French Fries",
                      "Grains",
                      "Potatoes",
                      "Rice",
                      "Seafood",
                      "Sides - Other",
                      "Vegetables"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "soups":
        types = {"types":
                     ["Bean and Legumes",
                      "Broth Stocks",
                      "Cheese Soups",
                      "Chili",
                      "Chowders",
                      "Cream-style Soups",
                      "Dry Soup Mixes",
                      "Meat and Poultry",
                      "Noodle",
                      "Seafood",
                      "Soups - Other",
                      "Stews",
                      "Vegetable"
                     ]
                }
        return make_response(jsonify(types), 200)
    elif qtype.lower() == "sauces":
        types = {"types":
                     ["Marinade",
                      "Sauce"
                     ]
                }
        return make_response(jsonify(types), 200)
    else:
        types = {"types": ["other"]}
        return make_response(jsonify(types), 200)



##############
############## auto ###############
@apiView.route('/auto/v1/vehicles', methods=['GET', 'POST', 'PUT', 'DELETE'])
def auto_v1_vehicles():

    userObj = validate_firebase_token_return_user(request)
    if type(userObj) != str and userObj != None:
        user = userObj.to_dict()
    else:
        user = userObj

    if user and user != 'expired':
        pass
    elif user == 'expired':
        return make_response(jsonify({'status': 'expired'}), 401)
    else:
        return make_response(jsonify({'status': 'failed'}), 401)

    if request.method == "GET":
        app.logger.debug("Reached GET in /auto/v1/vehicles")
        app.logger.debug(request.url)
        app.logger.debug(request.headers)

        vehicles = DB.collection(u'Vehicles')
        query = vehicles.where(u'uid', u'==', user['uid'])

        docs = query.stream()
        myVehicles = {"vehicles": []}
        for doc in docs:
            app.logger.debug(doc.id)
            d = doc.to_dict()
            d['vid'] = doc.id
            myVehicles['vehicles'].append(d)


        return make_response(jsonify(myVehicles), 200)



    elif request.method == "POST":
        """
        {
        "vehicles": {
            [id]: {
            "uid": str,
            "createdDate": int,
            "status": str,
            "type": str,
            "mfg": str,
            "model": str,
            "year": int,
            "nickname": str,
            "tanks": [
                {
                "name": str,
                "fuelType": str,
                "capacity": float
                }
            ]
            "units": str,
            "licensePlate": str,
            "licensePlateExp": int,
            "lastInspection": int,
            "chassisNumber": str,
            "vin": str,
            "notes": str,
            "updated": int
            }
          }
        }
        """
        try:
            data = request.get_json()
            app.logger.debug(data)
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)

        data['uid'] = user['uid']
        data['created'] = int(time.time())
        data['updated'] = int(time.time())

        try:
            doc = DB.collection(u'Vehicles').document()
            doc.set(data)
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)

        vehicles = DB.collection(u'Vehicles')
        query = vehicles.where(u'uid', u'==', user['uid'])

        docs = query.stream()
        myVehicles = {"vehicles": []}
        for doc in docs:
            app.logger.debug(doc.id)
            d = doc.to_dict()
            d['uid'] = doc.id
            myVehicles['vehicles'].append(d)

        return make_response(jsonify(myVehicles), 200)


@apiView.route('/auto/v1/vehicles/<vehiclesId>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def auto_v1_vehicles_vehiclesId(vehiclesId):

    if request.method == "GET":
        pass
    elif request.method == "POST":
        app.logger.debug("Reached POST in auto_v1_vehicles_vehiclesId")
        app.logger.debug(request.headers)
        userObj = validate_firebase_token_return_user(request)
        if type(userObj) != str and userObj != None:
            user = userObj.to_dict()
        else:
            user = userObj

        if '/' in vehiclesId:
            r = vehiclesId.split('/')
            vehiclesId = r[1]

        try:
            docRef = DB.collection(u'Vehicles').document(vehiclesId)
            doc = docRef.get()
            vehicle = doc.to_dict()
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)

        if user['uid'] != vehicle['uid']:
            return make_response(jsonify({'status': 'Unauthorized'}), 401)

        try:
            data = request.get_json()
            app.logger.debug(data)
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)

        goodKeys = [
            "uid",
            "createdDate",
            "active",
            "type",
            "mfg",
            "model",
            "year",
            "nickname",
            "tanks",
            "units",
            "licensePlate",
            "licensePlateExp",
            "lastInspection",
            "chassisNumber",
            "vin",
            "notes",
            "updated"
                    ]

        for key, value in data.items():
            if key not in goodKeys:
                continue

            if key == "images":
                pass
            else:
                vehicle[key] = value

        vehicle['updated'] = int(time.time())

        try:
            DB.collection(u'Vehicles').document(vehiclesId).set(vehicle)
        except Exception:
            return make_response(jsonify({'status': 'database error'}), 500)

        return make_response(jsonify({'status': 'ok'}), 200)
