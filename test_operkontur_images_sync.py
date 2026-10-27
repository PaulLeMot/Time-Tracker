import hashlib,json,tempfile,time,unittest
from pathlib import Path
from operkontur_images_sync import authenticate,signature,parse,eligible,changes,SyncError

class ImageSyncTests(unittest.TestCase):
    def row(self):return {'code':'00123','product_type':'SYN type','fandom':None,'name':'SYN product','sha256':hashlib.sha256(b'\xff\xd8SYN').hexdigest()}
    def body(self):return json.dumps({'version':1,'job_id':'a'*32,'products':[self.row()]}).encode()
    def test_signed_payload_tamper_wrong_key_and_expiry(self):
        key=b'SYN'*16;body=self.body();stamp=str(int(time.time()));proof=signature(key,stamp,body)
        authenticate(key,stamp,proof,body)
        for secret,content,clock in [(b'bad'*16,body,None),(key,body+b' ',None),(key,body,int(stamp)+121)]:
            with self.assertRaises(SyncError):authenticate(secret,stamp,proof,content,clock)
    def test_validation_rejects_duplicates_path_in_code_and_unknown_fields(self):
        self.assertEqual(parse(self.body())['products'][0]['code'],'00123')
        for rows in [[self.row(),self.row()],[{**self.row(),'code':'../12'}],[{**self.row(),'sql':'SYN'}],[{**self.row(),'name':''}]]:
            with self.assertRaises(SyncError):parse(json.dumps({'version':1,'job_id':'a'*32,'products':rows}).encode())
    def test_only_available_matching_jpeg_is_eligible(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'00123.jpg').write_bytes(b'\xff\xd8SYN')
            accepted,rejected=eligible([self.row()],root);self.assertEqual(len(accepted),1);self.assertEqual(rejected,[])
            for row in [{**self.row(),'sha256':'b'*64},{**self.row(),'code':'00456'}]:self.assertEqual(len(eligible([row],root)[1]),1)
            (root/'00123.jpg').write_bytes(b'SYN not JPEG');self.assertEqual(len(eligible([self.row()],root)[1]),1)
    def test_additive_update_preserves_unrelated_rows_and_repeat_is_unchanged(self):
        old={'code':'00999','product_type':'SYN other','fandom':None,'name':'SYN other'}
        row={k:v for k,v in self.row().items() if k!='sha256'};existing={'00999':old}
        count,changed=changes([row],existing);self.assertEqual(count,{'added':1,'updated':0,'unchanged':0});self.assertEqual(existing,{'00999':old})
        existing['00123']=row;self.assertEqual(changes([row],existing)[0]['unchanged'],1)
        self.assertEqual(changes([{**row,'name':'SYN updated'}],existing)[0]['updated'],1)

if __name__=='__main__':unittest.main()
