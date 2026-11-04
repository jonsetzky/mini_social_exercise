import sqlite3
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from html.parser import HTMLParser
from unittest.mock import patch

import app as application
from migrate_communities import migrate
import tests_communities


class ConfirmationFields(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.fields[attrs['name']] = attrs.get('value', '')


class HomepageInvitation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.invitation = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')

    def handle_endtag(self, tag):
        if tag == 'a':
            self.href = None

    def handle_data(self, data):
        if self.href and data.strip() == 'Introduce yourself':
            self.invitation = self.href


class NewcomerTests(unittest.TestCase):
    setUp = tests_communities.CommunityIntegrationTests.setUp
    tearDown = tests_communities.CommunityIntegrationTests.tearDown
    login = tests_communities.CommunityIntegrationTests.login

    def set_age(self, days):
        with closing(sqlite3.connect(self.path)) as db:
            # Signup stores CURRENT_TIMESTAMP at whole-second precision.
            # Match it so SQLite clock precision cannot shift the seven-day boundary.
            db.execute('UPDATE users SET created_at=? WHERE id=1',
                       ((datetime.utcnow() - timedelta(days=days)).replace(microsecond=0),))
            db.commit()

    def post(self, community='general', content='Hello everyone'):
        self.login()
        self.client.post('/posts/new', data={'community_id': community, 'content': content})
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT max(id) FROM posts').fetchone()[0]

    def test_migration_creates_introduction_and_backfills_only_newcomers_once(self):
        self.set_age(1)
        with closing(sqlite3.connect(self.path)) as db:
            # Simulate a database that has not yet received the introduction migration.
            db.execute("DELETE FROM community_migrations WHERE name='introduction_membership'")
            db.commit()
            migrate(db)
            self.assertEqual(db.execute("SELECT u.username FROM user_community m JOIN users u ON u.id=m.user_id JOIN communities c ON c.id=m.community_id WHERE c.public_id='introduction'").fetchall(), [('alice',)])
            db.execute("DELETE FROM user_community WHERE community_id=(SELECT id FROM communities WHERE public_id='introduction')")
            db.commit()
            migrate(db)
            self.assertEqual(db.execute("SELECT count(*) FROM user_community WHERE community_id=(SELECT id FROM communities WHERE public_id='introduction')").fetchone()[0], 0)

    def test_signup_joins_introduction_and_homepage_prompts_with_default(self):
        self.client.post('/signup', data={'username': 'newcomer', 'password': 'test'})
        with closing(sqlite3.connect(self.path)) as db:
            memberships = db.execute("SELECT c.public_id FROM user_community m JOIN communities c ON c.id=m.community_id JOIN users u ON u.id=m.user_id WHERE u.username='newcomer' ORDER BY c.public_id").fetchall()
            self.assertEqual(memberships, [('general',), ('introduction',)])
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('Introduce yourself', page)
        self.assertRegex(page, r'<option value="introduction"\s+selected')

    def test_prompt_ends_at_seven_days_or_after_introduction(self):
        self.login()
        for days, expected in ((6.999, True), (7, False), (8, False)):
            self.set_age(days)
            self.assertEqual('id="introduce-yourself-title"' in self.client.get('/').get_data(as_text=True), expected)
        self.set_age(1)
        self.post('introduction')
        self.assertNotIn(b'id="introduce-yourself-title"', self.client.get('/').data)

    def test_unknown_age_and_anonymous_visitors_have_no_prompt(self):
        self.assertNotIn(b'id="introduce-yourself-title"', self.client.get('/').data)
        self.login()
        self.assertNotIn(b'id="introduce-yourself-title"', self.client.get('/').data)

    def test_introduction_entry_dialog_includes_direct_visits_and_alias(self):
        response = self.client.get('/c/introduction')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="introduction-warning"', response.data)
        self.assertIn(b'Basic questions and mistakes are normal', response.data)
        self.assertEqual(self.client.get('/c/introducton').location, '/c/introduction')

    def test_homepage_invitation_skips_warning_for_that_visit_only(self):
        self.set_age(1)
        self.login()
        parser = HomepageInvitation()
        parser.feed(self.client.get('/').get_data(as_text=True))
        self.assertIsNotNone(parser.invitation)
        response = self.client.get(parser.invitation)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'id="introduction-warning"', response.data)
        self.assertIn(b'id="new-post"', response.data)
        self.assertIn(b'id="introduction-warning"', self.client.get('/c/introduction').data)

    def test_introduction_disables_nicknames_but_keeps_membership_controls(self):
        self.login()
        self.client.post('/c/introduction/join')
        response = self.client.post('/c/introduction/nickname', data={'nickname': 'alias'})
        self.assertEqual(response.status_code, 403)
        page = self.client.get('/c/introduction').data
        self.assertNotIn(b'Community nickname', page)
        self.assertIn(b'/c/introduction/leave', page)
        self.assertEqual(self.client.post('/c/general/nickname', data={'nickname': 'normal'}).status_code, 302)

    def test_legacy_introduction_nicknames_are_hidden_everywhere(self):
        self.set_age(1)
        post_id = self.post('introduction')
        self.client.post('/c/introduction/join')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE user_community SET nickname='legacyalias' WHERE community_id=(SELECT id FROM communities WHERE public_id='introduction') AND user_id=1")
            db.commit()
        for path in ('/c/introduction', '/', '/?sort=popular', '/?sort=recommended', f'/posts/{post_id}', '/u/alice'):
            with self.subTest(path=path):
                page = self.client.get(path).data
                self.assertNotIn(b'legacyalias', page)
                self.assertIn(b'alice', page)

    def test_migration_clears_only_introduction_nicknames(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO user_community(user_id, community_id, nickname) SELECT 1,id,'oldintro' FROM communities WHERE public_id='introduction'")
            db.execute("UPDATE user_community SET nickname='generalalias' WHERE user_id=1 AND community_id=(SELECT id FROM communities WHERE public_id='general')")
            db.commit()
            migrate(db)
            migrate(db)
            self.assertEqual(db.execute("SELECT c.public_id,m.nickname FROM user_community m JOIN communities c ON c.id=m.community_id WHERE m.user_id=1 ORDER BY c.public_id").fetchall(), [('general', 'generalalias'), ('introduction', None)])

    def test_introduction_form_offers_guiding_questions(self):
        self.set_age(1)
        self.login()
        for path in ('/c/introduction',):
            with self.subTest(path=path):
                page = self.client.get(path).data
                self.assertIn(b'name="introduction_about"', page)
                self.assertIn(b'name="introduction_interests"', page)
                self.assertIn(b'name="introduction_here"', page)
                self.assertIn(b'name="introduction_questions"', page)
                self.assertIn(b'Answer whichever questions you like', page)

    def test_homepage_keeps_basic_composer_for_newcomers(self):
        self.set_age(1)
        self.login()
        for path in ('/', '/?sort=popular', '/?sort=recommended', '/c/general'):
            with self.subTest(path=path):
                text = self.client.get(path).get_data(as_text=True)
                self.assertTrue('name="content"' in text)
                self.assertFalse('name="introduction_about"' in text)
                self.assertFalse("const introductionFields" in text)

    def test_introduction_rejects_posts_from_accounts_at_least_seven_days_old(self):
        self.login()
        for days in (7, 8, 30):
            self.set_age(days)
            for fields in ({'content': 'Another introduction'}, {'introduction_about': 'Another introduction'}):
                with self.subTest(days=days, fields=fields):
                    response = self.client.post('/posts/new', data={'community_id': 'introduction', **fields})
                    self.assertEqual(response.status_code, 403)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)

    def test_only_one_introduction_is_allowed(self):
        self.set_age(1)
        self.login()
        self.assertEqual(self.client.post('/posts/new', data={'community_id': 'introduction', 'introduction_about': 'My first introduction'}).status_code, 302)
        for fields in ({'content': 'Second introduction'}, {'introduction_about': 'Second introduction'}):
            response = self.client.post('/posts/new', data={'community_id': 'introduction', **fields})
            self.assertEqual(response.status_code, 403)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 1)

    def test_concurrent_introductions_cannot_bypass_the_one_post_limit(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        self.set_age(1)
        clients = [application.app.test_client(), application.app.test_client()]
        for client in clients:
            with client.session_transaction() as session:
                session['user_id'], session['username'] = 1, 'alice'
        checks_completed = Barrier(2)
        original_check = application.is_newcomer

        def check_before_either_insert(user_id):
            eligible = original_check(user_id)
            checks_completed.wait(timeout=5)
            return eligible

        def submit(client):
            return client.post('/posts/new', data={'community_id': 'introduction', 'content': 'Hello everyone'}).status_code

        # Force both real eligibility reads to complete before either request
        # can insert, reproducing the window a double submission would exploit.
        with patch.object(application, 'is_newcomer', side_effect=check_before_either_insert):
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(submit, clients))
        self.assertEqual(sorted(statuses), [302, 403])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 1)

    def test_deleting_an_introduction_does_not_allow_another(self):
        self.set_age(1)
        post_id = self.post('introduction')
        self.client.post(f'/posts/{post_id}/delete')
        response = self.client.post('/posts/new', data={'community_id': 'introduction', 'content': 'Another introduction'})
        self.assertEqual(response.status_code, 403)
        text = self.client.get('/').get_data(as_text=True)
        self.assertFalse('id="introduce-yourself-title"' in text)
        self.assertFalse('value="introduction"' in text)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)

    def test_migration_remembers_existing_introductions_after_deletion(self):
        self.set_age(1)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO posts(user_id,content,community_id) SELECT 1,'Legacy introduction',id FROM communities WHERE public_id='introduction'")
            db.commit()
            migrate(db)
            migrate(db)
            db.execute('DELETE FROM posts')
            db.commit()
        self.login()
        response = self.client.post('/posts/new', data={'community_id': 'introduction', 'introduction_about': 'Another introduction'})
        self.assertEqual(response.status_code, 403)

    def test_ineligible_users_cannot_select_introduction_or_see_its_composer(self):
        self.login()
        for days in (7, 8):
            self.set_age(days)
            with self.subTest(days=days):
                self.assertFalse('value="introduction"' in self.client.get('/').get_data(as_text=True))
                text = self.client.get('/c/introduction').get_data(as_text=True)
                self.assertFalse('id="new-post"' in text)
        self.set_age(1)
        self.post('introduction')
        self.assertFalse('value="introduction"' in self.client.get('/').get_data(as_text=True))
        self.assertFalse('id="new-post"' in self.client.get('/c/introduction').get_data(as_text=True))

    def test_established_users_can_still_welcome_in_comments_and_post_elsewhere(self):
        self.set_age(1)
        post_id = self.post('introduction')
        self.login(2, 'bob')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE users SET created_at=? WHERE id=2', (datetime.utcnow() - timedelta(days=30),))
            db.commit()
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data={'content': 'Welcome Alice!'}).status_code, 302)
        self.assertEqual(self.client.post('/posts/new', data={'community_id': 'general', 'content': 'Normal post'}).status_code, 302)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT content FROM comments').fetchall(), [('Welcome Alice!',)])
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 2)

    def test_guided_answers_create_one_introduction_post(self):
        self.set_age(1)
        self.login()
        response = self.client.post('/posts/new', data={
            'community_id': 'introduction', 'introduction_about': '  I am Alice.  ',
            'introduction_interests': 'Drawing and games', 'introduction_here': '   ',
            'introduction_questions': 'How can I find communities?',
        })
        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT content,c.public_id FROM posts p JOIN communities c ON c.id=p.community_id').fetchall(), [(
                'What would you like us to know about you?\nI am Alice.\n\n'
                'What are your interests or hobbies?\nDrawing and games\n\n'
                'What would you like to learn or ask?\nHow can I find communities?',
                'introduction',
            )])

    def test_empty_guided_answers_do_not_create_a_post(self):
        self.set_age(1)
        self.login()
        self.client.post('/posts/new', data={'community_id': 'introduction', 'introduction_about': '  ', 'introduction_interests': ''})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)

    def test_guided_answers_use_existing_moderation_and_preserve_draft(self):
        self.set_age(1)
        self.login()
        with patch.object(application, 'TIER1_WORDS', ['severe']):
            warning = self.client.post('/posts/new', data={'community_id': 'introduction', 'introduction_about': 'A severe draft'})
        self.assertEqual(warning.status_code, 200)
        self.assertIn(b'A ', warning.data)
        parser = ConfirmationFields()
        parser.feed(warning.get_data(as_text=True))
        edited = self.client.post('/posts/edit', data=parser.fields)
        self.assertIn(b'What would you like us to know about you?\nA severe draft', edited.data)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM posts').fetchone()[0], 0)

    def test_guiding_answers_do_not_change_other_communities_posts(self):
        self.login()
        self.client.post('/posts/new', data={'community_id': 'general', 'content': 'Normal post', 'introduction_about': 'Ignore me'})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT content FROM posts').fetchall(), [('Normal post',)])

    def test_switching_community_without_javascript_preserves_visible_answers(self):
        self.login()
        # With JavaScript disabled, the initially visible question fields remain
        # enabled when the user changes the community selector to general.
        self.client.post('/posts/new', data={'community_id': 'general', 'introduction_about': 'Hello from Alice'})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT content,c.public_id FROM posts p JOIN communities c ON c.id=p.community_id').fetchall(), [(
                'What would you like us to know about you?\nHello from Alice', 'general',
            )])

    def test_composer_initially_enables_only_fields_for_selected_community(self):
        class Fieldsets(HTMLParser):
            def __init__(self):
                super().__init__()
                self.states = {}

            def handle_starttag(self, tag, attrs):
                if tag == 'fieldset':
                    attrs = dict(attrs)
                    self.states[attrs['id']] = ('hidden' in attrs, 'disabled' in attrs)

        self.set_age(1)
        self.login()
        for path, introducing in (('/c/introduction', True), ('/', False), ('/c/general', False)):
            with self.subTest(path=path):
                parser = Fieldsets()
                parser.feed(self.client.get(path).get_data(as_text=True))
                if introducing:
                    self.assertEqual(parser.states['introduction-fields'], (False, False))
                else:
                    self.assertNotIn('introduction-fields', parser.states)
                self.assertEqual(parser.states['ordinary-post-fields'], (introducing, introducing))

    def test_guided_answers_are_displayed_as_plain_text(self):
        self.set_age(1)
        self.login()
        self.client.post('/posts/new', data={'community_id': 'introduction', 'introduction_about': 'Hi <em>friend</em>'})
        with closing(sqlite3.connect(self.path)) as db:
            post_id = db.execute('SELECT id FROM posts').fetchone()[0]
        for path in ('/c/introduction', f'/posts/{post_id}', '/u/alice'):
            with self.subTest(path=path):
                text = self.client.get(path).get_data(as_text=True)
                self.assertTrue('Hi &lt;em&gt;friend&lt;/em&gt;' in text)

    def test_comment_is_not_published_until_confirmed_and_confirmation_is_single_use(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        content = 'Welcome <friend>!'
        response = self.client.post(f'/posts/{post_id}/comment', data={'content': content})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Basic questions and mistakes are normal', response.data)
        self.assertIn(b'Welcome &lt;friend&gt;!', response.data)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)
        parser = ConfirmationFields()
        parser.feed(response.get_data(as_text=True))
        confirmed = self.client.post(f'/posts/{post_id}/comment', data=parser.fields)
        self.assertEqual(confirmed.status_code, 302)
        self.client.post(f'/posts/{post_id}/comment', data=parser.fields)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT content FROM comments').fetchall(), [(content,)])

    def test_confirmation_redirects_to_post_when_browser_referrer_is_comment_form(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        warning = self.client.post(f'/posts/{post_id}/comment', data={'content': 'Welcome!'})
        parser = ConfirmationFields()
        parser.feed(warning.get_data(as_text=True))
        response = self.client.post(f'/posts/{post_id}/comment', data=parser.fields,
                                    headers={'Referer': f'http://localhost/posts/{post_id}/comment'})
        self.assertEqual(response.location, f'/posts/{post_id}')
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_restoring_old_session_cookie_cannot_replay_confirmation(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        warning = self.client.post(f'/posts/{post_id}/comment', data={'content': 'Welcome!'})
        parser = ConfirmationFields()
        parser.feed(warning.get_data(as_text=True))
        cookie = self.client.get_cookie('session').value
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data=parser.fields).status_code, 302)
        self.client.set_cookie('session', cookie)
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data=parser.fields).status_code, 400)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 1)

    def test_two_pending_comments_can_each_be_confirmed(self):
        self.set_age(1)
        post_id = self.post()
        other_post = self.post(content='Another post')
        self.login(2, 'bob')
        pending = []
        for target in (post_id, other_post):
            warning = self.client.post(f'/posts/{target}/comment', data={'content': 'Welcome!'})
            parser = ConfirmationFields()
            parser.feed(warning.get_data(as_text=True))
            pending.append((target, parser.fields))
        for target, fields in pending:
            self.assertEqual(self.client.post(f'/posts/{target}/comment', data=fields).status_code, 302)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 2)

    def test_comment_draft_can_be_edited_without_publishing(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        response = self.client.post(f'/posts/{post_id}/comment', data={'content': '<draft>', 'edit': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'&lt;draft&gt;', response.data)
        self.assertIn(b'<textarea', response.data)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)

    def test_cancel_and_edit_with_confirmation_preserves_draft_without_javascript(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        warning = self.client.post(f'/posts/{post_id}/comment', data={'content': 'My draft'})
        parser = ConfirmationFields()
        parser.feed(warning.get_data(as_text=True))
        response = self.client.post(f'/posts/{post_id}/comment', data={**parser.fields, 'edit': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My draft</textarea>', response.data)
        self.assertNotIn(b'<dialog', response.data)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)

    def test_confirmation_cannot_be_used_for_changed_content_post_or_account(self):
        self.set_age(1)
        post_id = self.post()
        other_post = self.post(content='Another post')
        self.login(2, 'bob')
        response = self.client.post(f'/posts/{post_id}/comment', data={'content': 'Welcome!'})
        parser = ConfirmationFields()
        parser.feed(response.get_data(as_text=True))
        self.assertIn('confirmation', parser.fields)
        for target, changes in ((post_id, {'content': 'Changed'}), (other_post, {})):
            self.client.post(f'/posts/{target}/comment', data={**parser.fields, **changes})
        self.login()
        self.client.post(f'/posts/{post_id}/comment', data=parser.fields)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)

    def test_expired_and_tampered_confirmations_do_not_publish(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        warning = self.client.post(f'/posts/{post_id}/comment', data={'content': 'Welcome!'})
        parser = ConfirmationFields()
        parser.feed(warning.get_data(as_text=True))
        tampered = {**parser.fields, 'confirmation': parser.fields['confirmation'] + 'invalid'}
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data=tampered).status_code, 400)
        # Advance only the signing clock to exercise expiry without changing eligibility.
        import time
        future = time.time() + 901
        with patch('itsdangerous.timed.time.time', return_value=future):
            self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data=parser.fields).status_code, 400)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)

    def test_empty_comments_are_not_published(self):
        self.set_age(1)
        post_id = self.post()
        self.login(2, 'bob')
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data={'content': '  '}).status_code, 302)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 0)

    def test_established_authors_and_self_comments_publish_without_reminder(self):
        self.set_age(8)
        post_id = self.post()
        self.login(2, 'bob')
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data={'content': 'Hello'}).status_code, 302)
        self.set_age(1)
        self.login()
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data={'content': 'My reply'}).status_code, 302)
        self.post('introduction')
        self.login(2, 'bob')
        self.assertEqual(self.client.post(f'/posts/{post_id}/comment', data={'content': 'Glad to meet you'}).status_code, 302)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM comments').fetchone()[0], 3)

    def test_missing_post_is_404_and_anonymous_comments_require_login(self):
        self.assertIn('/login', self.client.post('/posts/999/comment', data={'content': 'Hi'}).location)
        self.login()
        self.assertEqual(self.client.post('/posts/999/comment', data={'content': 'Hi'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
