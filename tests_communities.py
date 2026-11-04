import sqlite3
import unittest
from migrate_communities import migrate

class MigrationTests(unittest.TestCase):
    def test_preserves_posts_and_is_repeatable(self):
        db = sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY); CREATE TABLE comments(post_id INTEGER, user_id INTEGER); CREATE TABLE reactions(post_id INTEGER, user_id INTEGER); CREATE TABLE posts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL); INSERT INTO users VALUES(1); INSERT INTO posts(user_id, content) VALUES(1, "hello");')
        migrate(db)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM user_community').fetchone()[0], 1)
        db.execute('DELETE FROM user_community')
        db.commit()
        migrate(db)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM user_community').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT content, public_id FROM posts JOIN communities ON community_id=communities.id').fetchone(), ('hello', 'general'))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO communities(public_id) VALUES ('Bad1')")
import os, sqlite3, tempfile, unittest
from migrate_communities import migrate
import app as application

class CommunityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.sqlite')
        db = sqlite3.connect(self.path)
        db.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, profile TEXT, location TEXT, birthdate TEXT, created_at TIMESTAMP, password TEXT);
        CREATE TABLE posts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL);
        CREATE TABLE follows(follower_id INTEGER, followed_id INTEGER);
        CREATE TABLE reactions(id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, reaction_type TEXT);
        CREATE TABLE comments(id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, content TEXT, created_at TIMESTAMP);
        INSERT INTO users(id,username) VALUES (1,'alice'),(2,'bob');''')
        db.commit(); migrate(db); db.close()
        application.DATABASE = self.path
        application.app.config.update(TESTING=True, SECRET_KEY='test')
        self.client = application.app.test_client()
    def tearDown(self): self.temp.cleanup()
    def login(self, uid=1, name='alice'):
        with self.client.session_transaction() as session:
            session['user_id'], session['username'] = uid, name
    def test_community_follow_post_and_feed(self):
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id':'music'})
        self.login()
        self.client.post('/c/music/join')
        self.client.post('/c/music/nickname', data={'nickname':'melody'})
        self.client.post('/posts/new', data={'community_id':'music', 'content':'hello community'})
        response = self.client.get('/?sort=new')
        self.assertIn(b'hello community', response.data)
        self.assertIn(b'melody', response.data)
        self.assertEqual(self.client.get('/c/music').status_code, 200)
        self.client.post('/c/music/leave')
        self.assertNotIn(b'hello community', self.client.get('/?sort=new').data)
    def test_admin_only_and_bad_ids(self):
        self.login()
        self.client.post('/c/create', data={'public_id':'valid'})
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id':'Bad1'})
        db = sqlite3.connect(self.path)
        self.assertEqual(db.execute('SELECT count(*) FROM communities').fetchone()[0], 3)
        db.close()
    def test_validation_and_following_sorts(self):
        self.login(1, 'admin')
        for value in ('abc', 'a'*33, 'ab', 'a'*34, 'abc1', 'ABC'):
            self.client.post('/c/create', data={'public_id':value})
        self.login(2, 'bob')
        self.assertEqual(self.client.post('/c/abc/nickname', data={'nickname':'x'}).status_code, 403)
        self.client.post('/posts/new', data={'community_id':'abc', 'content':'from bob'})
        self.client.post('/posts/new', data={'community_id':'missing', 'content':'invalid'})
        self.login(1, 'alice')
        self.client.post('/c/abc/join')
        self.client.post('/c/abc/join')
        db = sqlite3.connect(self.path)
        db.execute('INSERT INTO follows VALUES (1, 2)'); db.commit(); db.close()
        for sort in ('new', 'popular', 'recommended'):
            response = self.client.get('/?show=following&sort=' + sort)
            self.assertEqual(response.data.count(b'from bob'), 1)
            self.assertNotIn(b'invalid', response.data)
        self.assertEqual(self.client.get('/c/missing').status_code, 404)
        self.assertEqual(self.client.get('/posts/1').status_code, 200)
    def test_nickname_links_to_account_in_feed_and_post(self):
        from html.parser import HTMLParser
        class Links(HTMLParser):
            def __init__(self):
                super().__init__(); self.stack = []; self.targets = []
            def handle_starttag(self, tag, attrs):
                if tag == 'a': self.stack.append(dict(attrs).get('href'))
            def handle_endtag(self, tag):
                if tag == 'a' and self.stack: self.stack.pop()
            def handle_data(self, data):
                if '@melody' in data: self.targets.append(self.stack[-1] if self.stack else None)
        self.login()
        self.client.post('/c/general/join')
        self.client.post('/c/general/nickname', data={'nickname':'melody'})
        self.client.post('/posts/new', data={'community_id':'general', 'content':'hello'})
        for path in ('/', '/c/general', '/posts/1'):
            response = self.client.get(path)
            parser = Links(); parser.feed(response.get_data(as_text=True))
            self.assertEqual(parser.targets, ['/u/alice'])
            self.assertNotIn(b'@alice', response.data)
            self.assertIn(b'c/general', response.data)
    def test_feed_memberships_and_followed_users(self):
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id':'music'})
        self.login(2, 'bob')
        self.client.post('/posts/new', data={'community_id':'general', 'content':'member community post'})
        self.client.post('/posts/new', data={'community_id':'music', 'content':'other community post'})
        self.login(1, 'alice')
        self.client.post('/c/general/join')
        new = self.client.get('/?sort=new').data
        self.assertIn(b'member community post', new)
        self.assertNotIn(b'other community post', new)
        for sort in ('popular', 'recommended'):
            self.assertIn(b'other community post', self.client.get('/?sort=' + sort).data)
        for sort in ('new', 'popular', 'recommended'):
            self.assertNotIn(b'member community post', self.client.get('/?show=following&sort=' + sort).data)
        db = sqlite3.connect(self.path); db.execute('INSERT INTO follows VALUES (1, 2)'); db.commit(); db.close()
        self.assertIn(b'other community post', self.client.get('/?show=following&sort=new').data)
        self.client.post('/c/general/leave')
        self.assertNotIn(b'member community post', self.client.get('/?sort=new').data)
        self.assertIn(b'Join', self.client.get('/c/general').data)
    def test_signup_joins_general_and_list_shows_member_count(self):
        result = self.client.post('/signup', data={'username':'newuser', 'password':'test'})
        self.assertEqual(result.status_code, 302)
        db = sqlite3.connect(self.path)
        self.assertEqual(db.execute("SELECT count(*) FROM user_community uc JOIN users u ON u.id=uc.user_id JOIN communities c ON c.id=uc.community_id WHERE u.username='newuser' AND c.public_id='general'").fetchone()[0], 1)
        db.close()
        self.assertIn(b'3 members', self.client.get('/c').data)
    def test_community_description_is_editable_only_by_admin(self):
        self.login()
        self.assertEqual(self.client.post('/c/general/description', data={'description':'unauthorized'}).status_code, 403)
        self.login(1, 'admin')
        self.assertEqual(self.client.post('/c/missing/description', data={'description':'x'}).status_code, 404)
        self.client.post('/c/general/description', data={'description':'Welcome <everyone>'})
        page = self.client.get('/c').get_data(as_text=True)
        self.assertIn('(2 members) — Welcome &lt;everyone&gt;', page)
        self.assertIn('Welcome &lt;everyone&gt;', self.client.get('/c/general').get_data(as_text=True))
        self.client.post('/c/general/description', data={'description':''})
        self.assertNotIn('Welcome', self.client.get('/c').get_data(as_text=True))
    def test_profile_and_post_community_labels(self):
        self.login()
        self.client.post('/c/general/nickname', data={'nickname':'melody'})
        self.client.post('/posts/new', data={'community_id':'general', 'content':'test post'})
        profile = self.client.get('/u/alice').get_data(as_text=True)
        self.assertIn('at <a href="/c/general">/c/general</a> as melody', profile)
        for path in ('/', '/c/general', '/posts/1'):
            self.assertIn('/c/general', self.client.get(path).get_data(as_text=True))
    def test_wilderness_cannot_be_joined_or_use_nickname(self):
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id':'wilderness'})
        self.login()
        self.assertEqual(self.client.post('/c/wilderness/join').status_code, 403)
        self.assertEqual(self.client.post('/c/wilderness/nickname', data={'nickname':'wild'}).status_code, 403)
        page = self.client.get('/c/wilderness').get_data(as_text=True)
        self.assertNotIn('>Join</button>', page)
        self.assertNotIn('Community nickname', page)
        self.client.post('/posts/new', data={'community_id':'wilderness', 'content':'wild post'})
        self.assertEqual(self.client.get('/posts/1').status_code, 200)
    def test_wilderness_hidden_from_all_main_feed_modes(self):
        self.login(1, 'admin')
        self.client.post('/c/create', data={'public_id':'wilderness'})
        self.login(2, 'bob')
        self.client.post('/posts/new', data={'community_id':'wilderness', 'content':'wilderness-only post'})
        self.client.post('/posts/new', data={'community_id':'general', 'content':'general post'})
        self.login(1, 'alice')
        db = sqlite3.connect(self.path); db.execute('INSERT INTO follows VALUES (1,2)'); db.commit(); db.close()
        for sort in ('new', 'popular', 'recommended'):
            for show in ('all', 'following'):
                data = self.client.get('/?sort='+sort+'&show='+show).data
                self.assertNotIn(b'wilderness-only post', data)
                self.assertIn(b'general post', data)
        self.assertIn(b'wilderness-only post', self.client.get('/c/wilderness').data)
    def test_feed_filter_labels_are_uniform_across_sorts(self):
        from html.parser import HTMLParser

        class FilterLinks(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = {}
                self.href = None

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    self.href = dict(attrs).get('href')
                    if self.href:
                        self.links[self.href] = ''

            def handle_data(self, data):
                if self.href and 'show=' in self.href:
                    self.links[self.href] = self.links.get(self.href, '') + data

            def handle_endtag(self, tag):
                if tag == 'a':
                    self.href = None

        self.login()
        for sort in ('new', 'popular', 'recommended'):
            for show in ('all', 'following'):
                with self.subTest(sort=sort, show=show):
                    parser = FilterLinks()
                    parser.feed(self.client.get('/?sort='+sort+'&show='+show).get_data(as_text=True))
                    self.assertEqual(parser.links['/?sort='+sort+'&show=all'], 'Communities')
                    self.assertEqual(parser.links['/?sort='+sort+'&show=following'], 'Following')
    def test_community_list_warns_before_entering_wilderness(self):
        page = self.client.get('/c').get_data(as_text=True)
        self.assertIn('wilderness-warning', page)
        self.assertIn('Stay civilized', page)
        self.assertIn('Enter the wilderness', page)
        self.assertIn('href="/c/wilderness"', page)
    def test_clan_tag_earned_and_retained(self):
        db = sqlite3.connect(self.path)
        db.executemany('INSERT INTO users(id, username) VALUES (?,?)', [(i, 'user'+str(i)) for i in range(3,13)])
        db.executemany("INSERT INTO posts(id,user_id,content,community_id) VALUES (?,1,'qualifying',1)", [(i,) for i in range(1,4)])
        db.executemany("INSERT INTO reactions(post_id,user_id,reaction_type) VALUES (?,?,'like')", [(p,u) for p in range(1,4) for u in range(2,12)])
        db.execute('DELETE FROM user_community WHERE user_id=1'); db.commit(); db.close()
        self.login()
        self.assertEqual(self.client.post('/u/alice/clan-tag', data={'community':'general'}).status_code, 403)
        self.client.post('/c/general/join')
        self.assertEqual(self.client.post('/u/alice/clan-tag', data={'community':'general'}).status_code, 302)
        self.assertIn(b'clan-tag', self.client.get('/posts/1').data)
        self.assertEqual(self.client.post('/u/bob/clan-tag', data={'community':'general'}).status_code, 403)
        self.client.post('/c/general/leave')
        self.client.post('/c/general/join')
        db=sqlite3.connect(self.path); db.execute('DELETE FROM reactions'); db.commit(); db.close()
        self.assertEqual(self.client.post('/u/alice/clan-tag', data={'community':'general'}).status_code, 302)
    def test_achievement_distinct_interactors_and_reaction_trigger(self):
        db=sqlite3.connect(self.path)
        db.executemany('INSERT INTO users(id, username) VALUES (?,?)', [(i,'user'+str(i)) for i in range(3,13)])
        db.executemany("INSERT INTO posts(id,user_id,content,community_id) VALUES (?,1,'post',1)", [(i,) for i in (1,2,3)])
        db.executemany("INSERT INTO reactions(post_id,user_id,reaction_type) VALUES (?,?,'like')", [(p,u) for p in (1,2,3) for u in range(2,11)])
        db.executemany("INSERT INTO comments(post_id,user_id,content) VALUES (?,2,'again')", [(p,) for p in (1,2,3)])
        db.executemany("INSERT INTO comments(post_id,user_id,content) VALUES (?,1,'self')", [(p,) for p in (1,2,3)])
        db.commit(); db.close()
        self.login(12,'user12')
        for post in (1,2): self.client.post('/react', data={'post_id':post,'reaction':'like'})
        db=sqlite3.connect(self.path); self.assertEqual(db.execute('SELECT count(*) FROM earned_clan_tags').fetchone()[0],0); db.close()
        self.client.post('/react', data={'post_id':3,'reaction':'like'})
        db=sqlite3.connect(self.path); self.assertEqual(db.execute('SELECT count(*) FROM earned_clan_tags').fetchone()[0],1); db.close()
        self.login(); self.assertEqual(self.client.post('/u/alice/clan-tag', data={'community':'general'}).status_code,302)
    def test_admin_can_select_any_tag_for_own_profile(self):
        db=sqlite3.connect(self.path); db.execute("INSERT INTO users(id,username) VALUES (3,'admin')"); db.execute("INSERT OR IGNORE INTO communities(public_id) VALUES ('wilderness')"); db.commit(); db.close()
        self.login(3,'admin')
        self.assertEqual(self.client.post('/u/admin/clan-tag',data={'community':'wilderness'}).status_code,302)
        self.assertIn(b'wilderness', self.client.get('/u/admin').data)
        self.assertEqual(self.client.post('/u/bob/clan-tag',data={'community':'wilderness'}).status_code,403)
    def test_clan_selector_disabled_when_no_tags_available(self):
        self.login()
        page = self.client.get('/u/alice').get_data(as_text=True)
        self.assertRegex(page, r'<select id="clan-tag"[^>]* disabled')
        self.assertIn('3 posts', page)
        self.assertIn('10 distinct', page)
        self.assertNotIn('clan-tag', self.client.get('/u/bob').get_data(as_text=True))
