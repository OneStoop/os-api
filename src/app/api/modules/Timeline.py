import json
from datetime import datetime
#from ...helpers.get_signed_url import get_signed_url
from app import botoSession

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

def format_post(post, db):
    print(post)
    if type(post) == type({}):
        k = post['author_id'].split('/')
        key = k[1]
        author = db['Users'][key]
    
        if "reactions" not in post.keys():
            post["reactions"] = []
    
        thisPost = {"id": str(post["_id"]),
                    "body": post["body"],
                    "author_id": str(post["author_id"]),
                    "email": author['email'],
                    "name": author['name'],
                    "created_date": post["created_date"],
                    "images": [],
                    "comments": [],
                    "reactions": post['reactions'],
                    "visibility": post["visibility"]
                    }
  
        smiles = sum(x.get('type') == 'smile' for x in thisPost['reactions'])
        thisPost['smiles'] = smiles
    
        hearts = sum(x.get('type') == 'heart' for x in thisPost['reactions'])
        thisPost['hearts'] = hearts
    
        laughs = sum(x.get('type') == 'laugh' for x in thisPost['reactions'])
        thisPost['laughs'] = laughs
    
        surprises = sum(x.get('type') == 'surprise' for x in thisPost['reactions'])
        thisPost['surprises'] = surprises
    
        sads = sum(x.get('type') == 'sad' for x in thisPost['reactions'])
        thisPost['sads'] = sads
    
        angrys = sum(x.get('type') == 'angry' for x in thisPost['reactions'])
        thisPost['angrys'] = angrys
    
        for i in post["images"]:
            image = objdict(i)

            url = botoSession.generate_presigned_url(ClientMethod="get_object",
                                                     Params={'Bucket': image.bucket,
                                                             'Key': image.key},
                                                     ExpiresIn=86400)
            print(url)
            imagePath = url
            thisPost['images'].append({'url': imagePath,
                                       'id': str(image.image_uid),
                                       'key': image.key
                                      })
  
        comments = db['Comments'].fetchByExample({'post_id': post['_id']}, batchSize=100)
        for c in comments:
            comment = objdict(c.getStore())
            author = db['Users'][comment.author_id.split('/')[1]]
            if 'thread' not in comment.keys():
                comment['thread'] = []

            data = {'id': comment._id,
                    'post_id': str(post["_id"]),
                    'author_id': comment.author_id,
                    'authorEmail': author['email'],
                    'authorName': author['name'],
                    'body': comment.body,
                    'created_date': comment.created_date,
                    'images': comment.images,
                    'thread': comment.thread
                    }
  
            thisPost['comments'].append(data)
        return thisPost


def TimelineJSON(user_id,
                 visibility,
                 start_time,
                 end_time,
                 limit=10,
                 db=None):
    
    aql = 'FOR p IN Posts Filter p.author_id == "' + user_id + '" sort ' \
        'p.created_date ASC LIMIT 1 RETURN p'
    q = db.AQLQuery(aql, rawResults=True, batchSize=100)
    if len(q) == 1:
        oldestPost = q[0]
    else:
        oldestPost = None
    
    if oldestPost is None:
        return json.dumps({'posts': [], 'lastPost': False})
    
    if end_time <= oldestPost['created_date']:
        lastPost = True
    else:
        lastPost = False
    
    aql = 'FOR p IN Posts Filter p.created_date < ' + str(end_time) + ' AND ' \
        'p.created_date > ' + str(start_time) + ' FILTER p.author_id == "' + user_id + '" sort ' \
        'p.created_date DESC LIMIT ' + str(limit) + ' RETURN p'
    q = db.AQLQuery(aql, rawResults=True, batchSize=100)
    
    if visibility == "friends" or visibility == "self":
        posts = q
    elif visibility == "following":
        posts = []
        for i in range(len(q)):
        #for post in q:
            post = q[i]
            if post['visibility'] == "followers" or post['visibility'] == "public":
                posts.append(post)
    else:
        print('must be public')
        posts = []
        #for post in q:
        for i in range(len(q)):
            post = q[i]
            if post['visibility'] == "public":
                posts.append(post)
    
    data = []
    #for post in posts:
    for i in range(len(posts)):
        post = posts[i]
        thisPost = format_post(post, db)
        data.append(thisPost)
    
    sorted_data = sorted(data, key=lambda k: k['created_date'], reverse=True)
    
    jsonData = json.dumps({'posts': sorted_data, 'lastPost': lastPost})
    
    return jsonData


def Feed(user_id,
         start_time,
         end_time,
         limit=10,
         db=None):
    print("start Feed")
    print(start_time)
    print(end_time)
    print(user_id)

    relations = db['Relations'].fetchByExample({'_from': user_id}, 10)
    aql = 'FOR p IN Posts Filter p.created_date < ' + str(end_time) + ' AND ' \
        'p.created_date > ' + str(start_time) + ' FILTER p.author_id == "' + user_id + '" sort ' \
        'p.created_date DESC LIMIT ' + str(limit) + ' RETURN p'
    q = db.AQLQuery(aql, rawResults=True, batchSize=100)

    data = []
    for i in range(len(q)):
        data.append(format_post(q[i], db))

    for following in relations:
        aql = 'FOR p IN Posts Filter p.created_date < ' + str(end_time) + ' AND ' \
            'p.created_date > ' + str(start_time) + ' FILTER p.author_id == "' + following["_to"] + '" sort ' \
            'p.created_date DESC LIMIT ' + str(limit) + ' RETURN p'
        q = db.AQLQuery(aql, rawResults=True, batchSize=100)
        print("this is q")
        print(q)
        for post in q:
            print(q)
            data.append(format_post(post, db))
    
    sorted_data = sorted(data, key=lambda k: k['created_date'], reverse=True)
    print("done Feed")
    return sorted_data
