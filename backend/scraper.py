import os
import random
import datetime
import requests
from typing import List, Dict

class Scraper:
    def __init__(self):
        self.news_api_key = os.getenv("NEWSAPI_KEY")
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "SentioTrack/0.1")

    def scrape_news(self, query: str, limit: int = 20) -> List[Dict]:
        """Fetch news articles using NewsAPI, or fall back to mock data if key is missing/fails."""
        if not self.news_api_key or self.news_api_key.strip() == "":
            print("NewsAPI key missing. Generating mock news data.")
            return self._generate_mock_news(query, limit)

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": query,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": limit,
                "apiKey": self.news_api_key
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])
                results = []
                for art in articles:
                    published_str = art.get("publishedAt", "")
                    try:
                        published_at = datetime.datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except Exception:
                        published_at = datetime.datetime.utcnow() - datetime.timedelta(hours=random.randint(1, 48))

                    results.append({
                        "title": art.get("title") or "No Title",
                        "text": art.get("description") or art.get("content") or "",
                        "author": art.get("author") or "Staff Reporter",
                        "source": "news",
                        "url": art.get("url") or "",
                        "published_at": published_at
                    })
                if results:
                    return results
            print(f"NewsAPI returned status {response.status_code}. Generating mock news data.")
        except Exception as e:
            print(f"Error scraping NewsAPI: {e}. Generating mock news data.")
            
        return self._generate_mock_news(query, limit)

    def scrape_reddit(self, query: str, limit: int = 20) -> List[Dict]:
        """Fetch Reddit posts using PRAW, or fall back to mock data if credentials are missing/fails."""
        if not self.reddit_client_id or not self.reddit_client_secret:
            print("Reddit client credentials missing. Generating mock Reddit data.")
            return self._generate_mock_reddit(query, limit)

        try:
            import praw
            reddit = praw.Reddit(
                client_id=self.reddit_client_id,
                client_secret=self.reddit_client_secret,
                user_agent=self.reddit_user_agent
            )
            submissions = reddit.subreddit("all").search(query, limit=limit)
            results = []
            for sub in submissions:
                published_at = datetime.datetime.utcfromtimestamp(sub.created_utc)
                results.append({
                    "title": sub.title,
                    "text": sub.selftext or "",
                    "author": f"u/{sub.author.name}" if sub.author else "u/[deleted]",
                    "source": "reddit",
                    "url": f"https://reddit.com{sub.permalink}",
                    "published_at": published_at
                })
            if results:
                return results
        except Exception as e:
            print(f"Error scraping Reddit: {e}. Generating mock Reddit data.")
            
        return self._generate_mock_reddit(query, limit)

    def _generate_mock_news(self, query: str, limit: int) -> List[Dict]:
        """Generates realistic news headlines based on common topics."""
        q = query.lower()
        
        # Topic-specific mock databases
        topics_db = {
            "tesla": [
                {"title": "Tesla Announces Record Deliveries for Q2, Beating Wall Street Estimates", "text": "Tesla shares surged after the automaker reported delivery numbers that surpassed analyst expectations. Demand in China was key.", "sentiment": "positive"},
                {"title": "Consumer Reports Flags Safety Issues in Latest Autopilot Update", "text": "A new investigation raises concerns about Tesla's latest software release, citing sluggish reactions to road hazards.", "sentiment": "negative"},
                {"title": "Tesla Explores Sites for Next Gigafactory in Europe", "text": "Industry insiders report that Tesla is in discussions with government officials about building a new vehicle assembly plant.", "sentiment": "neutral"},
                {"title": "Elon Musk Outlines Strategy for Tesla's Next-Generation Cheap EV", "text": "In a post, the CEO hinted at a sub-$25,000 electric vehicle that could launch as early as next year, boosting investor sentiment.", "sentiment": "positive"},
                {"title": "Tesla Model Y Ranked Safest SUV in Recent Crash Test Audits", "text": "The crash safety rating organization awarded the Tesla Model Y the highest possible safety score in its annual assessment.", "sentiment": "positive"},
                {"title": "Tesla Recalls 120,000 Vehicles Over Rear Door Latch Defect", "text": "Federal regulators announced a recall affecting Model S and Model X vehicles due to a hazard where doors could unlatch during a crash.", "sentiment": "negative"}
            ],
            "bitcoin": [
                {"title": "Bitcoin Surpasses $90,000 as Institutional Inflow Reaches Record Highs", "text": "Cryptocurrency markets surged today with Bitcoin breaking through psychological resistance. Experts point to ETF demand.", "sentiment": "positive"},
                {"title": "SEC Launches New Investigation Into Major Crypto Exchange Operations", "text": "Regulatory pressure mounts as the SEC scrutinizes market manipulation and compliance in digital asset trades.", "sentiment": "negative"},
                {"title": "Central Bank Announces Digital Currency Pilot Program Details", "text": "The government released its official framework for CBDCs, claiming it will run alongside existing digital assets.", "sentiment": "neutral"},
                {"title": "MicroStrategy Acquires Additional $1.2 Billion Worth of Bitcoin", "text": "The enterprise software firm continued its aggressive treasury strategy, purchasing the asset at an average price of $88,200.", "sentiment": "positive"},
                {"title": "New Tech Upgrades Target Bitcoin Network's High Transaction Fees", "text": "Developers are proposing scaling solutions to lower costs and speed up peer-to-peer microtransactions.", "sentiment": "positive"},
                {"title": "Bitcoin Mining Energy Consumption Faces Heavy Backlash from Environmental Groups", "text": "A coalition of environmental advocates called for stricter green energy mandates on large-scale proof-of-work facilities.", "sentiment": "negative"}
            ]
        }

        # Select relevant templates or generate generic ones
        templates = []
        for key, val in topics_db.items():
            if key in q:
                templates = val
                break
                
        if not templates:
            # Generic templates for any search
            templates = [
                {"title": f"Why Investors Are Bullish on {query} This Quarter", "text": f"Market analysts expect {query} to outperform competitors due to strong adoption rates and strategic new leadership.", "sentiment": "positive"},
                {"title": f"New Report Details Significant Setbacks for {query} Development", "text": f"Technical hurdles and supply chain issues are stalling progress for {query}, leading to concerns about delayed timelines.", "sentiment": "negative"},
                {"title": f"Government Releases Regulatory Framework Affecting {query}", "text": f"A new policy guidelines draft outlines how companies operating in the {query} space must comply with safety regulations.", "sentiment": "neutral"},
                {"title": f"Strategic Partnership Expected to Accelerate {query} Adoption", "text": f"Two industry leaders announced a joint venture aimed at integrating {query} into commercial logistics systems.", "sentiment": "positive"},
                {"title": f"Data Breach Leaks Private Information Involving {query} Users", "text": f"Security researchers discovered an unsecured database exposing thousands of records associated with {query}.", "sentiment": "negative"},
                {"title": f"Industry Leaders Gather for Annual {query} Conference in New York", "text": f"The international summit kicked off today with discussions focusing on the future of the industry and emerging standards.", "sentiment": "neutral"}
            ]

        # Populate output
        results = []
        now = datetime.datetime.utcnow()
        for i in range(limit):
            # Rotate through templates and inject minor random variance
            tpl = templates[i % len(templates)]
            hours_ago = (i * 3) + random.randint(1, 10)
            published_at = now - datetime.timedelta(hours=hours_ago)
            
            results.append({
                "title": tpl["title"],
                "text": tpl["text"],
                "author": random.choice(["Sarah Jenkins", "Michael Chang", "Reuters Staff", "Bloomberg News", "TechCrunch Editor"]),
                "source": "news",
                "url": f"https://example.com/news/{q}-{i}",
                "published_at": published_at
            })
            
        return results

    def _generate_mock_reddit(self, query: str, limit: int) -> List[Dict]:
        """Generates realistic Reddit titles and self-text comments with internet slang."""
        q = query.lower()
        
        topics_db = {
            "tesla": [
                {"title": "Just took delivery of my Model Y, this thing is unreal! 🚗⚡", "text": "Honestly, after reading all the negative press I was nervous. But the acceleration, the tech, the build quality is flawless. Best purchase I've ever made.", "sentiment": "positive"},
                {"title": "Autopilot tried to merge into a concrete barrier today...", "text": "FSD Beta is getting worse with every patch. Almost had a heart attack on the I-95. Anyone else experiencing severe phantom braking?", "sentiment": "negative"},
                {"title": "Quick question on Model 3 charging speed limiters", "text": "Does charging to 100% every night on LFP batteries actually degrade the pack? The manual says one thing but people online say another.", "sentiment": "neutral"},
                {"title": "Tesla stock (TSLA) is absolutely ripping today, short squeeze?", "text": "Short sellers are getting absolutely wrecked right now. To the moon! HODL my brothers. $300 next week is not a meme.", "sentiment": "positive"},
                {"title": "Customer service at the service center was an absolute nightmare.", "text": "They kept my car for 4 days for a simple squeak, broke my cup holder, and then charged me $150 diagnostic fee. Terrible experience.", "sentiment": "negative"},
                {"title": "My custom vinyl wrap is finally done!", "text": "Decided to go with a matte emerald green finish. What do you guys think? Will post pictures soon.", "sentiment": "neutral"}
            ],
            "bitcoin": [
                {"title": "WE JUST CRUSHED $90k! LFG! 🚀🔥", "text": "I remember when everyone said Bitcoin was going to $10k. Bears are in absolute shambles. Keep stacking sats, this bull run is just getting started!", "sentiment": "positive"},
                {"title": "Is anyone else worried about the Tether audit reports?", "text": "It feels like we are playing musical chairs with a ticking time bomb. If USDT collapses, the whole market goes down. Talk me off the ledge.", "sentiment": "negative"},
                {"title": "Hardware wallet recommendations for long term storage?", "text": "Looking to move my coins off Coinbase. Should I get a Ledger, Trezor, or Coldcard? Looking for security first.", "sentiment": "neutral"},
                {"title": "Why you should never sell your Bitcoin. A long term macro analysis.", "text": "Inflation is eating fiat currency alive. Bitcoin is the only lifeboat. It's a digital property, not just a coin. Don't get shaken out.", "sentiment": "positive"},
                {"title": "Lost my seed phrase. I am officially ruined.", "text": "I kept it on a piece of paper in my drawer and my mom threw it out during spring cleaning. 2.4 BTC gone forever. Please learn from my mistake.", "sentiment": "negative"},
                {"title": "What percentage of your portfolio is in crypto?", "text": "Curious how aggressive you guys are. I'm currently about 15% BTC, 5% ETH, and the rest in standard index funds.", "sentiment": "neutral"}
            ]
        }

        templates = []
        for key, val in topics_db.items():
            if key in q:
                templates = val
                break
                
        if not templates:
            templates = [
                {"title": f"Why {query} is the future. Change my mind.", "text": f"Seriously, the fundamentals are just too strong. We are early adapters. 10x gains in 3 years is the base case. Bullish!", "sentiment": "positive"},
                {"title": f"I am so incredibly sick of hearing about {query}.", "text": f"Every single subreddit is spamming this garbage. It's an overhyped bubble and it's going to crash hard. Put your money in real assets.", "sentiment": "negative"},
                {"title": f"Simple discussion: What is the current state of {query}?", "text": f"Looking for unbiased pros and cons. Let's keep it civil in the comments. What are the key milestones for this year?", "sentiment": "neutral"},
                {"title": f"Absolutely crushing it today! {query} to the moon!", "text": f"Cannot believe the gains today. Buying more on the dip. Diamond hands, let's go!", "sentiment": "positive"},
                {"title": f"Huge warning: AVOID {query} at all costs.", "text": f"Losing money daily, dev team has gone silent, customer support is nonexistent. Scam vibes all over this.", "sentiment": "negative"},
                {"title": f"New update releases tomorrow for {query}", "text": f"Just saw the press release. They are rolling out a patch to fix minor bugs and add secondary language support. Read more here.", "sentiment": "neutral"}
            ]

        results = []
        now = datetime.datetime.utcnow()
        for i in range(limit):
            tpl = templates[i % len(templates)]
            hours_ago = (i * 2) + random.randint(0, 5)
            published_at = now - datetime.timedelta(hours=hours_ago)
            
            results.append({
                "title": tpl["title"],
                "text": tpl["text"],
                "author": f"u/{random.choice(['crypto_king', 'lambo_dreamer', 'throwaway992', 'tech_guru', 'zen_master', 'satoshi_disciple'])}",
                "source": "reddit",
                "url": f"https://reddit.com/r/{q}/comments/mock_{i}",
                "published_at": published_at
            })
            
        return results
