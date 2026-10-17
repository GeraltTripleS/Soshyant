import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error

from expert.cloud import CloudClient,CloudProfiles,NoRedirect,protect
from expert.config import Config,ROOT
from expert.model import LocalModel


class ProviderStub:
    def __init__(self):self.requests=[];self.error=None;self.finish='stop';self.content=None
    def open(self,request,timeout=0):
        self.requests.append(request)
        if self.error:raise self.error
        messages=json.loads(request.data)['messages']
        grounded=any('REFERENCE PASSAGES' in row['content'] for row in messages)
        result={'status':'answered','answer':'The warranty is 36 months. [1]','citations':[1]} if grounded else {
            'status':'insufficient','answer':'Connection verified','citations':[]}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':self.finish,'message':{'content':self.content or json.dumps(result)}}]}).encode())


class CloudTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        (self.root/'config').mkdir()
        (self.root/'config/server.json').write_bytes((ROOT/'config/server.json').read_bytes())
        self.config=Config(self.root);self.profiles=CloudProfiles(self.config)
        self.data={'name':'Test API','provider':'openai','model':'test-model','api_key':'test-only-never-real-secret'}
        self.profile=self.profiles.add(self.data)
        self.client=CloudClient(self.config);self.provider=ProviderStub();self.client.opener=self.provider

    def test_secret_roundtrip_and_never_returned_or_plaintext(self):
        self.assertEqual(protect(protect(self.data['api_key']),True),self.data['api_key'])
        self.assertNotIn(self.data['api_key'],self.profiles.path.read_text())
        self.assertNotIn('secret',self.profile)
        self.assertNotIn('api_key',self.profile)
        if os.name!='nt':self.assertEqual(self.profiles.path.stat().st_mode&0o777,0o600)

    def test_openai_schema_store_flag_and_token_budget(self):
        self.client.probe(self.profile['id'])
        request=self.provider.requests[0];payload=json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.openai.com/v1/chat/completions')
        self.assertEqual(request.get_header('Authorization'),'Bearer '+self.data['api_key'])
        self.assertFalse(payload['store']);self.assertFalse(payload['stream'])
        self.assertEqual(payload['response_format']['type'],'json_schema')
        self.assertIn('max_completion_tokens',payload)
        self.assertNotIn('temperature',payload)

    def test_compatible_json_mode_and_custom_endpoint(self):
        profile=self.profiles.add({**self.data,'provider':'compatible','base_url':'https://example.com/api/v1/','response_mode':'json_object'})
        self.client.probe(profile['id'])
        request=self.provider.requests[0];payload=json.loads(request.data)
        self.assertEqual(request.full_url,'https://example.com/api/v1/chat/completions')
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertIn('max_tokens',payload)

    def test_failures_are_sanitized_and_do_not_retry(self):
        self.provider.error=urllib.error.HTTPError('https://example.com',401,'secret echoed',{},io.BytesIO(self.data['api_key'].encode()))
        with self.assertRaises(RuntimeError) as raised:self.client.probe(self.profile['id'])
        self.assertIn('401',str(raised.exception));self.assertNotIn(self.data['api_key'],str(raised.exception))
        self.assertEqual(len(self.provider.requests),1)
        self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_incomplete_and_malformed_response_and_cancellation(self):
        self.provider.finish='length'
        with self.assertRaises(RuntimeError):self.client.probe(self.profile['id'])
        self.provider.finish='stop';self.provider.content='not JSON'
        with self.assertRaises(RuntimeError):self.client.probe(self.profile['id'])
        count=len(self.provider.requests)
        with self.assertRaises(InterruptedError):self.client.generate(self.profile['id'],[],lambda:True)
        self.assertEqual(len(self.provider.requests),count)

    def test_validation_rejects_unsafe_urls_and_malformed_keys(self):
        for override in ({'provider':'other'},{'provider':'compatible','base_url':'http://example.com/v1'},
            {'provider':'compatible','base_url':'https://user:pass@example.com/v1'},
            {'provider':'compatible','base_url':'https://example.com/v1?key=secret'},
            {'api_key':'bad\nkey-value'},{'model':'bad model'},{'response_mode':'text'}):
            with self.subTest(override=override),self.assertRaises(ValueError):self.profiles.add({**self.data,**override})

    def test_router_uses_only_explicitly_selected_cloud_profile(self):
        router=LocalModel(self.config);router.cloud.opener=self.provider
        self.assertEqual(self.provider.requests,[])
        self.config.settings['cloud_model_id']=self.profile['id']
        self.assertTrue(router.available());router.ensure()
        self.assertEqual(router.state,'ready')
        self.assertEqual(len(self.provider.requests),1)
