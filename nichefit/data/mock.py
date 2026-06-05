"""
Bundled sample follower dataset for mock mode.

When APIFY_API_TOKEN is missing we serve these instead of scraping, and when
ANTHROPIC_API_KEY is missing we score them with a deterministic heuristic. This
lets you click through the entire UI and scoring flow before spending anything.
"""
from __future__ import annotations

# A small, varied cast: niche experts, mid-tier creators, micro accounts, and
# an obvious bot — so the tier distribution and top-followers table look real.
MOCK_FOLLOWERS: list[dict] = [
    {
        "screen_name": "sama",
        "name": "Sam Altman",
        "description": "Building AGI @OpenAI. Investor. ex-YC president.",
        "location": "San Francisco",
        "url": "https://openai.com",
        "followers_count": 3200000,
        "friends_count": 900,
        "listed_count": 18000,
        "statuses_count": 6400,
        "favourites_count": 4100,
        "created_at": "Tue Apr 22 12:00:00 +0000 2008",
        "verified": True,
        "status": {
            "full_text": "We just shipped a huge update to our AI models. Try it and tell us what breaks.",
            "retweet_count": 2400,
            "favorite_count": 31000,
        },
    },
    {
        "screen_name": "dharmesh",
        "name": "Dharmesh Shah",
        "description": "Founder/CTO @HubSpot. I build SaaS and software for B2B marketers.",
        "location": "Boston, MA",
        "url": "https://hubspot.com",
        "followers_count": 480000,
        "friends_count": 2500,
        "listed_count": 7800,
        "statuses_count": 28000,
        "favourites_count": 12000,
        "created_at": "Wed Jun 11 09:30:00 +0000 2008",
        "verified": True,
        "status": {
            "full_text": "The best SaaS growth lever nobody talks about: making your free tier genuinely useful.",
            "retweet_count": 410,
            "favorite_count": 5200,
        },
    },
    {
        "screen_name": "saas_sally",
        "name": "Sally — SaaS Growth",
        "description": "Growth lead @ a Series B SaaS co. I write about PLG, onboarding, retention.",
        "location": "Austin, TX",
        "url": "https://sallysaas.substack.com",
        "followers_count": 24000,
        "friends_count": 1100,
        "listed_count": 320,
        "statuses_count": 9400,
        "favourites_count": 22000,
        "created_at": "Mon Feb 02 14:00:00 +0000 2015",
        "verified": False,
        "status": {
            "full_text": "Your activation metric is probably wrong. Measure the moment users feel the core value, not signup.",
            "retweet_count": 60,
            "favorite_count": 940,
        },
    },
    {
        "screen_name": "devjon",
        "name": "Jon | indie dev",
        "description": "Shipping a micro-SaaS in public. Python, FastAPI, a little React.",
        "location": "Remote",
        "url": "https://jonbuilds.dev",
        "followers_count": 3800,
        "friends_count": 600,
        "listed_count": 41,
        "statuses_count": 5200,
        "favourites_count": 8800,
        "created_at": "Sat Mar 19 10:00:00 +0000 2016",
        "verified": False,
        "status": {
            "full_text": "MRR update: crossed $1.2k this month. Slow but it compounds.",
            "retweet_count": 8,
            "favorite_count": 210,
        },
    },
    {
        "screen_name": "fitness_fran",
        "name": "Fran Lifts",
        "description": "Personal trainer. Strength, nutrition, no BS. Online coaching.",
        "location": "Miami, FL",
        "url": "https://franlifts.com",
        "followers_count": 61000,
        "friends_count": 800,
        "listed_count": 540,
        "statuses_count": 14000,
        "favourites_count": 30000,
        "created_at": "Thu Jan 14 08:00:00 +0000 2014",
        "verified": False,
        "status": {
            "full_text": "Progressive overload beats any supplement. Add 2.5kg, eat protein, sleep. That's it.",
            "retweet_count": 120,
            "favorite_count": 3300,
        },
    },
    {
        "screen_name": "crypto_carl",
        "name": "Carl ⛓️",
        "description": "DeFi degen. NFA. gm.",
        "location": "",
        "url": "",
        "followers_count": 14000,
        "friends_count": 6900,
        "listed_count": 60,
        "statuses_count": 41000,
        "favourites_count": 70000,
        "created_at": "Fri Nov 05 22:00:00 +0000 2021",
        "verified": False,
        "status": {
            "full_text": "This token is going to 100x trust me bro 🚀🚀",
            "retweet_count": 2,
            "favorite_count": 9,
        },
    },
    {
        "screen_name": "lurker_lee",
        "name": "Lee",
        "description": "",
        "location": "",
        "url": "",
        "followers_count": 38,
        "friends_count": 410,
        "listed_count": 0,
        "statuses_count": 12,
        "favourites_count": 90,
        "created_at": "Mon Sep 18 03:00:00 +0000 2023",
        "verified": False,
        "status": None,
    },
    {
        "screen_name": "promo_bot_9931",
        "name": "🔥 FOLLOW BACK 🔥",
        "description": "Follow 4 follow! DM for promo. Crypto signals 100% accurate!!!",
        "location": "",
        "url": "http://sketchy.link/promo",
        "followers_count": 1200,
        "friends_count": 4900,
        "listed_count": 1,
        "statuses_count": 88000,
        "favourites_count": 3,
        "created_at": "Wed Jan 03 01:00:00 +0000 2024",
        "verified": False,
        "status": {
            "full_text": "DM ME FOR PROMO 🔥🔥🔥 follow back guaranteed",
            "retweet_count": 0,
            "favorite_count": 0,
        },
    },
    {
        "screen_name": "pm_priya",
        "name": "Priya — Product",
        "description": "Senior PM in B2B SaaS. Ex-consultant. I tweet about roadmaps and discovery.",
        "location": "Seattle, WA",
        "url": "https://priyaproduct.com",
        "followers_count": 9200,
        "friends_count": 740,
        "listed_count": 110,
        "statuses_count": 4300,
        "favourites_count": 15000,
        "created_at": "Tue Jul 07 12:00:00 +0000 2017",
        "verified": False,
        "status": {
            "full_text": "Discovery isn't a phase, it's a habit. Talk to 3 customers this week even if you're shipping.",
            "retweet_count": 24,
            "favorite_count": 610,
        },
    },
    {
        "screen_name": "marketer_max",
        "name": "Max | Demand Gen",
        "description": "Demand gen for B2B SaaS. Paid, lifecycle, attribution. Coffee.",
        "location": "Chicago, IL",
        "url": "https://maxdemand.io",
        "followers_count": 17500,
        "friends_count": 1300,
        "listed_count": 230,
        "statuses_count": 11000,
        "favourites_count": 26000,
        "created_at": "Sun Apr 12 16:00:00 +0000 2015",
        "verified": False,
        "status": {
            "full_text": "Attribution is a model, not the truth. Pick one, stay consistent, and stop arguing about last-touch.",
            "retweet_count": 33,
            "favorite_count": 720,
        },
    },
]


def expand_mock(n: int) -> list[dict]:
    """Tile the base cast up to n followers, giving each clone a unique handle."""
    out: list[dict] = []
    i = 0
    while len(out) < n:
        base = MOCK_FOLLOWERS[i % len(MOCK_FOLLOWERS)]
        clone = dict(base)
        if i >= len(MOCK_FOLLOWERS):
            clone["screen_name"] = f"{base['screen_name']}_{i}"
        out.append(clone)
        i += 1
    return out[:n]
