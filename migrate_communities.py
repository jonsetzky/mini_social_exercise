"""Migrate the original SQLite database to the communities schema."""
import sqlite3
import sys
from clan_tags import award_clan_tags
from newcomers import NEWCOMER_PREDICATE


def migrate(db):
    # The original schema does not declare references to posts. Disable FK checks
    # around the table replacement, and restore the caller's setting afterward.
    foreign_keys = db.execute('PRAGMA foreign_keys').fetchone()[0]
    db.execute('PRAGMA foreign_keys = OFF')
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute("""CREATE TABLE IF NOT EXISTS communities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL UNIQUE CHECK(length(public_id) BETWEEN 3 AND 33
              AND public_id NOT GLOB '*[^a-z]*'))""")
        if 'description' not in {row[1] for row in db.execute('PRAGMA table_info(communities)')}:
            db.execute("ALTER TABLE communities ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        visibility_added = 'show_in_main_feed' not in {row[1] for row in db.execute('PRAGMA table_info(communities)')}
        if visibility_added:
            db.execute("ALTER TABLE communities ADD COLUMN show_in_main_feed INTEGER NOT NULL DEFAULT 1 CHECK(show_in_main_feed IN (0, 1))")
        db.execute("""CREATE TABLE IF NOT EXISTS user_community (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
            nickname TEXT, PRIMARY KEY(user_id, community_id))""")
        db.execute("INSERT OR IGNORE INTO communities(public_id) VALUES ('general')")
        db.execute("INSERT OR IGNORE INTO communities(public_id, show_in_main_feed) VALUES ('wilderness', 0)")
        db.execute("""INSERT OR IGNORE INTO communities(public_id, description, show_in_main_feed)
            VALUES ('introduction', 'Introduce yourself, ask basic questions, and welcome newcomers warmly.', 0)""")
        if visibility_added:
            db.execute("UPDATE communities SET show_in_main_feed=0 WHERE public_id IN ('wilderness', 'introduction')")
        db.execute("CREATE TABLE IF NOT EXISTS community_migrations (name TEXT PRIMARY KEY)")
        db.execute("""CREATE TABLE IF NOT EXISTS used_comment_confirmations (
            nonce TEXT PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        if not db.execute("SELECT 1 FROM community_migrations WHERE name='general_membership'").fetchone():
            db.execute("""INSERT OR IGNORE INTO user_community (user_id, community_id)
                SELECT users.id, communities.id FROM users CROSS JOIN communities
                WHERE communities.public_id = 'general'""")
            db.execute("INSERT INTO community_migrations(name) VALUES ('general_membership')")
        db.execute("DELETE FROM user_community WHERE community_id IN (SELECT id FROM communities WHERE public_id = 'wilderness')")
        db.execute("UPDATE user_community SET nickname=NULL WHERE community_id IN (SELECT id FROM communities WHERE public_id='introduction') AND nickname IS NOT NULL")
        columns = {row[1] for row in db.execute('PRAGMA table_info(posts)')}
        if 'community_id' not in columns:
            db.execute('''CREATE TABLE posts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                content TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                community_id INTEGER NOT NULL REFERENCES communities(id))''')
            db.execute('''INSERT INTO posts_new(id, user_id, content, created_at, community_id)
                SELECT id, user_id, content, created_at, (SELECT id FROM communities WHERE public_id='general') FROM posts''')
            db.execute('DROP TABLE posts')
            db.execute('ALTER TABLE posts_new RENAME TO posts')
        db.execute("""CREATE TABLE IF NOT EXISTS user_introductions (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE)""")
        db.execute("""INSERT OR IGNORE INTO user_introductions(user_id)
            SELECT DISTINCT p.user_id FROM posts p
            JOIN users u ON u.id=p.user_id
            JOIN communities c ON c.id=p.community_id
            WHERE c.public_id='introduction'""")
        if not db.execute("SELECT 1 FROM community_migrations WHERE name='introduction_membership'").fetchone():
            if 'created_at' in {row[1] for row in db.execute('PRAGMA table_info(users)')}:
                db.execute(f"""INSERT OR IGNORE INTO user_community (user_id, community_id)
                    SELECT u.id, c.id FROM users u CROSS JOIN communities c
                    WHERE c.public_id = 'introduction' AND {NEWCOMER_PREDICATE}""")
            db.execute("INSERT INTO community_migrations(name) VALUES ('introduction_membership')")
        db.execute("CREATE TABLE IF NOT EXISTS earned_clan_tags (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, community_id INTEGER NOT NULL REFERENCES communities(id) ON DELETE CASCADE, PRIMARY KEY(user_id, community_id))")
        if 'clan_tag_id' not in {row[1] for row in db.execute('PRAGMA table_info(users)')}:
            db.execute('ALTER TABLE users ADD COLUMN clan_tag_id INTEGER REFERENCES communities(id)')
        award_clan_tags(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute('PRAGMA foreign_keys = ' + ('ON' if foreign_keys else 'OFF'))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python migrate_communities.py DATABASE')
    with sqlite3.connect(sys.argv[1]) as connection:
        migrate(connection)
