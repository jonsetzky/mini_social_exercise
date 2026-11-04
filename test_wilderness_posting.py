import sqlite3
from contextlib import closing
from unittest.mock import patch
from tests_communities import CommunityIntegrationTests
import app as application


class WildernessPostingTests(CommunityIntegrationTests):
    def test_posts_at_or_above_five_require_confirmation_and_land_only_in_wilderness(self):
        from html.parser import HTMLParser

        class ConfirmationForm(HTMLParser):
            def __init__(self):
                super().__init__()
                self.action = None
                self.fields = {}
                self.in_confirmation = False

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'form':
                    self.in_confirmation = attrs.get('action') == '/posts/confirm'
                    if self.in_confirmation:
                        self.action = attrs['action']
                if tag == 'input' and self.in_confirmation:
                    self.fields[attrs['name']] = attrs.get('value', '')

            def handle_endtag(self, tag):
                if tag == 'form':
                    self.in_confirmation = False

        self.login()
        with patch.multiple(application, TIER1_WORDS=['severe'], TIER2_PHRASES=['claim prize'], TIER3_WORDS=['mild', 'rude', 'coarse', 'tier3badword']):
            for content in ('severe message', 'claim prize now', 'mild rude coarse', 'mild rude https://example.com', 'https://example.com https://example.org https://example.net', 'tier3badword tier3badword tier3badword', 'tier3badword, TIER3BADWORD! (tier3badword)'):
                with self.subTest(content=content):
                    with closing(sqlite3.connect(self.path)) as db:
                        db.execute('DELETE FROM posts')
                        db.commit()
                    warning = self.client.post('/posts/new', data={'community_id': 'general', 'content': content})
                    self.assertEqual(warning.status_code, 200, 'Flagged posts must show a confirmation before publishing')
                    with closing(sqlite3.connect(self.path)) as db:
                        self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)
                    parser = ConfirmationForm()
                    parser.feed(warning.get_data(as_text=True))
                    self.assertEqual(parser.action, '/posts/confirm')
                    response = self.client.post(parser.action, data=parser.fields)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.location.endswith('/c/wilderness'))
                    with closing(sqlite3.connect(self.path)) as db:
                        self.assertEqual(db.execute('SELECT content, public_id FROM posts JOIN communities ON communities.id=posts.community_id').fetchall(), [(content, 'wilderness')])
                    for url in ('/c/general', '/?sort=new&show=all', '/?sort=popular&show=all', '/?sort=recommended&show=all'):
                        self.assertNotIn(content, self.client.get(url).get_data(as_text=True))
                    self.assertIn(content, self.client.get('/c/wilderness').get_data(as_text=True))

    def test_posts_below_five_stay_in_selected_community_without_warning(self):
        self.login()
        with patch.multiple(application, TIER1_WORDS=['severe'], TIER2_PHRASES=['claim prize'], TIER3_WORDS=['mild', 'rude']):
            for content, score in (('ordinary message', 0.0), ('a mild message', 2.0), ('mild rude', 4.0), ('mild mild', 4.0), ('visit https://example.com', 2.0), ('THIS IS AN ALL CAPS MESSAGE', 0.5), ('ABCDEFGHIJKLMNOP mild rude', 4.5)):
                with self.subTest(content=content, score=score):
                    self.assertEqual(application.moderate_content(content)[1], score)
                    with closing(sqlite3.connect(self.path)) as db:
                        db.execute('DELETE FROM posts')
                        db.commit()
                    response = self.client.post('/posts/new', data={'community_id': 'general', 'content': content})
                    self.assertEqual(response.status_code, 302)
                    with closing(sqlite3.connect(self.path)) as db:
                        self.assertEqual(db.execute('SELECT content, public_id FROM posts JOIN communities ON communities.id=posts.community_id').fetchall(), [(content, 'general')])

    def test_popup_highlights_each_risk_category_with_its_color(self):
        from html.parser import HTMLParser

        class Highlights(HTMLParser):
            def __init__(self):
                super().__init__()
                self.classes = None
                self.marks = []

            def handle_starttag(self, tag, attrs):
                if tag == 'mark':
                    self.classes = dict(attrs).get('class', '').split()

            def handle_data(self, text):
                if self.classes is not None:
                    self.marks.append((text, self.classes))

            def handle_endtag(self, tag):
                if tag == 'mark':
                    self.classes = None

        self.login()
        with patch.multiple(application, TIER1_WORDS=['severe'], TIER2_PHRASES=['claim prize'], TIER3_WORDS=['mild', 'rude']):
            for content, expected in (
                ('severe claim prize mild https://example.com', [('severe', 'red'), ('claim prize', 'yellow'), ('mild', 'yellow'), ('https://example.com', 'red')]),
                ('ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN MILD rude https://example.com', [('ABCDEFGHIJKLMNOPQRSTUVWXYZABCDEFGHIJKLMN', 'red'), ('MILD', 'yellow'), ('rude', 'yellow'), ('https://example.com', 'red')]),
                ('mild rude https://example.com', [('mild', 'yellow'), ('rude', 'yellow'), ('https://example.com', 'red')]),
                ('mild, MILD! (mild)', [('mild', 'yellow'), ('MILD', 'yellow'), ('mild', 'yellow')]),
            ):
                with self.subTest(content=content):
                    response = self.client.post('/posts/new', data={'community_id': 'general', 'content': content})
                    self.assertEqual(response.status_code, 200)
                    parser = Highlights()
                    parser.feed(response.get_data(as_text=True))
                    self.assertEqual([(text, next((color for color in ('red', 'yellow') if 'risk-'+color in classes), None)) for text, classes in parser.marks], expected)

    def test_edit_view_preserves_draft_without_creating_post(self):
        self.login()
        with patch.object(application, 'TIER1_WORDS', ['severe']):
            warning = self.client.post('/posts/new', data={'community_id': 'general', 'content': 'severe <draft>'})
            self.assertIn(b'btn-success', warning.data)
            self.assertNotIn(b'<textarea', warning.data)
            edit = self.client.post('/posts/edit', data={'community_id': 'general', 'content': 'severe <draft>'})
            self.assertIn(b'<textarea', edit.data)
            self.assertIn(b'severe &lt;draft&gt;', edit.data)
            db = sqlite3.connect(self.path)
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)
            db.close()

    def test_matches_use_boundaries_and_highlight_all_tiers(self):
        with patch.object(application, 'TIER1_WORDS', ['severe']), patch.object(application, 'TIER2_PHRASES', ['claim prize']):
            self.assertEqual(application.severe_matches('unsevere claim prizes'), [])
            self.assertEqual([s for s, flagged in application.highlight_segments('SEVERE, claim prize and severe') if flagged], ['SEVERE', 'claim prize', 'severe'])

    def test_warning_highlights_messages_flagged_by_other_moderation_rules(self):
        with patch.multiple(application, TIER1_WORDS=[], TIER2_PHRASES=[], TIER3_WORDS=['mild']):
            for content in ('a mild message', 'visit https://example.com', 'THIS IS AN ALL CAPS MESSAGE'):
                with self.subTest(content=content):
                    segments = application.highlight_segments(content)
                    self.assertEqual(''.join(text for text, _ in segments), content)
                    self.assertTrue(any(flagged for _, flagged in segments))

    def test_tampered_confirmation_is_rejected(self):
        self.login()
        self.assertEqual(self.client.post('/posts/confirm', data={'confirmation': 'invalid'}).status_code, 400)

    def test_flagged_post_requires_confirmation_and_is_redirected(self):
        self.login()
        with patch.object(application, 'TIER1_WORDS', ['severe']), patch.object(application, 'TIER2_PHRASES', ['claim prize']):
            response = self.client.post('/posts/new', data={'community_id': 'general', 'content': 'SEVERE claim prize'})
            self.assertIn(b'<mark', response.data)
            self.assertIn(b'/c/wilderness', response.data)
            db = sqlite3.connect(self.path)
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)
            db.close()
            from html.parser import HTMLParser
            class Token(HTMLParser):
                value = None
                def handle_starttag(self, tag, attrs):
                    attrs = dict(attrs)
                    if tag == 'input' and attrs.get('name') == 'confirmation': self.value = attrs.get('value')
            parser = Token(); parser.feed(response.get_data(as_text=True))
            self.assertTrue(parser.value)
            self.client.post('/posts/confirm', data={'confirmation': parser.value})
            db = sqlite3.connect(self.path)
            self.assertEqual(db.execute('SELECT content, public_id FROM posts JOIN communities ON communities.id=posts.community_id').fetchone(), ('SEVERE claim prize', 'wilderness'))
            db.close()
            self.assertIn(b'SEVERE claim prize', self.client.get('/c/wilderness').data)
            self.assertIn(b'SEVERE claim prize', self.client.get('/posts/1').data)
            self.assertNotIn(b'SEVERE claim prize', self.client.get('/u/alice').data)
            self.client.post('/posts/confirm', data={'confirmation': parser.value})
            db = sqlite3.connect(self.path)
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 1)
            db.close()
