# MarketIt

MarketIt markets anything you give it on social media, automatically and for free.

You give it a link (a product, a service, an app, a Lego Ideas project, a Kickstarter, anything) and optional notes. The AI works out what the link is and who it's for, writes posts in the right style for each platform, makes or picks images, and posts on a schedule. Over time it learns which kinds of posts get the most engagement.

It runs entirely on **GitHub Actions** (free), uses **free AI tiers**, and stores everything in this repo, so there is no server and no database.

---

## Setup

### 1. Let the workflows save their work
In this repo, go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**, then save.

Make sure this code is on your **default branch** (usually `main`). GitHub only runs scheduled workflows from the default branch.

### 2. Add a free AI key
1. Get a free Gemini key at <https://aistudio.google.com/apikey>.
2. In this repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
3. Name it `GEMINI_API_KEY` and paste the key.

Optional backup: add a free `GROQ_API_KEY` from <https://console.groq.com/keys>. MarketIt switches to it automatically if Gemini hits its free limit.

### 3. Connect at least one channel
Add the secrets for the channels you want; see the [channel table](#channels) below. **Bluesky is the easiest way to reach new people**, so start there:

1. Create an account at <https://bsky.app>.
2. Go to **Settings → Privacy and security → App passwords** and create an app password.
3. Add two secrets: `BLUESKY_HANDLE` (e.g. `yourname.bsky.social`) and `BLUESKY_APP_PASSWORD`.

### 4. Market something
Go to **Issues → New issue → 📣 Market something**:

- **Link:** paste a link.
- **Notes (optional):** anything in plain English. For example: *"Check this Lego Ideas project every day and make a special post when we hit 1k supporters, then 5k and 10k. Aim at adult Lego fans."*
- **Images:** choose one:
  - `auto` (default): the AI decides.
  - `link`: use the photos from the page.
  - `ai`: AI-generated images.

Within a minute or two MarketIt replies on the issue with what it understood:
- what the item is and who it's for
- which channels it will use
- the rules it took from your notes
- the watchers it set up
- any notes it won't follow, and why
- a couple of Reddit drafts

### 5. Approve your first 5 posts
The first 5 posts are commented on the issue for you to check. Reply with one of:

- `approve P1A2B3`
- `reject P1A2B3`
- `edit P1A2B3: better text here`
- `approve all`

After 5 approvals MarketIt runs on its own. Milestone posts from watchers never wait for approval. To change the number of approvals, edit `approvals.first_n` in `config.yaml`.

---

## Day to day

MarketIt runs every 3 hours. On each run it:
1. Checks watchers.
2. Decides which channels are due to post.
3. Picks the item that has waited longest for each due channel.
4. Writes and publishes the posts.

It also collects likes, reposts and replies once a day and learns which styles and posting hours work best on each channel. Every few posts it still tries a different style, so it keeps learning.

**Commands** (comment on an item's issue):

| Comment | What it does |
|---|---|
| `pause` / `resume` | Stop or restart posting about this item |
| `stop` | Stop for good (closing the issue does the same) |
| `status` | Recent posts with their likes, plus watcher readings |
| `notes: …` | Add more instructions; the AI re-reads everything |

Editing the issue (the link or notes) updates the item.

**Watchers** come from your notes, for example *"check daily"*, *"post when we hit 1k supporters"*, *"every 1000 backers"* or *"when it gains 100 in a day"*. They read the number on the page on that schedule. Each milestone posts **once**. Milestones you've already passed when the watcher is set up don't trigger a post. A sudden implausible jump or drop is ignored until the next check confirms it.

---

## Channels

| Channel | Secrets to add | How to get them |
|---|---|---|
| **Bluesky** | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Settings → Privacy and security → App passwords |
| **Mastodon** | `MASTODON_BASE_URL` (e.g. `https://mastodon.social`), `MASTODON_ACCESS_TOKEN` | Preferences → Development → New application (scopes `read` + `write`) → copy the access token |
| **Pinterest** | `PINTEREST_ACCESS_TOKEN`, `PINTEREST_BOARD_ID` | Business account + an app at <https://developers.pinterest.com> (app review required) |
| **Threads** | `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` | Meta developer app with the Threads API. Needs public image URLs (see below) |
| **Instagram** | `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN` | Business/creator account linked to a Facebook Page, Meta developer app. Needs public image URLs |
| **Facebook Page** | `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN` | Meta developer app → Page access token |
| **Telegram** | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (e.g. `@mychannel`) | Create a bot with @BotFather and make it an admin of your channel |
| **Discord** | `DISCORD_WEBHOOK_URL` | Server Settings → Integrations → Webhooks → New Webhook → Copy URL |
| **X** | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | Developer portal. The free tier is very limited, so X is off by default in `config.yaml` |

Notes on reach and setup:

- **Telegram and Discord only reach people who already follow you.** Bluesky, Mastodon and Pinterest are where new people find you.
- **Reddit is not automated on purpose.** Subreddits ban automated self-promotion. MarketIt writes Reddit drafts for you to post by hand.
- **Instagram and Threads fetch images from a URL.** In a **public** repo this works automatically. In a private repo, set `media.public_base_url` in `config.yaml`, or don't use those two channels.
- Meta and Pinterest **developer app reviews** can take a while. Start with Bluesky while you wait.

Run `python -m marketit doctor` to see what's connected.

---

## Images

- **`link`**: photos from the page, cropped and compressed for each platform. Only use photos you have the right to use. For your own products or projects, you're fine.
- **`ai`**: free AI art from [Pollinations](https://pollinations.ai), which needs no account. To use Cloudflare Workers AI instead, set `images.ai_provider: cloudflare` and add `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`. AI art is used as mood or promo art, never passed off as the real product.
- **`auto`**: real photos when the page has any, sometimes as a branded card with a headline and price. Uses AI art when there are no photos.
- If an image service is down, MarketIt draws a clean template card instead. Milestones get a celebration card, e.g. "1,000 SUPPORTERS!".

---

## The manual way

If there's no link, use the issue form's **Manual details** box. You can also add a YAML file to `items/`:

```yaml
# items/candle.yaml
name: Lavender Candle
description: Hand-poured soy candle, burns 40 hours.
price: $12
where_to_buy: Etsy shop "CozyWicks"
link: https://example.com/candle      # optional
notes: Cozy autumn vibes. Push harder in December.
image_mode: link                      # auto | link | ai
images:                               # optional: URLs or paths in this repo
  - items/photos/candle1.jpg
active: true                          # false = paused
```

MarketIt picks up new or changed files on its next run.

---

## Settings (`config.yaml`)

- **AI providers:** which ones to use, in fallback order, and which model each uses. Claude (paid) is supported if you add `ANTHROPIC_API_KEY`.
- **`daily_cap`:** posts per day for each channel.
- **`explore_rate`:** how often MarketIt tries a non-winning style.
- **Approvals:** how many posts need your approval before it goes fully automatic.
- **Media:** whether to make Reddit drafts, the Meta Graph API version, the public media URL, and how many days to keep images.

---

## Running on your own computer

```bash
pip install -r requirements.txt
```

```bash
export GEMINI_API_KEY=...
```

Add an item (`--notes` and `--images` are optional):

```bash
python -m marketit add https://ideas.lego.com/projects/... --notes "post at 1k supporters" --images auto
```

See sample posts for every channel without posting anything:

```bash
python -m marketit preview
```

Check watchers, write posts and publish what's ready:

```bash
python -m marketit run
```

Show items, the queue and connected channels:

```bash
python -m marketit status
```

Approve a waiting post (`--reject` and `--text "..."` also work):

```bash
python -m marketit approve P1A2B3
```

Try everything without any keys using `--fake-ai`:

```bash
python -m marketit --fake-ai add --manual "name: Test thing"
```

For Ollama (free, runs on your machine), set `OLLAMA_HOST=http://localhost:11434`.

Run the tests:

```bash
pip install pytest && python -m pytest
```

---

## Costs and limits

- **GitHub Actions:** free for public repos. Private repos get 2,000 free minutes a month, and a run takes about 2–3 minutes. Running every 3 hours uses roughly 500–700 minutes a month.
- **Free AI tiers** have daily limits. MarketIt uses about 1–2 AI calls per post, which is well within them for normal use.
- **Scheduled workflows in public repos** are paused by GitHub after 60 days with no repo activity. MarketIt's own commits count as activity.

## Safety

- Facts come only from the link and your notes. The AI is told never to invent prices, reviews or numbers.
- Page content is treated as untrusted data, so instructions hidden in a web page are ignored.
- Only the repo owner, members and collaborators can add items or approve posts. Issues from strangers on a public repo are ignored.
- Secrets live in GitHub Secrets and are removed from logs and issue comments.
- MarketIt caps posts per channel per day and varies its posts. It never DMs, auto-follows or mass-replies.

See [PLAN.md](PLAN.md) for the design.
