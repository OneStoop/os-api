from datetime import datetime
import math
from ...models import Following, Followers, Friends, FriendRequest_by_user, FriendRequest_by_requester, Alerts_by_user
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

def listFriends(user, limit=10, page=1):
    start = (limit * page) - limit
    end = limit * page
    try:
        query = Friends.objects(user_uid=user.uid).first()
        data = {'total': len(query.friends), 'total_pages': math.ceil(len(query.friends)/limit), 'limit': limit, 'page': page, 'friends': query.friends[start:end]}
    except Exception:
        data = {'total': 0, 'total_pages': 0, 'limit': limit, 'friends': []}
    
    if query is None:
        return {'total': 0, 'total_pages': 0, 'limit': limit, 'friends': []}

    return data


def addFriend(user, friend):
    friend_dict = {'user_uid': friend.uid, 'name':friend.name, 'email': friend.email}
    try:
        f = Friends.objects(user_uid=user.uid).first()
    except Exception:
        f = None
    
    if f:
        existing = next(( item for item in f.friends if item['user_uid'] == friend.uid), None)
        if existing is None:
            f.friends += [friend_dict]
    else:
        f = Friends(user_uid=user.uid, friends = [friend_dict])
    f.save()
    
    return f

def removeFriend(user, friend):
    try:
        f = Friends.objects(user_uid=user.uid).first()
    except Exception:
        f = None
    
    if f:
        for i in range(len(f.friends)):
            if f.friends[i]['user_uid'] == friend.uid:
                del f.friends
                f.save()
                break
    return f
