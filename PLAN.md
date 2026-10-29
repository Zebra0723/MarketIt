# MarketIt — Plan

An automated, AI-driven marketing system that promotes your products with no ongoing cost and close to no daily effort from you.

## 1. Goal

You describe each product once. MarketIt then, on a schedule:

1. Writes marketing content for it (posts, captions, product pages, emails).
2. Makes simple promo images.
3. Publishes to free channels.
4. Measures what worked and leans into it the next time.

You only step in to add products, and optionally to approve posts.

## 2. Guiding principles

- **$0 to run.** Use only free tiers, free APIs and free hosting. Every paid service must be optional and swappable.
- **AI does the work, you have the final say.** It starts in "draft + approve" mode and moves to full autopilot once you trust the output.
- **Play by platform rules.** No spam, no fake accounts, no fake reviews, and posting limits stay within each platform's terms. Getting banned costs more than any gain.
- **Pluggable.** Each AI model, channel and image tool sits behind a small interface, so swapping one is a single file change.

## 3. Architecture

```
            ┌──────────────┐
products/   │  Catalog     │  one YAML file per product (name, price, link,
  *.yaml ──►│  loader      │  photos, audience, key benefits, tone)
            └──────┬───────┘
                   ▼
            ┌──────────────┐     LLM provider (free tier / local)
            │  Content     │◄──  - Gemini / Groq free tiers, or
            │  generator   │     - Ollama running locally (fully free)
            └──────┬───────┘     - Claude API (paid, optional, best quality)
                   ▼
            ┌──────────────┐
            │  Image maker │  Pillow templates: product photo + headline
            └──────┬───────┘  + price badge → sized for each platform
                   ▼
            ┌──────────────┐
            │  Queue       │  drafts saved as JSON; approve via GitHub
            │  (+ approve) │  issue/PR or set AUTO_APPROVE=true
            └──────┬───────┘
                   ▼
            ┌──────────────┐  Bluesky · Mastodon · Telegram · Discord
            │  Publishers  │  · Pinterest · email newsletter · website
            └──────┬───────┘
                   ▼
            ┌──────────────┐  pull likes/clicks/reposts → score each
            │  Analytics   │  post's "angle" → feed the winners back
            │  + learning  │  into the generator prompt
            └──────────────┘

Scheduler: GitHub Actions cron (free) runs the whole pipeline daily.
Storage:   the git repo itself (catalog, queue, history, metrics as JSON).
```

## 4. Free channels, by priority

| Channel | Why | Automation |
|---|---|---|
| **Own website / product pages** (GitHub Pages) | Free hosting; SEO brings traffic for months | Full — AI writes the pages, Actions deploys them |
| **Bluesky** | Open, free API; easy to automate | Full |
| **Mastodon** | Open, free API | Full |
| **Telegram channel** | Free bot API; direct reach to followers | Full |
| **Discord** (your server) | Free webhooks | Full |
| **Pinterest** | Strong for products, links drive traffic | API needs app approval |
| **Email newsletter** (Buttondown / Brevo free tier) | Highest-converting channel you own | Full, within free-tier send limits |
| **Reddit** | Big reach, but strict self-promo rules | **Drafts only** — you post by hand |
| **Instagram / Facebook / TikTok** | Big reach | Business account + app review needed; later phase |
| **X (Twitter)** | Free API tier is very limited | Optional; check current limits first |

The free-tier limits for each service change over time. Check them when you build each publisher.

## 5. What the AI generates

For each product, on each run:

- **Several variants** of each post, each with a different angle (problem/solution, social proof, urgency, humor, behind-the-scenes, how-to).
- Platform-shaped copy: length limits, hashtags and tone per channel.
- An SEO product page (title, meta description, FAQ) for the website.
- A weekly newsletter roundup.
- Reddit/forum drafts that lead with value rather than an ad (approval only).

**Learning loop:** each post is tagged with its angle. Analytics scores the angles per channel, and the next prompt says, for example, "humor and how-to performed best on Bluesky last 2 weeks; favor those, keep 20% exploration."

## 6. Repo layout

```
MarketIt/
├── products/              # your catalog — the only thing you edit
│   └── example.yaml
├── marketit/
│   ├── catalog.py         # load + validate products
│   ├── llm/               # provider interface + gemini/groq/ollama/claude
│   ├── generate.py        # prompts, variants, angle tagging
│   ├── images.py          # Pillow promo-card templates
│   ├── queue.py           # drafts, approval state
│   ├── publishers/        # bluesky.py, mastodon.py, telegram.py, ...
│   ├── analytics.py       # fetch metrics, score angles
│   └── site/              # static product pages generator
├── data/                  # queue/, history/, metrics/ (JSON, committed)
├── .github/workflows/
│   ├── daily.yml          # generate → (approve) → publish
│   └── metrics.yml        # collect stats, update scores
└── config.yaml            # channels on/off, posting frequency, auto-approve
```

API keys are stored as **GitHub Actions secrets** and never committed.

## 7. Build phases

**Phase 1 — MVP**
- Product YAML schema and loader
- LLM provider interface plus one free provider
- Post generator with variants and angles
- Publishers for Bluesky, Telegram and Discord
- Approval queue, plus a `--dry-run` CLI mode
- Daily GitHub Actions workflow

**Phase 2 — Owned channels**
- Generated static site with SEO product pages on GitHub Pages
- Promo image generator
- Email newsletter integration
- Mastodon publisher

**Phase 3 — Getting smarter**
- Metrics collection per channel
- Angle scoring and a feedback loop into the prompts
- Best-time-to-post learning
- UTM links so website clicks can be traced to the post that drove them

**Phase 4 — Reach**
- Pinterest, then Instagram/Facebook via the Meta Graph API
- Reddit/community draft suggestions
- Optional local web dashboard to approve posts and view stats

## 8. Risks and how they're handled

| Risk | Mitigation |
|---|---|
| AI writes something wrong or off-brand | Approval mode by default; facts come only from the product YAML; banned-claims list |
| Looks spammy / account flagged | Posting caps per channel, varied content, value-first posts, real account only |
| Free tier changes or disappears | Pluggable providers; Ollama as a fully local fallback |
| Leaked API keys | GitHub secrets only; `.gitignore` for local `.env` |

## 9. Open questions

1. **What are you marketing?** Physical products, digital products, an app, or a service? This decides which channels go first.
2. **Where does the audience already hang out?** Pick the first 2–3 channels from that.
3. **Where should the "buy" link go?** Etsy, Shopify, Gumroad, eBay, your own site?
4. **Approval or autopilot from day one?**
