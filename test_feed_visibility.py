import sqlite3
import unittest
from contextlib import closing

from migrate_communities import migrate
import tests_communities


class FeedVisibilityTests(unittest.TestCase):
    setUp = tests_communities.CommunityIntegrationTests.setUp
    tearDown = tests_communities.CommunityIntegrationTests.tearDown
    login = tests_communities.CommunityIntegrationTests.login

    def seed_posts(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO communities(public_id) VALUES ('custom')")
            for public_id in ('general', 'introduction', 'wilderness', 'custom'):
                db.execute("INSERT INTO posts(user_id,content,community_id) SELECT 2,?,id FROM communities WHERE public_id=?", (public_id + '-unique-post', public_id))
            db.execute('INSERT OR IGNORE INTO user_community(user_id,community_id) SELECT 1,id FROM communities')
            db.execute('INSERT INTO follows(follower_id,followed_id) VALUES (1,2)')
            db.commit()
        self.login()

    def assert_feed_visibility(self, visible, hidden):
        for sort in ('new', 'popular', 'recommended'):
            for show in ('all', 'following'):
                with self.subTest(sort=sort, show=show):
                    page = self.client.get(f'/?sort={sort}&show={show}').data
                    for public_id in visible:
                        self.assertTrue((public_id + '-unique-post').encode() in page, f'{public_id} should be visible')
                    for public_id in hidden:
                        self.assertFalse((public_id + '-unique-post').encode() in page, f'{public_id} should be hidden')

    def test_migration_adds_database_flag_with_builtin_defaults(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIn('show_in_main_feed', {row[1] for row in db.execute('PRAGMA table_info(communities)')})
            self.assertEqual(db.execute('SELECT public_id,show_in_main_feed FROM communities ORDER BY public_id').fetchall(), [('general', 1), ('introduction', 0), ('wilderness', 0)])
            db.execute("INSERT INTO communities(public_id) VALUES ('custom')")
            self.assertEqual(db.execute("SELECT show_in_main_feed FROM communities WHERE public_id='custom'").fetchone()[0], 1)

    def test_hidden_communities_are_excluded_from_every_main_feed_mode(self):
        self.seed_posts()
        self.assert_feed_visibility(('general', 'custom'), ('introduction', 'wilderness'))
        for public_id in ('introduction', 'wilderness'):
            for sort in ('new', 'popular', 'recommended'):
                with self.subTest(community=public_id, sort=sort):
                    self.assertIn((public_id + '-unique-post').encode(), self.client.get(f'/c/{public_id}?sort={sort}').data)

    def test_database_flag_controls_any_community_and_survives_migration(self):
        self.seed_posts()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIn('show_in_main_feed', {row[1] for row in db.execute('PRAGMA table_info(communities)')})
            db.execute("UPDATE communities SET show_in_main_feed=0 WHERE public_id IN ('general','custom')")
            db.execute("UPDATE communities SET show_in_main_feed=1 WHERE public_id IN ('introduction','wilderness')")
            db.commit()
            migrate(db)
            migrate(db)
            # The new feed still requires membership; migration deliberately
            # removes wilderness memberships, so restore this test fixture.
            db.execute("INSERT OR IGNORE INTO user_community(user_id,community_id) SELECT 1,id FROM communities WHERE public_id='wilderness'")
            db.commit()
        self.assert_feed_visibility(('introduction', 'wilderness'), ('general', 'custom'))

    def test_visibility_is_not_editable_through_community_forms(self):
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id': 'custom', 'show_in_main_feed': '0'})
        self.client.post('/c/introduction/description', data={'description': 'Welcome!', 'show_in_main_feed': '1'})
        self.assertEqual(self.client.post('/c/introduction/show_in_main_feed', data={'show_in_main_feed': '1'}).status_code, 404)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIn('show_in_main_feed', {row[1] for row in db.execute('PRAGMA table_info(communities)')})
            self.assertEqual(db.execute("SELECT public_id,show_in_main_feed FROM communities WHERE public_id IN ('custom','introduction') ORDER BY public_id").fetchall(), [('custom', 1), ('introduction', 0)])
        for path in ('/c', '/c/introduction', '/c/custom'):
            self.assertNotIn(b'name="show_in_main_feed"', self.client.get(path).data)


if __name__ == '__main__':
    unittest.main()
