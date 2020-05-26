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
from app import app, cos, botoSession
from pyArango.connection import *
from app.api.modules.Image import Image as ImageObj
from app.api.modules.Timeline import Feed, TimelineJSON

#
# Some notes
# Need to support videos.

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


def http_decode(data):
    data_unquoted = urllib.unquote(urllib.unquote(data))
    http_codes = (
        ("'", '&#39;'),
        ('"', '&quot;'),
        ('>', '&gt;'),
        ('<', '&lt;'),
        ('&', '&amp;')
    )
    for code in http_codes:
        data_unquoted = data_unquoted.replace(code[1], code[0])
    return data_unquoted


def epoch_to_datetime(epoch):
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=int(epoch))).replace(tzinfo=pytz.utc)


def datetime_to_epoch(dt):
    return int(dt.timestamp())


def addFollowers(follower=None, following=None):
    app.logger.debug("Reached addFollowers")
    app.logger.debug(follower)
    app.logger.debug(following)
    try:
        followingObject = Following.objects(user_uid=follower.uid).first()
    except Exception:
        followingObject = None

    app.logger.debug(followingObject)
    if followingObject is None:
        try:
            followingObject = Following(user_uid=follower.uid, following=[following.uid])
            followingObject.save()
        except Exception:
            followingObject = None
    else:
        if following.uid not in followingObject.following:
            followingObject.following += [following.uid]
            followingObject.save()

    try:
        followersObject = Followers.objects(user_uid=following.uid).first()
    except Exception:
        followersObject = None

    if followersObject is None:
        try:
            followersObject = Followers(user_uid=following.uid, followers=[follower.uid])
            followersObject.save()
        except Exception:
            followersObject = None
    else:
        if follower.uid not in followersObject.followers:
            followersObject.followers += [follower.uid]
            followersObject.save()

    app.logger.debug("done addFollowers")
    return followingObject


def add_user(email, uid, name):
    app.logger.debug("Reached add_user")

    created = datetime_to_epoch((datetime.utcnow().replace(tzinfo=pytz.utc)))
    newUser = Users.createDocument()
    #newUser['_id'] = "Users/" + uid
    #newUser['_key'] = uid
    newUser['uid'] = uid
    newUser['email'] = email
    newUser['name'] = name
    newUser['created_date'] = created
    newUser.save()
    return newUser


def format_user_response(user, visibility):
    if visibility == 'self' or visibility == 'friends':
        responseData = {'created_date': 1571843230,
                        'email': user['email'],
                        'name': user['name'],
                        'visibility': visibility,
                        '_id': user['_id']
                        }
    else:
        responseData = {'created_date': 1571843230,
                        'email': user['email'],
                        'name': user['name'],
                        'visibility': visibility,
                        '_id': user['_id']
                        }
    return responseData


def get_feed(user, start_time, end_time, limit):
    global db
    app.logger.debug('starting get_feed')

    data = Feed(user_id=user['_id'],
                start_time=start_time,
                end_time=end_time,
                limit=limit, db=db)

    app.logger.debug('done get_feed')

    return data


def get_user_by_id(uid):
    app.logger.debug('starting get_user_by_id')
    app.logger.debug(uid)
    
    if '/' in uid:
        u = uid.split('/')
        uid = u[1]

    try:
        user = Users[uid]
    except Exception:
        user = None

    app.logger.debug('done get_user_by_id')
    return user

def get_user_by_uuid(uid):
    app.logger.debug('starting get_user_by_uuid')
    app.logger.debug(uid)

    if '/' in uid:
        u = uid.split('/')
        uid = u[1]

    try:
        #user = Users_by_uuid.objects(uid=uid).first()
        #user = Users.objects(collection='Users', uid=uid).first()
        user = Users.fetchFirstExample({'uid': uid}, 1)
    except Exception:
        user = None

    app.logger.debug(user['email'])
    app.logger.debug('done get_user_by_uuid')
    return user


def get_user(email):
    app.logger.debug('starting get_user')
    app.logger.debug(email)

    user = Users.fetchFirstExample({'email': email}, 1)
    if len(user) == 1:
        app.logger.debug(user[0])
        app.logger.debug('done get_user')
        return user[0]
    else:
        app.logger.debug('done get_user')
        return None
    #user = Users.objects(collection='Users', email=email).first()
    ##user = UsersM.objects(email=email).first()
    #try:
        #user_search = session.prepare('SELECT * from users_by_email where email=?')
        #user_results = session.execute(user_search, [email])
        #user = objdict(user_results[0])
    #except Exception:
        #user = None

    app.logger.debug(user)
    app.logger.debug('done get_user')
    return user


def getVisibility(user, q_user):
    # user=the logged in user
    # q_user=the person we need to find the relationship with

    app.logger.debug('starting getVisibility')
    if user is None or q_user is None:
        return None

    if user['_id'] == q_user['_id']:
        return "self"

    aql = 'FOR r IN Relations Filter r._from == "' + user['_id'] + '" AND ' \
        'r._to == "' + q_user['_id'] + '" LIMIT 1 RETURN r'
    q = db.AQLQuery(aql, rawResults=True, batchSize=100)
    
    if len(q) == 0:
        following = False
        friends = False
    else:
        following = q[0]['follow']
        friends = q[0]['friend']
        
    if following == False and friends == False:
        visibility = None
    elif following == True and friends == False:
        visibility = 'following'
    elif friends == True:
        visibility = 'friends'

    app.logger.debug(visibility)
    app.logger.debug('done getVisibility')
    return visibility


def delete_file_from_cos(bucket, key):
    app.logger.debug("starting delete")
    try:
        cos.Object(bucket, key).delete()
    except Exception as e:
        app.logger.debug(e)
        return None
    app.logger.debug("done delete")
    return 1


def upload_file_to_cos(imgFile, bucket, user):
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
        ExtraArgs = {'Metadata': {'owner': user['_id'], 'filename': filename}}
        cos.Object(bucket, key).upload_fileobj(newFile,
                                               ExtraArgs=ExtraArgs
                                               )
    except Exception as e:
        print("Error: ", e)
        return None

    app.logger.debug("done upload")
    return key


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
    #image = objdict(i)

    url = botoSession.generate_presigned_url(ClientMethod="get_object",
                                             Params={'Bucket': image['bucket'],
                                             'Key': image['key']},
                                              ExpiresIn=86400)
        
    imagePath = url
    data = {'url': imagePath,
            'id': str(image['image_uid']),
            'key': image['key']
            }
    return data


apiView = Blueprint('api', __name__)


@app.before_request
def before_request():
    global db
    global cookingDB
    global Comments
    global Images
    global Posts
    global Relations
    global Users
    global Requests
    global Recipes
    global Reviews
    global conn

    conn = Connection(arangoURL='https://db.onestoop.com:8529',
                      username=app.config['ARANGODB_SETTINGS']['username'],
                      password=app.config['ARANGODB_SETTINGS']['password'],)
    db = conn['onestoop']
    Comments = db['Comments']
    Images = db['Images']
    Posts = db['Posts']
    Relations = db['Relations']
    Users = db['Users']
    Requests = db['Requests']
    
    cookingDB = conn['cooking']
    Recipes = cookingDB['Recipes']
    Reviews = cookingDB['Reviews']

    ## Bluemix proxy sets a $WSSC header to either http or https.
    ## All triffic to flask is http.
    ## So if $WSSC is set to http we should redirect the user to https.
    #if request.headers.get('$WSSC') == "http":
        #url = request.url.replace('http://', 'https://', 1)
        #return redirect(url, code=301)

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
# Would like to support sub-comments
# Would like to support images in comments
@apiView.route('/v1/comments', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_comments():
    global Comments

    if request.method == "GET":
        return make_response(jsonify({'status': 'ok'}), 200)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_comments")
        user = validate_firebase_token_return_user(request)

        if user and user != 'expired':
            app.logger.debug("decoded worked")
            try:
                commentJSON = request.get_json()
                app.logger.debug(commentJSON)
                body = commentJSON['comment']
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

            try:
                newComment = Comments.createDocument({"post_id": commentJSON['post_id'],
                                       "author_id": user['_id'],
                                       "body": body,
                                       "created_date": int(time.time()),
                                       "images": None})
                newComment.save()
            except Exception:
                newComment = None

            if newComment:
                return make_response(jsonify(newComment.getStore()), 201)
            else:
                return make_response(jsonify({'status': 'failed'}), 400)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif request.method == "PUT":
        app.logger.debug("Reached PUT in v1_comments")
        user = validate_firebase_token_return_user(request)

        if user and user != 'expired':
            app.logger.debug("decoded worked")
            
            commentID = request.args.get("commentID", default=None)
            if commentID is None:
                responseData = jsonify({'status': 'missing arg commentID'})
                return make_response(responseData, 400)
            
            try:
                commentJSON = request.get_json()
                app.logger.debug(commentJSON)
                body = commentJSON['comment']
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)
            
            thread = request.args.get("thread", default=False)
            if thread:
                try:
                    comment = Comments[commentID]
                except Exception:
                    return make_response(jsonify({'status': 'not found'}), 404)

                comment['thread'].append({'author': user['_id'],
                                          'body': body,
                                          'created_date': int(time.time())
                                          })
                comment.save()
                return make_response(jsonify({'author': user['_id'],
                                              'body': body,
                                            'created_date': int(time.time())
                                            }), 201)
            else:
                return make_response(jsonify({'status': 'not implemented'}), 200)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)


# need to handle empty feed
@apiView.route('/v1/feed', methods=['GET'])
def v1_feed():
    if request.method == "GET":
        app.logger.debug("Reached GET in v1_feed")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)

        start_time = request.args.get("startTime", default=1546300800)
        end_time = request.args.get("endTime", default=int(datetime.utcnow().timestamp()))
        limit = request.args.get("limit", default=10)

        if user and user != 'expired':
            feed_data = get_feed(user, start_time, end_time, limit)
            data = jsonify({"posts": feed_data})
            app.logger.debug(data)
            return make_response(data, 200)
        elif user == 'expired':
            app.logger.debug('expired')
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            app.logger.debug('some other issue?')
            app.logger.debug(user)
            return make_response(jsonify({'status': 'failed'}), 401)
    else:
        return make_response(jsonify({'status': 'failed'}), 400)


@apiView.route('/v1/requests', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_requests():
    global Requests
    app.logger.debug("Reached v1_requests")
    user = validate_firebase_token_return_user(request)

    if user is None or user == 'expired':
        return make_response(jsonify({'status': 'failed'}), 401)
    
    requestType = request.args.get("type", default=None)
    
    if request.method == "GET":
        responseData = jsonify({'status': 'ok'})
        return make_response(responseData, 200)
    elif request.method == "POST":
        if requestType == "friend":
            q_email = request.args.get("email", default=None)
            
            if q_email:
                q_user = get_user(q_email)
            else:
                return make_response(jsonify({'status': 'failed'}), 400)
            
            visibility = getVisibility(user, q_user)
            if visibility is 'friends' or visibility is 'self':
                return make_response(jsonify({'status': 'conflict'}), 409)
            
            newRequest = Requests.createDocument({"requestor": user['_id'],
                                                  "requested": q_user['id'],
                                                  "created_date": int(time.time()),
                                                  "type": "friend"})
            newRequest.save()
            responseData = jsonify({'status': 'ok'})
            return make_response(responseData, 201)
        else:
            responseData = jsonify({'status': 'type not supported'})
            return make_response(responseData, 400)
    else:
        responseData = jsonify({'status': 'method not supported'})
        return make_response(responseData, 400)

#
# Need to add delete method
# Need to update POST method.  When friend option is given a friend request
# should be created.
# Need a PUT method that updates a friend request (confirms or deletes)
@apiView.route('/v1/friends', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_friends():
    app.logger.debug("Reached v1_friends")
    user = validate_firebase_token_return_user(request)

    if user is None or user == 'expired':
        return make_response(jsonify({'status': 'failed'}), 401)

    q_email = request.args.get("email", default=None)
    q_friend = request.args.get("friend", default=False)

    if q_email:
        q_user = get_user(q_email)
    else:
        return make_response(jsonify({'status': 'failed'}), 400)

    if request.method == "GET":
        visibility = getVisibility(user, q_user)
        if visibility is 'friends' or visibility is 'self':
            limit = int(request.args.get("limit", default=10))
            page = int(request.args.get("page", default=1))
            data = listFriends(user=q_user, limit=limit, page=page)
            return make_response(jsonify(data), 200)
        else:
            responseData = jsonify({'status': 'unauthorized'})
            return make_response(responseData, 401)
    elif request.method == "POST":
        #newFollower = addFollowers(follower=user, following=q_user)

        #if q_friend == 'true':
            #newFriend = addFollowers(follower=q_user, following=user)
        

        return make_response(jsonify({'status': 'ok'}), 200)
    elif request.method == "PUT":
        return make_response(jsonify({'status': 'ok'}), 200)
    elif request.method == "DELETE":
        return make_response(jsonify({'status': 'ok'}), 200)
    else:
        return make_response(jsonify({'status': 'ok'}), 200)


#
# Need a way to NOT hard code the image bucket
# Need a put method to add/remove tags
@apiView.route('/v1/images', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_images():
    global Images

    if request.method == "GET":
        return "images"
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_images")
        user = validate_firebase_token_return_user(request)
        if user and user != 'expired':
            #bucket = 'onestoop-ussouth'
            #bucket = 'mcontent'
            bucket = "onestoop00001"

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
                key = upload_file_to_cos(imgFile, bucket, user)
                uid = key.split('.')

                if key:
                    #image = ImageObj(user_id=user['_id'],
                                     #image_uid=uid[0],
                                     #bucket=bucket,
                                     #key=key,
                                     #Images=Images
                                     #)
                    #image.publish()
                    newImage = Images.createDocument()
                    data = {'user_id': user['_id'],
                            'created_date': int(datetime.utcnow().timestamp()),
                            'bucket': bucket,
                            'key': key,
                            'tags': None}
        
                    for k,v in data.items():
                      newImage[k] = v
        
                    newImage.save()
        
                    url = botoSession.generate_presigned_url(ClientMethod="get_object",
                                                             Params={'Bucket': bucket,
                                                                    'Key': key},
                                                             ExpiresIn=86400)
                    imagePath = url
                    responseData = jsonify({'status': 'success',
                                            'imageID': newImage._key,
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
        user = validate_firebase_token_return_user(request)
        if user and user != 'expired':
            app.logger.debug("got user")
            #fileName = request.args.get("fileName", default=None)
            #app.logger.debug("filename")
            #app.logger.debug(fileName)
            #if fileName is None:
                #responseData = jsonify({'status': 'missing fileName param'})
                #return make_response(responseData, 400)

            key = request.args.get("key", default=None)
            if key is None:
                responseData = jsonify({'status': 'missing key param'})
                return make_response(responseData, 400)
            #key = fileName.split('.')
            app.logger.debug("key")
            app.logger.debug(key)
            #image = ImageObj(image_uid=key[0]).get()
            try:
                image = Images[key]
                post = Posts.fetchFirstExample({"_key": key, "author_id": user["_id"]})
            except Exception:
                responseData = jsonify({'status': 'image not found'})
                return make_response(responseData, 404)
            #post_uid = request.args.get("postID", default=None)
            #postUidSplit = post_uid.split('/')
            
            #try:
                #p =  Posts[postUidSplit[1]].getStore()
            #except Exception:
                #p = None
                #return make_response(jsonify({'status': 'Not Found'}), 404)
            app.logger.debug("image")
            app.logger.debug(image)
            if image is None:
                app.logger.debug("image was None")
                responseData = jsonify({'status': 'image not found'})
                return make_response(responseData, 404)

            app.logger.debug("trying to delete from cos")
            d = delete_file_from_cos(image.bucket, image.key)
            if d:
                image.delete()
                return make_response(jsonify({'status': 'success'}), 200)
            else:
                return make_response(jsonify({'status': 'failed'}), 400)
        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)


#
# Need a way to NOT hard code the image bucket
# Need to support tags
@apiView.route('/v1/posts', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_posts():
    global Posts
    if request.method == "GET":
        app.logger.debug("Reached GET in v1_post")
        user = validate_firebase_token_return_user(request)
        if user and user != 'expired':
            post_uid = request.args.get("postID", default=None)
            postUidSplit = post_uid.split('/')
            
            try:
                p =  Posts[postUidSplit[1]].getStore()
            except Exception:
                p = None
                return make_response(jsonify({'status': 'Not Found'}), 404)
            
            q_user = get_user_by_uuid(p['users_uid'])
            visibility = getVisibility(user, q_user)
            if visibility == "friends" or visibility == "self":
                post = p
            elif visibility == "following" and p.visibility == "followers" or p.visibility == "public":
                post = p
            elif p.visibility == "public":
                post = p
            else:
                post = {}
            
            return make_response(jsonify(post), 200)
        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_post")
        user = validate_firebase_token_return_user(request)

        if user and user != 'expired':
            app.logger.debug("decoded worked")
            try:
                postJSON = request.get_json()
                app.logger.debug(postJSON)
                data = postJSON['post']
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

            images = postJSON.get('images')
            if images is None:
                images = []
            else:
                imagesDict = []
                images_uids = []
                for i in images:
                    uid = i['key'].split('.')
                    imagesDict.append({'bucket': i['bucket'], 'key': i['key'], 'image_uid': uid[0]})
                    images_uids.append(uid[0])
            app.logger.debug(images)
            visibility = postJSON.get('visibility')
            if visibility is None:
                visibility = 'friends'

            comments = []
            comments_uids = []

            try:
                newPost = Posts.createDocument({"created_date": int(time.time()),
                                                "body": data,
                                                "author_id": user['_id'],
                                                "images": imagesDict,
                                                "comments": comments,
                                                "visibility": visibility})
                newPost.save()
            except Exception:
                return make_response(jsonify({'status': 'failed'}), 400)

            app.logger.debug('newPost')
            app.logger.debug(newPost)
            return make_response(jsonify(newPost.getStore()), 201)
        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif request.method == "PUT":
        app.logger.debug("Reached PUT in v1_post")
        user = validate_firebase_token_return_user(request)

        if user and user != 'expired':
            postID = request.args.get("postID", default=None)
            if postID is None:
                responseData = jsonify({'status': 'missing arg postID'})
                return make_response(responseData, 400)

            postUidSplit = postID.split('/')
            
            try:
                post =  Posts[postUidSplit[1]]
            except Exception:
                post = None
                return make_response(jsonify({'status': 'Not Found'}), 404)

            if post is None:
                responseData = jsonify({'status': 'not found'})
                return make_response(responseData, 404)

            reaction = request.args.get("reaction", default=None)
            if reaction:
                try:
                    reactionData = request.get_json()
                except Exception:
                    return make_response(jsonify({'status': 'fail'}), 400)
                
                if 'reactions' not in post.getStore().keys():
                    post['reactions'] = []

                post['reactions'].append({'reactor': user['_id'], 'type': reactionData['type']})
                try:
                    post.save()
                except Exception:
                    return make_response(jsonify({'status': 'fail'}), 400)
                return make_response(jsonify(post.getStore()), 200)

            if post['author_id'] != user['_id']:
                responseData = jsonify({'status': 'unauthorized'})
                return make_response(responseData, 401)

            try:
                postJSON = request.get_json()
                app.logger.debug('inbound JSON')
                app.logger.debug(postJSON)
                data = postJSON['post']
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

            post['body'] = data
            post['visibility'] = postJSON['visibility']

            newImages = postJSON.get('newImages')
            if newImages is None:
                newImages = []

            removeImages = postJSON.get('removeImages')
            if removeImages is None:
                removeImages = []

            # setup images
            images = post['images']
            newImagesList = []
            #for img in removeImages:
                #uid = img.split('.')
                #try:
                    #post.images_uids.remove(uuid.UUID(uid[0]))
                #except Exception:
                    #pass

                #tmp = [i for i in images if not (i['key'] == img)]
                #images = tmp

            #for img in newImages:
                #images.append()
                #uid = img.split('.')
                #images.append({'bucket': 'onestoop-ussouth', 'key': img, 'image_uid': uid[0]})
                #post.images_uids.append(uid[0])

            #post.images = images
            #post.publish()
            post.save()

            app.logger.debug(post.getStore())
            return make_response(jsonify(post.getStore()), 200)
        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    elif request.method == "DELETE":
        app.logger.debug("Reached DELETE in v1_post")
        user = validate_firebase_token_return_user(request)

        if user and user != 'expired':
            app.logger.debug("decoded worked")
            postID = request.args.get("postID", default=None)

            if postID is None:
                responseData = jsonify({'status': 'missing arg postID'})
                return make_response(responseData, 400)
            else:
                post = Posts.fetchFirstExample({"_id": postID, "author_id": user["_id"]})
                app.logger.debug("this is post")
                app.logger.debug(post)

                if post is None:
                    return make_response(jsonify({'status': 'not found'}), 400)

                if post[0]['author_id'] != user['_id']:
                    return make_response(jsonify({'status': 'failed'}), 401)
                else:
                    comments = Comments.fetchByExample({"post_id": post[0]['_id']}, 1)
                    for comment in comments:
                        app.logger.debug("deleted comment " + comment["_id"])
                        comment.delete()

                    post[0].delete()
                    return make_response(jsonify({'status': 'success'}), 200)

        elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)


# Need a tag search
@apiView.route('/v1/search', methods=['GET'])
def v1_search():
    global db
    app.logger.debug("Reached search in v1_search")
    user = validate_firebase_token_return_user(request)

    q_email = request.args.get("email", default=None)
    q_name = request.args.get("name", default=None)
    q = request.args.get("q", default=None)
    limit = request.args.get("limit", default=10)

    if user and user != 'expired':
        app.logger.debug("user not expired")
        if q_email:
            app.logger.debug("Starting email search")
            aql = 'FOR u in Users FILTER u.email LIKE "' + q_email + '%" LIMIT ' + str(limit) + ' return u '
            q = db.AQLQuery(aql, rawResults=True, batchSize=100)
            options = []
            for i in q:
                options.append(i)
            app.logger.debug("here are your options!!!!!!!!!!!!")
            app.logger.debug(options)
        elif q_name:
            app.logger.debug("Starting name search")
            aql = 'FOR u in Users FILTER u.name LIKE "' + q_name + '%" LIMIT ' + str(limit) + ' return u '
            q = db.AQLQuery(aql, rawResults=True, batchSize=100)
            options = []
            for i in q:
                options.append(i)
            app.logger.debug("here are your options!!!!!!!!!!!!")
            app.logger.debug(options)
        elif q:
            app.logger.debug("Starting q search")
            options = []
            #if len(options) < limit:
            aql = 'FOR u in Users FILTER u.email LIKE "' + q + '%" OR u.name LIKE "' + q + '%" LIMIT ' + str(limit) + ' return u '
            q = db.AQLQuery(aql, rawResults=True, batchSize=100)
            app.logger.debug('here is q!!!!!!!!!!')
            app.logger.debug(q)
            #for i in q:
            for i in range(len(q)):
                options.append(q[i])
            app.logger.debug("here are your options!!!!!!!!!!!!")
            app.logger.debug(options)
        else:
            options = []
        app.logger.debug("here is json data")
        app.logger.debug(jsonify({'opitons': options}))
        return make_response(jsonify({'opitons': options}), 200)
    elif user == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
    else:
        return make_response(jsonify({'status': 'failed'}), 401)


@apiView.route('/v1/status', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_status():
    return make_response(jsonify({'status': 'up'}), 200)


@apiView.route('/v1/timeline', methods=['GET'])
def v1_timeline():
    global db
    if request.method == "GET":
        app.logger.debug("Reached GET in v1_timeline")
        user = validate_firebase_token_return_user(request)
        if user and user != 'expired':
            start_time = request.args.get("startTime", default=1546300800)
            end_time = int(request.args.get("endTime", default=int(datetime.utcnow().timestamp())))
            limit = int(request.args.get("limit", default=10))
            q_userString = request.args.get("email", default=None)
            q_user = get_user(q_userString)

            visibility = getVisibility(user, q_user)

            posts = TimelineJSON(user_id=q_user['_id'],
                             visibility=visibility,
                             start_time=start_time,
                             end_time=end_time,
                             limit=limit,
                             db=db
                             )

            return make_response(posts, 200)
        else:
            return make_response(jsonify({'status': 'expired'}), 401)
    else:
        return make_response(jsonify({'status': 'not supported'}), 200)


#
# Need a delete method that cleans up all data
# Need a put method to update user
@apiView.route('/v1/users', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_users():
    global Users

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_user")
        app.logger.debug(request.headers)

        displayName = request.args.get("displayName", default=None)
        q_id = request.args.get("userId", default=None)
        q_email = request.args.get("email", default=None)

        if displayName and q_id:
            user = get_user_by_id(q_id)
            if user and 'displayName' in user.getStore().keys():
                responseData = {'status': 'ok', 'user': {"displayName": user.displayName}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 200)
            elif user:
                responseData = {'status': 'ok', 'user': {"displayName": ''}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 200)
            else:
                responseData = {'status': 'not found', 'user': {"displayName": ''}}
                app.logger.debug(responseData)
                return make_response(jsonify(responseData), 404)
                
        user = validate_firebase_token_return_user(request)
        if user and user != 'expired':
            if q_email is None:
                return make_response(jsonify({'status': 'not found'}), 404)
            else:
                q_user = get_user(q_email)
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
            email = decoded_token['email']
            uid = decoded_token['uid']
            name = request.args.get('name') or None

            user = add_user(email,
                            uid,
                            name)

            return make_response(jsonify({'status': 'ok'}), 200)

            if user:
                return make_response(jsonify({'status': 'ok'}), 201)
            else:
                return make_response(jsonify({'status': 'failed'}), 400)
        elif decoded_token == 'expired':
            return make_response(jsonify({'status': 'expired'}), 401)
        else:
            return make_response(jsonify({'status': 'failed'}), 401)
    else:
        return make_response(jsonify({'status': 'failed'}), 400)



###########################
def loadRecipe(r, recipes):
    app.logger.debug("doign loadRecipe")
    images = []
    for iNum, imageID in enumerate(r['images']):
        try:
            image = Images[imageID]
        except:
            pass
        image = get_image_url(image)
        images.append(image)
        r['images'] = images
    rId = r['_id'].split('/')
    r['_id'] = rId[1]
    recipes['recipes'].append(r)
    return recipes

    
@apiView.route('/v1/recipes', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes():
    global Recipes
    global db
    global cookingDB
    global Images

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes")
        app.logger.debug(request.url)
        app.logger.debug(request.headers)

        user = validate_firebase_token_return_user(request)

        authorEmail = request.args.get("author", default=None)
        recipeType = request.args.get("recipeType", default=None)
        term = request.args.get("term", default=None)

        limit = request.args.get("limit", default=10)
        nextOffset = request.args.get("nextOffset", default=0)
        
        if authorEmail:
            q_user = get_user(authorEmail)
        else:
            q_user = None
        
        if int(limit) > 100:
            limit = 100
        
        
        app.logger.debug("building aql")
        aql = 'FOR r in Recipes FILTER '
        
        if user == None or user == 'expired':
            aql += 'r.visibility != "private" FILTER '

        if q_user:
            app.logger.debug("doing recipeId or q_user")
            aql += 'r.authorId == "' + q_user['_id'] + '"'
    
        if term:
            term = term.lower()
            aql += 'LOWER(r.title) LIKE "%' + term \
                + '%" OR LOWER(r.description) LIKE "%' + term \
                + '%" OR LOWER(r.ingredients[*].item) LIKE "%' + term \
                + '%" OR LOWER(r.recipeType) LIKE "%' + term \
                + '%" OR LOWER(r.cusine) LIKE "%' + term + '%" '

        elif recipeType:
            recipeType = recipeType.lower()
            aql += 'r.recipeType == "' + recipeType + '" '
            
        aql += 'sort r.created_date DESC LIMIT ' + str(nextOffset) \
            + ', ' + str(limit) + ' RETURN r'
        
        app.logger.debug("this is aql")
        app.logger.debug(aql)
        
        try:
            r = cookingDB.AQLQuery(aql, rawResults=True, batchSize=100)
            q = r.response['result']
        except:
            q = []
    
        app.logger.debug("this is q")
        app.logger.debug(q)
        recipes = {"recipes": []}
        
        if len(q) < int(limit):
            recipes['nextOffset'] = int(nextOffset)
            recipes['moreResults'] = False
        else:
            recipes['nextOffset'] = int(nextOffset) + int(limit)
            recipes['moreResults'] = True
            
        for rNum, r in enumerate(q):
            
            if r['visibility'] == 'private':
                if user == None or user == 'expired':
                  pass
                elif r['authorId'] != user['_id']:
                  pass
                else:
                    recipes = loadRecipe(r, recipes)
            else:
                recipes = loadRecipe(r, recipes)
                    
        
        app.logger.debug(recipes)
        return make_response(jsonify(recipes), 200)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)

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
            
            data['authorId'] = user['_id']
            data['bookmarked'] = 0
            data['rating'] = 0
            data['ratingCount'] = 0
            data['shares'] = 0
            data['visibility'] = data['visibility'].lower()
            data['cusine'] = data['cusine'].lower()
            data['recipeType'] = data['recipeType'].lower()
            data['recipeSubType'] = data['recipeSubType'].lower()
            data["created_date"] = int(time.time())
            
            try:
                newRecipe = Recipes.createDocument(data)
                newRecipe.save()
            except Exception:
                return make_response(jsonify({'status': 'fail'}), 400)

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

@apiView.route('/v1/recipes/<recipeId>', methods=['GET', 'PATCH', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id(recipeId):
    global Recipes
    global db
    global cookingDB
    global Images

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)
        
        if '/' in recipeId:
            r = recipeId.split('/')
            recipeId = r[1]
        
        try:
            recipe = Recipes[recipeId]
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)
        
        if recipe['visibility'] == 'private':
            if user == None or user == 'expired':
                return make_response(jsonify({'status': 'not found'}), 401)
            if user['_id'] != recipe['authorId']:
                return make_response(jsonify({'status': 'not found'}), 401)
        
        recipes = {"recipes": []}
        recipes = loadRecipe(recipe.getStore(), recipes)
        
        return make_response(jsonify(recipes),200)
    elif request.method == "PATCH":
        app.logger.debug("Reached PATCH in v1_recipes_id")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)
        
        if '/' in recipeId:
            r = recipeId.split('/')
            recipeId = r[1]
        
        try:
            recipe = Recipes[recipeId]
        except Exception:
            return make_response(jsonify({'status': 'not found'}), 404)
        
        if user['_id'] != recipe.authorId:
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
        
        try:
            recipe.save()
        except Exception:
            return make_response(jsonify({'status': 'database error'}), 500)
        
        return make_response(jsonify({'status': 'ok'}), 200) 

    elif request.method == "POST":
        return
    elif request.method == "PUT":
        return
    elif request.method == "DELETE":
        return
    else:
        return

@apiView.route('/v1/recipes/<recipeId>/reviews', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id_reviews(recipeId):
    global Recipes
    global db
    global cookingDB
    global Reviews
    global Users
    
    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id_reviews")
        
        limit = request.args.get("limit", default=10)
        offset = request.args.get("offset", default=0)
        
        aql = 'FOR r in Reviews FILTER r.recipeId == "' + recipeId + '" ' \
            ' sort r.created_date DESC LIMIT ' + str(offset) \
            + ', ' + str(limit) + ' RETURN r'
        
        aqlCount = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT WITH COUNT INTO length RETURN length'

        app.logger.debug(aql)
        try:
            r = cookingDB.AQLQuery(aql, rawResults=True, batchSize=100)
            c = cookingDB.AQLQuery(aqlCount, rawResults=True, batchSize=100)
            q = r.response['result']
            count = c.response['result'][0]
        except:
            q = []
            
        reviews = {'reviews': q}
        reviews['total'] = count

        if len(q) < int(limit):
            reviews['nextOffset'] = int(offset)
            reviews['moreResults'] = False
        else:
            reviews['nextOffset'] = int(offset) + int(limit)
            reviews['moreResults'] = True
            
        for i, review in enumerate(reviews['reviews']):
            app.logger.debug(review['authorId'])
            u = Users[review['authorId'].split('/')[1]]
            reviews['reviews'][i]['authorId'] = u.displayName
        
        app.logger.debug(reviews)
        return make_response(jsonify(reviews), 200)
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes_id_reviews")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)

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
        
        data['authorId'] = user['_id']
        data["created_date"] = int(time.time())
        data["recipeId"] = recipeId
        
        try:
            newReview = Reviews.createDocument(data)
            newReview.save()
        except Exception:
            return make_response(jsonify({'status': 'fail'}), 400)
        
        #update the recipe with Metadata
        try:
            aqlScore = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT AGGREGATE score = AVG(doc.score) RETURN score'
            aqlCount = 'FOR doc in Reviews FILTER doc.recipeId == "' + recipeId + '" COLLECT WITH COUNT INTO length RETURN length'
            s = cookingDB.AQLQuery(aqlScore, rawResults=True)
            c = cookingDB.AQLQuery(aqlCount, rawResults=True)
            score = round(s.response['result'][0],2)
            count = c.response['result'][0]
            recipe = Recipes[recipeId]
            recipe['rating'] = score
            recipe['ratingCount'] = count
            recipe.save()
        except Exception:
            pass

        return make_response(jsonify({"reviews": [newReview.getStore()]}), 200)
    elif request.method == "PUT":
        return
    elif request.method == "DELETE":
        return
    else:
        return


@apiView.route('/v1/recipes/<recipeId>/bookmarks', methods=['GET', 'POST', 'PUT', 'DELETE'])
def v1_recipes_id_bookmarks(recipeId):
    global Recipes
    global db
    global cookingDB
    global Users

    if request.method == "GET":
        app.logger.debug("Reached GET in v1_recipes_id_bookmarks")
        return
    elif request.method == "POST":
        app.logger.debug("Reached POST in v1_recipes_id_bookmarks")
        app.logger.debug(request.headers)
        user = validate_firebase_token_return_user(request)

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
    
