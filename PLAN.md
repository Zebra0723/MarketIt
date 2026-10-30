# MarketIt — Final Plan

> **Scope update:** MarketIt now promotes **LEGO Ideas projects only**.
>
> - Posts cover milestones (100 / 250 / 500 / 1K, then every 1K up to 10K) and countdowns (30 / 7 / 1 days left), plus regular progress posts.
> - Every post includes the project's own photos from its LEGO Ideas page, shown uncropped and unaltered, and a link to support it.
> - The ads are minimal designs (`marketit/images/ads.py`).
>
> AI-generated images and non-LEGO items were removed. The rest of this plan still describes the architecture.

An automated, AI-driven system that markets anything you give it (products, services, apps, Lego Ideas projects, events, anything else) on social media. It costs nothing to run and needs almost no work from you.

## 1. How you use it

You add an item in one of two ways.

**A. Link mode (main way)**
- Paste a link to anything: a product page, a service, a Lego Ideas project, an app, a Kickstarter, a YouTube video, etc.
- Optionally add **notes** in plain English. The AI follows them as instructions, and they can say anything, for example:
  - "Check this Lego Ideas project every day and make a special post when we hit 1k supporters, and again at 5k and 10k."
  - "Aim at adult Lego fans, not kids."
  - "Don't mention the price."
  - "Stop promoting after December 31."
  - "Push hard this week, it's launch week."
- Pick an image mode:
  - `link`: use the images found at the link.
  - `ai`: AI-generated images.
  - `auto`: AI decides; the default.

**B. Manual mode**
- Fill in the details yourself: name, description, images, audience. The same notes and image options apply.

**Where you add items:** open a GitHub Issue using a ready-made form (link, notes, image mode). This works from your phone. MarketIt picks it up automatically and replies on the issue with what it understood. Manual mode can also be a YAML file in `items/`.

You can add **as many items as you like**. MarketIt rotates between them.

## 2. What the AI does on its own

For each new item:

1. **Reads the link.** It fetches the page and pulls out the title, text, images and key numbers. A headless browser handles pages that load content with JavaScript, like Lego Ideas.
2. **Identifies what it is.** For example: physical product, service, digital product, app, crowdfunding or Lego Ideas project, event, content, or other.
3. **Builds a profile.** It writes down the key facts, benefits, target audience and tone. All facts come only from the page and your notes, never invented.
4. **Chooses where and how often to market it.** It picks from the channels you've connected, based on what the item is and who it's for.
5. **Turns your notes into rules.** Content instructions shape every post. Recurring tasks become **watchers** (section 4).

Every run (daily, via GitHub Actions):

- Generates posts in several styles (problem/solution, behind-the-scenes, how-to, humor, urgency, milestone/celebration), shaped for each platform's length, hashtags and tone.
- Makes or selects images in the item's image mode and crops them for each platform.
- Publishes them.
- Collects likes, reposts and clicks, scores which styles work per channel and item type, and favors the winners next time while keeping about 20% exploration.

## 3. Approvals: full auto after the first 5

- The **first 5 posts** wait for your approval. Each appears as a GitHub Issue comment with the text and image; you reply `approve`, `reject`, or `edit: <new text>`.
- After 5 approvals, MarketIt runs **fully automatically**.
- `config.yaml` can change the number or turn approvals back on at any time.
- **Watcher posts are always automatic**, because milestones are time-sensitive.

## 4. Watchers (recurring tasks from your notes)

The AI converts notes like the Lego example into a structured task:

```yaml
watch:
  url: https://ideas.lego.com/projects/...
  every: daily
  metric: supporters
  triggers:
    - when: ">= 1000"   # fires once
      action: celebration post on all channels
    - when: ">= 5000"
      action: celebration post on all channels
    - when: "+100 in a day"
      action: momentum post
```

- On each run, MarketIt reads the current value from the page and compares it with the last stored value. Each trigger fires **exactly once**.
- Watchers work on any page with a number: supporters, backers, downloads, stars, days left, and so on.
- The value history is stored, so posts can say things like "we gained 300 supporters this week!"

## 5. Channels (social media only, no websites)

The AI posts only to channels you've connected, and decides which items go where.

| Channel | Good for | What you need (all free) | Fully automatic? |
|---|---|---|---|
| **Bluesky** | Reaching new people (hashtags, custom feeds) | Account + app password | Yes |
| **Mastodon** | Niche communities (hobby, tech, Lego/AFOL instances) | Account + access token | Yes |
| **Pinterest** | Products, crafts, Lego builds; long-lasting traffic | Business account + developer app approval | Yes, once approved |
| **Threads / Instagram / Facebook** | Big reach | Business/creator account + Meta developer app | Yes, after setup |
| **Telegram channel** | Followers you already have | Channel + bot from @BotFather | Yes |
| **Discord** | A community/server you already have | Server + webhook URL | Yes |
| **Reddit** | Big niche communities | — | **No.** Subreddit rules ban automated self-promotion and accounts get banned. The AI writes drafts you can post by hand. |
| **X (Twitter)** | — | Free API tier is very restricted | Optional, check limits first |

**Do you need Bluesky, Telegram and Discord accounts? No, you don't need all three.** You need **at least one channel**, and each channel you want needs its own free account. Note:

- **Telegram and Discord only reach people who already joined your channel or server.** They're useful once you have fans, but they won't find new people for you.
- **To reach new people, start with Bluesky, then add Pinterest and Mastodon.** These have free APIs and real discovery.
- Since you'll market many different things, use **one creator/brand account per platform** that posts all of them. The AI keeps the mix varied so it doesn't look like spam.

## 6. AI and image providers (free)

| Job | Default (free) | Alternatives |
|---|---|---|
| Reading pages, writing posts, following notes | Gemini API free tier | Groq free tier, local Ollama, Claude API (paid, optional) |
| AI images | Free-tier image model (e.g. Gemini or Cloudflare Workers AI) | Local Stable Diffusion; Pillow template cards as the always-free fallback |
| Image mode `link` | Images downloaded from the page, then resized/cropped | — |

Each provider sits behind a small interface, so switching is a config change. Free-tier limits change over time and are checked when each provider is built. In `auto` mode, AI images are never made to look like the real product, which would be misleading. They are used for mood/promo graphics, and real photos from the link are used to show the item itself.

## 7. Architecture

```
GitHub Issue (link + notes + image mode)  or  items/*.yaml
                    │
                    ▼
   ┌─────────────────────────────┐
   │ Intake: fetch page → identify│──► item profile + rules + watchers
   │ type → extract facts/images  │    (saved to data/items/)
   └──────────────┬──────────────┘
                  ▼   (daily GitHub Actions cron)
   ┌─────────────────────────────┐
   │ Watchers: check pages,       │──► milestone posts (always auto)
   │ fire triggers once           │
   ├─────────────────────────────┤
   │ Planner: pick items + channels│  rotation across all items,
   │ for today within post caps   │  per-channel daily limits
   ├─────────────────────────────┤
   │ Generator: text per platform │◄── learned style scores
   │ + images (link / ai / auto)  │
   ├─────────────────────────────┤
   │ Approval gate (first 5 only) │
   ├─────────────────────────────┤
   │ Publishers: Bluesky, Mastodon│
   │ Pinterest, Meta, Telegram,   │
   │ Discord                      │
   ├─────────────────────────────┤
   │ Analytics: fetch stats,      │──► style scores
   │ score styles                 │
   └─────────────────────────────┘
```

**Storage:** the repo itself holds items, posts, watcher values and stats as JSON, so there's no database to pay for.
**Secrets:** API keys are stored as GitHub Actions secrets and never committed.

## 8. Repo layout

```
MarketIt/
├── items/                     # manual-mode items (optional YAML files)
├── marketit/
│   ├── intake/                # fetch.py (incl. headless browser), issue_form.py, profile.py
│   ├── llm/                   # gemini.py, groq.py, ollama.py, claude.py, fake.py (tests)
│   ├── images/                # photos from the link, ai_gen.py, cards.py (templates)
│   ├── publishers/            # bluesky, mastodon, pinterest, threads, instagram, facebook, telegram, discord, x
│   ├── prompts.py             # every prompt sent to the AI
│   ├── watchers.py            # metric checks + milestone triggers
│   ├── planner.py             # what to post now, where
│   ├── generate.py            # platform-shaped posts, style tagging
│   ├── learning.py            # style + best-hour scoring
│   ├── approvals.py           # first-5 gate + issue comment commands
│   ├── runner.py              # prepare → publish → stats
│   └── cli.py                 # python -m marketit ...
├── data/                      # items/, queue/, posts/, media/, state.json (committed by the bot)
├── tests/
├── .github/
│   ├── ISSUE_TEMPLATE/add-item.yml
│   └── workflows/
│       ├── issues.yml         # new/edited/closed item issues + comment commands
│       ├── run.yml            # every 3h: prepare → push images → publish → stats
│       └── tests.yml
├── config.yaml                # channel caps, AI providers, approval count
└── PLAN.md
```

## 9. Build phases

**Phase 1 — Core**
- Issue form and intake: fetch, identify, extract facts and images
- Notes interpreter that turns notes into rules and watchers
- Gemini provider
- Generator, with images from the link plus template cards
- First-5 approval gate
- Bluesky publisher
- Daily workflow, plus a `--dry-run` CLI

**Phase 2 — Watchers and more channels**
- Watchers with milestone triggers (Lego Ideas tested first)
- Mastodon, Telegram and Discord publishers
- AI image generation

**Phase 3 — Getting smarter**
- Stats collection
- Style scoring and a feedback loop into the generator
- Best-time-to-post learning
- Multi-item rotation tuning

**Phase 4 — Big platforms**
- Pinterest, Threads, Instagram and Facebook, once developer app approvals come through
- Reddit draft suggestions

## 10. Guardrails

- Facts come only from the link and your notes; the AI never invents claims, reviews or numbers.
- Posting caps per channel per day; content is varied; there are no auto-DMs, auto-follows or mass replies.
- Notes can ask for anything, but the AI won't follow notes that break platform rules (e.g. spamming, fake accounts). It reports that on the item's issue instead.
- Each watcher trigger fires once, so a page glitch can't cause duplicate milestone posts.
- If anything fails (a dead link, an expired key, a rate limit), MarketIt comments on the item's issue, so you'll know.
