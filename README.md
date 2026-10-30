# MarketIt

MarketIt promotes **LEGO Ideas projects** on social media, automatically and for free.

Paste a LEGO Ideas project link. MarketIt then:

- reads the project's photos, supporters, days left and creator;
- posts on a schedule with a clean, minimal ad built around the project's own photos, plus the photos themselves and a link to support the project;
- celebrates every milestone (100, 250, 500, 1K, then every 1K up to 10K) and counts down the final days.

It runs entirely on **GitHub Actions** (free), uses **free AI tiers**, and stores everything in this repo.

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

### 4. Add your project
Go to **Issues → New issue → 🧱 Promote a LEGO Ideas project**:

- **LEGO Ideas link:** e.g. `https://ideas.lego.com/product-ideas/…`
- **Notes (optional):** anything in plain English. For example: *"Aim at castle fans. Mention the working drawbridge. Also celebrate 1,500 supporters."*

Within a minute or two MarketIt replies on the issue with what it understood:
- the current supporters and days left
- how many project photos it found
- the milestones and countdowns it will post about
- which channels it will use
- the rules it took from your notes, and any it won't follow (with why)
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

MarketIt runs every hour. On each run it:
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

**Milestones** come built in: 100, 250, 500, 1K, then every 1K up to 10K (LEGO review), plus countdown posts at 30, 7 and 1 days left. You can add more in your notes, e.g. *"also celebrate 1,500"*, or change the defaults under `lego:` in `config.yaml`.

- MarketIt reads the project page every 6 hours.
- Each milestone posts **once**. Milestones you'd already passed before adding the project are skipped.
- If one check jumps past several milestones, only the biggest gets a post.
- A sudden implausible drop in supporters is ignored until the next check confirms it.

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

## The ads

Every post has a designed ad: minimal, lots of white space, Inter typography, one accent colour. There are four layouts:

| Layout | Used for |
|---|---|
| **Milestone** | "1,000 supporters", with what the milestone means (e.g. "Extra time unlocked", "Headed to LEGO review") |
| **Countdown** | "7 days left", plus the next supporter goal |
| **Progress** | A headline about the build, live stats (supporters / to next goal / days left) |
| **Gallery** | Three of the project's photos plus a headline |

Every ad shows progress toward 10,000 and ends with **"Support it on LEGO Ideas"** and the project link.

**Photos:** MarketIt only uses the exact photos from the project's LEGO Ideas page. They're shown whole: never cropped, filtered, drawn over or replaced with AI images, only scaled to fit. On Bluesky, Mastodon, Telegram and Discord, posts also include up to 3 of the project's photos as the original files (only scaled down if a platform's size limit requires it). If MarketIt can't find any photos on the page, it doesn't post. It tells you why instead.

To see sample posts and ads without posting anything:

```bash
python -m marketit preview
```

The ads are saved to `data/media/`.

---

## Adding projects without an issue

You can also add a project as a YAML file in `items/`:

```yaml
# items/castle.yaml
link: https://ideas.lego.com/product-ideas/…
notes: Aim at castle fans. Also celebrate 1,500 supporters.
active: true          # false = paused
```

---

## Settings (`config.yaml`)

- **AI providers:** which ones to use, in fallback order, and which model each uses. Claude (paid) is supported if you add `ANTHROPIC_API_KEY`.
- **`lego`:** milestones, countdown days, how often to check the page, posts per week.
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

Add a project (`--notes` is optional):

```bash
python -m marketit add https://ideas.lego.com/product-ideas/... --notes "aim at castle fans"
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

Try it without an AI key using `--fake-ai`:

```bash
python -m marketit --fake-ai add https://ideas.lego.com/product-ideas/...
```

For Ollama (free, runs on your machine), set `OLLAMA_HOST=http://localhost:11434`.

Run the tests:

```bash
pip install pytest && python -m pytest
```

---

## Costs and limits

- **GitHub Actions:** free for public repos. Private repos get 2,000 free minutes a month, and a run takes about 2–3 minutes. Running every hour uses roughly 500–700 minutes a month.
- **Free AI tiers** have daily limits. MarketIt uses about 1–2 AI calls per post, which is well within them for normal use.
- **Scheduled workflows in public repos** are paused by GitHub after 60 days with no repo activity. MarketIt's own commits count as activity.

## Safety

- Facts come only from the project page and your notes. The AI is told never to invent piece counts, features or numbers, and never to imply LEGO made or endorses the project.
- Page content is treated as untrusted data, so instructions hidden in a web page are ignored.
- Only the repo owner, members and collaborators can add items or approve posts. Issues from strangers on a public repo are ignored.
- Secrets live in GitHub Secrets and are removed from logs and issue comments.
- MarketIt caps posts per channel per day and varies its posts. It never DMs, auto-follows or mass-replies.

See [PLAN.md](PLAN.md) for the design.
