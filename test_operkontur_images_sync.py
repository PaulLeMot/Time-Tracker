import hashlib,json,tempfile,time,unittest
from pathlib import Path
from operkontur_images_sync import authenticate,signature,parse,eligible,changes,available_codes,SyncError,parse_inventory

class ImageSyncTests(unittest.TestCase):
    def row(self):return {'code':'00123','product_type':'SYN type','fandom':None,'name':'SYN product','sha256':hashlib.sha256(b'\xff\xd8SYN').hexdigest()}
    def body(self):return json.dumps({'version':1,'job_id':'a'*32,'products':[self.row()]}).encode()
    def test_inventory_allows_only_unique_five_digit_codes(self):
        self.assertEqual(parse_inventory(b'{"codes":["00123","00456"]}'),['00123','00456'])
        for body in (b'{}',b'{"codes":["00123","00123"]}',b'{"codes":[12345]}',b'{"codes":["../12"]}',b'{"codes":[],"extra":1}',b'null',b'{"codes":[{}]}'):
            with self.assertRaises(SyncError):parse_inventory(body)
    def test_signed_payload_tamper_wrong_key_and_expiry(self):
        key=b'SYN'*16;body=self.body();stamp=str(int(time.time()));proof=signature(key,stamp,body)
        authenticate(key,stamp,proof,body)
        for secret,content,clock in [(b'bad'*16,body,None),(key,body+b' ',None),(key,body,int(stamp)+121)]:
            with self.assertRaises(SyncError):authenticate(secret,stamp,proof,content,clock)
    def test_validation_rejects_duplicates_path_in_code_and_unknown_fields(self):
        self.assertEqual(parse(self.body())['products'][0]['code'],'00123')
        for rows in [[self.row(),self.row()],[{**self.row(),'code':'../12'}],[{**self.row(),'sql':'SYN'}],[{**self.row(),'name':''}],[{**self.row(),'product_type':''}]]:
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
    def test_full_refresh_adds_missing_without_changing_existing_metadata(self):
        row={k:v for k,v in self.row().items() if k!='sha256'}
        old={**row,'name':'SYN existing name'}
        self.assertEqual(changes([row],{'00123':old},'missing_only'),({'added':0,'updated':0,'unchanged':1},[]))
        self.assertEqual(old['name'],'SYN existing name')
        value=json.loads(self.body());value['mode']='missing_only';self.assertEqual(parse(json.dumps(value).encode())['mode'],'missing_only')
    def test_availability_lists_only_ready_numeric_jpeg_names(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('00123.jpg','name.jpg','00123.png','.operkontur-images.json'):(root/name).write_bytes(b'SYN')
            (root/'00456.jpg').mkdir()
            self.assertEqual(available_codes(root),['00123'])

if __name__=='__main__':unittest.main()
