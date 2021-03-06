import os
import os.path
import datetime
import tempfile
import urllib

from twisted.internet import reactor
from twisted.internet import defer
from twisted.internet import endpoints
from twisted.web import client as webclient
from twisted.web import http_headers
from twisted.web.iweb import IBodyProducer
from twisted.trial.unittest import TestCase as TrialTestCase
from zope.interface import implementer

from infobob.http import makeSite, DEFAULT_TEMPLATES_DIR
import infobob.tests.support as sp


class WebUITestCase(TrialTestCase):
    def setUp(self):
        self.client = webclient.Agent(reactor)

    @defer.inlineCallbacks
    def startWebUI(self, dbpool_fake):
        self.site = makeSite(DEFAULT_TEMPLATES_DIR, dbpool_fake)
        self.endpoint = endpoints.TCP4ServerEndpoint(reactor, 8888)
        self.listeningPort = yield self.endpoint.listen(self.site)
        self.addCleanup(self.listeningPort.stopListening)

    @defer.inlineCallbacks
    def _request(self, method, url_path, headers=None, bodyProducer=None):
        url = b'http://localhost:8888' + url_path
        res = yield self.client.request(method, url, headers, bodyProducer)
        content = yield webclient.readBody(res)
        defer.returnValue((res, content))

    def get(self, url_path):
        return self._request(b'GET', url_path)

    def post(self, url_path, dataMapping):
        headers = http_headers.Headers()
        headers.setRawHeaders(
            b'Content-Type',
            [b'application/x-www-form-urlencoded'],
        )
        bodyProducer = XWWWFormUrlencodedProducer(dataMapping)
        return self._request(b'POST', url_path, headers, bodyProducer)

    @defer.inlineCallbacks
    def test_bans_index_active_bans(self):
        bans = [
            (
                b'#project', b'$a:baduser', b'b',
                dt('2018-03-14T15:09:26'), b'someop!foo',
                dt('2018-03-21T15:09:26'), b'bad behavior', None, b'',
            ),
        ]
        dbpool = sp.FakeObj()
        dbpool.get_active_bans = sp.DeferredSequentialReturner([bans])
        yield self.startWebUI(dbpool)

        res, content = yield self.get(b'/bans')
        self.assertEqual(res.code, 200)
        self.assertIn(b'<table', content)
        self.assertIn(b'<td class="set-by">someop</td>', content)
        self.assertIn(b'$a:baduser</td>', content)
        # TODO: Test that other expected bits appear.
        # TODO: Test more bans, in several channels, etc.

    @defer.inlineCallbacks
    def test_expired_bans(self):
        bans = [
            (
                b'#project', b'$a:forgivenuser', b'b',
                dt('2018-02-07T18:28:18'), b'someop!foo',
                dt('2018-02-14T18:28:18'), b'forgivable behavior',
                dt('2018-02-10T18:28:18'), b'forgivingop!bar',
            ),
        ]
        dbpool = sp.FakeObj()
        dbpool.get_recently_expired_bans = sp.DeferredSequentialReturner([bans])
        yield self.startWebUI(dbpool)

        res, content = yield self.get(b'/bans/expired')
        self.assertEqual(res.code, 200)
        self.assertIn(b'<table', content)
        self.assertIn(b'$a:forgivenuser</td>', content)
        # TODO: Test that other expected bits appear.
        # TODO: Test more bans, in several channels, etc.

    @defer.inlineCallbacks
    def test_all_bans(self):
        bans = [
            (
                b'#project', b'$a:baduser', b'b',
                dt('2018-03-14T15:09:26'), b'someop!foo',
                dt('2018-03-21T15:09:26'), b'bad behavior', None, b'',
            ),
            (
                b'#project', b'$a:forgivenuser', b'b',
                dt('2018-02-07T18:28:18'), b'someop!foo',
                dt('2018-02-14T18:28:18'), b'forgivable behavior',
                dt('2018-02-10T18:28:18'), b'forgivingop!bar',
            ),
        ]
        dbpool = sp.FakeObj()
        dbpool.get_all_bans = sp.DeferredSequentialReturner([bans])
        yield self.startWebUI(dbpool)

        res, content = yield self.get(b'/bans/all')
        self.assertEqual(res.code, 200)
        self.assertIn(b'<table', content)
        self.assertIn(b'$a:baduser</td>', content)
        self.assertIn(b'$a:forgivenuser</td>', content)
        # TODO: Test that other expected bits appear.
        # TODO: Test more bans, in several channels, etc.

    @defer.inlineCallbacks
    def test_edit_ban(self):
        ban = (
            b'#project', b'$a:baduser', b'b',
            dt('2018-03-14T15:09:26'), b'someop!foo',
            dt('2018-03-21T15:09:26'), b'bad behavior', None, b'',
        )
        dbpool = sp.FakeObj()
        dbpool.get_ban_with_auth = sp.DeferredSequentialReturner([ban])
        yield self.startWebUI(dbpool)

        res, content = yield self.get(b'/bans/edit/5/deadbeef')
        self.assertEqual(
            dbpool.get_ban_with_auth.calls,
            [sp.Call(b'5', b'deadbeef')],
        )
        self.assertEqual(res.code, 200)
        self.assertIn(b'<form', content)
        self.assertIn(b'#project', content)
        self.assertIn(b'$a:baduser', content)
        self.assertIn(b'bad behavior', content)
        # TODO: Test that other expected bits appear.

    @defer.inlineCallbacks
    def test_post_edit_ban(self):
        ban = (
            b'#project', b'$a:baduser', b'b',
            dt('2018-03-14T15:09:26'), b'someop!foo',
            dt('2018-03-21T15:09:26'), b'bad behavior', None, b'',
        )
        dbpool = sp.FakeObj()
        dbpool.get_ban_with_auth = sp.DeferredSequentialReturner([ban])
        dbpool.update_ban_by_rowid = sp.DeferredSequentialReturner([None])
        yield self.startWebUI(dbpool)

        res, content = yield self.post(
            b'/bans/edit/5/deadbeef',
            {b'expire_at': b'never', b'reason': b'they lost their chance'},
        )
        self.assertEqual(
            dbpool.get_ban_with_auth.calls,
            [sp.Call(b'5', b'deadbeef')],
        )
        self.assertEqual(
            dbpool.update_ban_by_rowid.calls,
            [sp.Call(b'5', None, b'they lost their chance')],
        )
        self.assertEqual(res.code, 200)
        self.assertIn(b'<form', content)
        self.assertIn(b'#project', content)
        self.assertIn(b'never', content)
        self.assertIn(b'$a:baduser', content)
        self.assertIn(b'they lost their chance', content)
        # TODO: Test that other expected bits appear.

    @defer.inlineCallbacks
    def test_post_edit_ban_errors_sanely_on_bad_expiry(self):
        ban = (
            b'#project', b'$a:baduser', b'b',
            dt('2018-03-14T15:09:26'), b'someop!foo',
            dt('2018-03-21T15:09:26'), b'bad behavior', None, b'',
        )
        dbpool = sp.FakeObj()
        dbpool.get_ban_with_auth = sp.DeferredSequentialReturner([ban])
        dbpool.update_ban_by_rowid = sp.DeferredSequentialReturner([None])
        yield self.startWebUI(dbpool)

        res, content = yield self.post(
            b'/bans/edit/5/deadbeef',
            {
                # 1day is invalid, should be +1day.
                b'expire_at': b'1day',
                b'reason': b'they lost their chance',
            },
        )
        self.assertEqual(res.code, 200)
        self.assertIn(
          b"<p>Invalid expiration timestamp or relative date '1day'",
          content,
        )
        self.assertIn(b'#project', content)
        self.assertIn(b'never', content)
        self.assertIn(b'$a:baduser', content)
        self.assertIn(b'bad behavior', content)
        # TODO: Test that other expected bits appear.


@implementer(IBodyProducer)
class XWWWFormUrlencodedProducer(object):
    def __init__(self, mapping):
        self.body = urllib.urlencode(mapping)
        self.length = len(self.body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


def dt(isoformatted):
    return datetime.datetime.strptime(isoformatted, '%Y-%m-%dT%H:%M:%S')
