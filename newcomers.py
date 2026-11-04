"""Shared eligibility rule for newcomer onboarding (design claims 18, 19, 21)."""

INTRODUCTION_QUESTIONS = (
    ("introduction_about", "What would you like us to know about you?"),
    ("introduction_interests", "What are your interests or hobbies?"),
    ("introduction_here", "What brought you here?"),
    ("introduction_questions", "What would you like to learn or ask?"),
)

# The caller aliases users as u. SQLite timestamps use UTC throughout the app.
NEWCOMER_PREDICATE = """
    julianday(u.created_at) > julianday('now', '-7 days')
    AND julianday(u.created_at) <= julianday('now')
    AND NOT EXISTS (SELECT 1 FROM user_introductions i WHERE i.user_id = u.id)
    AND NOT EXISTS (
        SELECT 1 FROM posts p JOIN communities c ON c.id = p.community_id
        WHERE p.user_id = u.id AND c.public_id = 'introduction'
    )
"""
