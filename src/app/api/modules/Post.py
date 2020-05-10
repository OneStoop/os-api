import json
import uuid
#from ...models import Followers, Posts_by_postid, Posts_by_user, Feeds_by_user
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


class Post:
    def __init__(self,
                 author_id=None,
                 post_uid=None,
                 body=None,
                 created_date=None,
                 comments_uids=None,
                 comments=None,
                 images_uids=None,
                 images=None,
                 visibility=None,
                 Posts=None):
        self.post_uid = str(post_uid)
        self.body = body
        self.author_id = author_id
        self.created_date = created_date
        self.comments = comments
        self.images = images
        self.visibility = visibility
        self.Posts = Posts
    
    
    def publish(self):
        print('Starting publish')
        newPost = self.Posts.createDocument()
        data = {'body': self.body,
                'author_id': self.author_id,
                'created_date': self.created_date,
                'images': self.images,
                'comments': self.comments,
                'visibility': self.visibility}
        
        for k,v in data.items():
            newPost[k] = v
        print(newPost)
        newPost.save()
        print('done publish')
        return 'done'
    
    def delete(self):
        followers = Followers.objects(user_uid=self.user_uid).first()
        post = Posts_by_postid.objects.filter(post_uid=self.post_uid).first()
        postU = Posts_by_user.objects.filter(user_uid=self.user_uid).filter(created_date=post.created_date).filter(post_uid=self.post_uid).first()
        postU.delete()
        if followers:
            for follower in followers.followers:
                ps = Feeds_by_user.objects.filter(user_uid=follower).filter(created_date=post.created_date).filter(author_uid=post.user_uid).first()
                ps.delete()
        ps = Feeds_by_user.objects.filter(user_uid=self.user_uid).filter(created_date=post.created_date).filter(post_uid=post.post_uid).first()
        ps.delete()
        post.delete()
        return 'done'
    
    
    def json(self):
        thisPost = {"id": str(self.post_uid),
                    "body": self.body,
                    "author_id": self.author_id,
                    "created_date": self.created_date,
                    "images": [],
                    "comments": [],
                    "visibility": self.visibility
                    }
    
        for i in self.images:
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
    
        for c in self.comments:
            comment = objdict(c)
    
            thisPost['comments'].append({"comment": comment.body,
                                         "userName": comment.author_name,
                                         "userID": comment.author_uid,
                                         "email": comment.author_email,
                                         "created_date": comment.created_date
                                         })
    
        return json.dumps(thisPost)
    
    
    def get(self):
        try:
            q = self.Posts[self.post_uid]
        except Exception:
            return None
        
        if q is None:
            return None

        p = objdict(q.getStore())

        #if self.visibility == "friends" or self.visibility == "self":
            #p = query
        #elif self.visibility == "following" and query.visibility == "followers" or query.visibility == "public":
            #p = query
        #elif query.visibility == "public":
            #p = query
        #else:
            #print('returning None')
            #p = None
            #return None

        post = Post(post_uid=p._key,
                    author_id=p.author_id,
                    body=p.body,
                    created_date=p.created_date,
                    comments=p.comments,
                    images=p.images,
                    visibility=p.visibility)
        return post
