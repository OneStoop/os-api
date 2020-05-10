import json
import uuid
from datetime import datetime
#from ...models import Images_by_user, Images_by_uuid

class Image:
    def __init__(self,
                 user_id=None,
                 image_uid=uuid.uuid4(),
                 created_date=int(datetime.utcnow().timestamp()),
                 bucket=None,
                 key=None,
                 tags=None,
                 Images=None):
        
        self.user_id = user_id
        self.image_uid = image_uid
        self.created_date=created_date
        self.bucket=bucket
        self.key = key
        self.tags = tags
        self.Images = Images
        
        
    def publish(self):
        newImage = self.Images.createDocument()
        data = {'user_id': self.user_id,
                'created_date': self.created_date,
                'bucket': self.bucket,
                'key': self.key,
                'tags': self.tags}
        
        for k,v in data.items():
            newImage[k] = v
        
        newImage.save()
        #newImage = Images_by_user(user_uid = self.user_uid,
                                  #image_uid = self.image_uid,
                                  #created_date = self.created_date,
                                  #bucket = self.bucket,
                                  #key = self.key,
                                  #tags = self.tags)
        #newImage.save()
        #newImageUuid = Images_by_uuid(user_uid = self.user_uid,
                                      #image_uid = self.image_uid,
                                      #created_date = self.created_date,
                                      #bucket = self.bucket,
                                      #key = self.key,
                                      #tags = self.tags)
        #newImageUuid.save()
        return 'done'
    
    
    def delete(self):
        query1 = Images_by_user.objects(user_uid=self.user_uid, image_uid=self.image_uid).first()
        query1.delete()

        query2 = Images_by_uuid.objects(image_uid=self.image_uid, user_uid=self.user_uid).first()
        query2.delete()
        
        return 'done'
    
    
    def get(self):
        try:
            query = Images_by_uuid.objects(image_uid=self.image_uid).first()
            return Image(user_uid=query.user_uid,
                         image_uid=query.image_uid,
                         created_date=query.created_date,
                         bucket=query.bucket,
                         key=query.key,
                         tags=query.tags)
        except Exception:
            return None
