import json
import uuid
#from ...models import Followers, Posts_by_postid, Posts_by_user, Feeds_by_user, Comments_by_postid, Comments_by_user
#from ...helpers.get_signed_url import get_signed_url

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

class Comment:
    def __init__(self,
                 comment_id=None,
                 post_id=None,
                 author_id=None,
                 body=None,
                 created_date=None,
                 images=[],
                 thread=None,
                 db=None):
        self.comment_id = comment_id
        self.post_id = post_id
        self.author_id = author_id
        self.body = body
        self.created_date = created_date
        self.images = images
        self.thread = thread
        self.db = db
    
    def publish(self):
        print('Starting Comments publish')
        newComment = self.db['Comments'].createDocument()

        data = {'post_id': self.post_id,
                'author_id': self.author_id,
                'body': self.body,
                'created_date': self.created_date,
                'images': self.images,
                thread: self.thread
                }
        
        for k,v in data.items():
            newComment[k] = v
        print(newComment)
        newComment.save()
        self.comment_id = newComment['_id']
        print('done Comments publish')
        return 'done'

    def delete(self):
        pass
    
    
    def json(self):
        author = self.db['Users'][self.author_id.split('/')[1]]
        data = {'id': self.comment_id,
                'author_id': self.author_id,
                'authorEmail': author['email'],
                'authorName': author['name'],
                'body': self.body,
                'created_date': self.created_date,
                'images': self.images,
                thread: self.thread
                }
        return json.dumps(data)
    
        
    def get(self):
        try:
            q = self.Posts[self.comment_id.split('/')[1]]
        except Exception:
            return None
        
        if query is None:
            return None
        
        author = self.db['Users'][query.author_id.split('/')[1]]
        comment = Comment(comment_uid=query.comment_uid,
                          post_id=query.post_id,
                          author_id=query.author_id,
                          user_name=author['name'],
                          user_email=author['email'],
                          body=query.body,
                          created_date=query.created_date,
                          images=query.images,
                          thread=query.thread)
        return comment

        
