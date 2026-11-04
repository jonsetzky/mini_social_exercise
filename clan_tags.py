"""Award clan tags from qualifying community activity."""
def award_clan_tags(db):
    db.execute("""INSERT OR IGNORE INTO earned_clan_tags(user_id, community_id)
        SELECT p.user_id, p.community_id FROM posts p
        JOIN communities community ON community.id=p.community_id
        JOIN user_community membership ON membership.user_id=p.user_id AND membership.community_id=p.community_id
        WHERE community.public_id != 'wilderness'
          AND (SELECT COUNT(DISTINCT actor.user_id) FROM (
              SELECT post_id, user_id FROM reactions UNION SELECT post_id, user_id FROM comments
          ) actor WHERE actor.post_id=p.id AND actor.user_id != p.user_id) >= 10
        GROUP BY p.user_id, p.community_id HAVING COUNT(*) >= 3""")
