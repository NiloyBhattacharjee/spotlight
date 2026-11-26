<p align="center"><img src="logo.svg" width="128" alt="slopcannon logo"></p>

<h1 align="center">slopcannon</h1>

<p align="center">Makes short vertical videos and posts them to Instagram, Facebook, YouTube Shorts and TikTok on a schedule.</p>

slopcannon is one Python script, `slopcannon.py`. Claude writes the script for each reel through the Claude Code CLI, so you need no API key. Every reel is labelled as AI-generated wherever the platform's API allows it.

## What it makes

| Mode | Command | What you get |
|---|---|---|
| Trivia | `python slopcannon.py` | An infographic reel of surprising facts, narrated with Edge TTS. |
| Variety | `python slopcannon.py --variety` | A different listicle each run: would you rather, red flags, ranked, fake or real, unpopular opinions or nobody tells you. It never repeats the last two formats. |
| SCP lore | `python slopcannon.py --scp` or `--scp SCP-173` | A random SCP article rated 100 or more, told as a memory by someone who was there: a retired researcher, a former guard, a surviving D-class. The narrator sounds like a real person, exhausted and sad and still scared of it, on a tape that skips and crackles between words, from Orpheus running locally on the graphics card (Chatterbox, then Kokoro, if it isn't set up), over a synthesized suspense drone with a heartbeat. mockingbird draws it as a recovered VHS tape (`scp_motion.html`): strange line drawings Claude makes of the thing for each reel, traced on black and tearing with the tape, each line typed as a subtitle as it's spoken, and the pop-up captions flashed in red. Without mockingbird it falls back to plain cards. Articles come from the SCP dataset at scp-data.tedivm.com, and every reel credits the author under CC BY-SA 3.0. |
| Reddit stories | `python slopcannon.py --reddit` | A popular drama or revenge post retold in Claude's own words over gameplay footage from `bg/`. It is credited "Based on a story by u/… on r/…". |
| Classic books | `python slopcannon.py --book` or `--book "White Nights"` | A story reel in the style of TED-Ed about a public-domain classic. It has flat-vector art from Cloudflare Workers AI (Pollinations if Cloudflare isn't set up), a Kokoro narrator that matches the story's mood (sombre, eerie, tense, tender or wry), ambience for the setting (rain, snow, mist, embers or dust), and a motion layer drawn by mockingbird (`book_motion.html`). The final mix is levelled to −14 LUFS. |
| Business promos | `python slopcannon.py --brand new mitu <website or file>`, then `--brand mitu` | Promo reels for any business. The first command has Claude draft `brands/mitu.md`, a marketing brief (what it does, who it's for, proof, offers, call to action, tone, colours, what never to say) from its website, a file or a description; you check it once. Each run then picks a format the page hasn't had lately (problem then fix, an acted-out chat, three reasons, one number, before and after, a spotlight, a real review), writes a 20 to 35 second script that claims only what the brief says, and mockingbird draws it in the business's colours (`brand_motion.html`) with captions and an upbeat music bed. Acted-out chats are labelled as dramatised. A business's reels post only to the pages in its own `mitu.env`. |
| Test | `python slopcannon.py --demo` | A built-in trivia sample. It makes no API calls and posts nothing. |

Add `--dry-run` to build a reel without posting it. Finished reels go to `out/<date_time>/reel.mp4`.

## Setup

You need:

- Python 3.12 or later: `pip install edge-tts requests pillow pydantic`
- **ffmpeg** on your PATH
- **Claude Code**, signed in (`claude -p` must work)
- Optional, for book reels:
  - **Kokoro**, for the narrator. It needs Python 3.10 to 3.12:
    ```
    py -3.11 -m venv .venv-kokoro
    .venv-kokoro/Scripts/pip install kokoro soundfile en_core_web_sm@https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
    ```
  - **mockingbird**, for the motion layer. Without it, book reels get plain burnt-in captions.
- Optional, for Reddit reels: gameplay clips in `bg/`.

## Posting

Each page (account) has its own settings file. To set one up, copy `page.env.example` to `books.env` or `stories.env`, fill in the platforms you use, and pass the file with `--env books.env`. A page's file replaces the platform settings in your environment, so a reel never lands on the wrong page.

| Platform | Settings | One-time step |
|---|---|---|
| Instagram and Facebook | `IG_USER_ID`, `IG_TOKEN`, `FB_PAGE_ID`, `FB_PAGE_TOKEN` | Run `python slopcannon.py --meta` with a Meta system user token. It prints all four values for each of your Pages. |
| YouTube | `YT_CLIENT_ID`, `YT_CLIENT_SECRET` (a Desktop OAuth client) | `python slopcannon.py --env books.env --login youtube` |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI` | `python slopcannon.py --env books.env --login tiktok`. Posts stay private (`TIKTOK_PRIVACY=SELF_ONLY`) until TikTok audits the app. |
| Book art | `CF_ACCOUNT_ID`, `CF_API_TOKEN` (the Workers AI token template) | None |

A platform with missing settings is skipped. If one platform fails, the others still post.

Settings files, sign-in tokens and post logs (`*.env`, `*.tokens.json`, `*.posts.json`, `logs/`) are kept out of git.

## Schedule

Run `schedule.ps1` once, in PowerShell, to register two Windows Task Scheduler jobs:

| Task | Command | Times |
|---|---|---|
| `slopcannon books` | `--book --env books.env` | 10:40 and 18:40 |
| `slopcannon stories` | `--reddit --env stories.env` | 12:55 and 20:55 |
| `slopcannon scp` | `--scp --env scp.env` | 16:50 and 22:50 |

Each job catches up after the PC was asleep, wakes the PC to run, and retries twice. Output goes to `logs/<page>.log`.

## Learning from views

Every posted reel is logged. Before each run, slopcannon pulls Instagram's views, reach, shares, saves and average watch time for reels posted 1 to 30 days ago. It tells Claude which reels did best and worst before Claude picks the next topic.

## Promo reels for Mitu

`promo/mitu/` holds five 25 to 32 second promo reels for [Mitu](https://github.com/NiloyBhattacharjee/MITUai), an AI assistant for shops that sell in DMs. They're in `promo/mitu/reels/`:

| Reel | Hook |
|---|---|
| `mitu_3am_english.mp4` | "It's 3 AM. 14 people just asked "price?"" |
| `mitu_3am_bangla.mp4` | The same reel, in Bangla. |
| `mitu_screenshot_order.mp4` | "Typing the same price 200 times a day?" A customer sends a screenshot, and Mitu takes a bKash order. |
| `mitu_cafe.mp4` | "Your barista can't pour and text." A coffee order placed by voice note, and an honest allergen answer. |
| `mitu_voice_note.mp4` | "Your customers don't type." A kurti ordered entirely by voice notes. |

Each reel is a WhatsApp-style chat drawn on a canvas. The chats and prices come from Mitu's landing page and demo shops. The customer voice notes in `voices/` are Edge TTS voices, so they're AI-generated. Replace those files with real recordings if you have them.

To change a reel or add one:

1. Edit `promo/mitu/mitu_data.js`. Each reel has a hook, a few chat lines, cards that pop up, and an end card. `node mitu_data.js` prints each reel's length.
2. Make the pages: in Git Bash, from `promo/mitu`, run
   `for k in en bn photo cafe voice; do mkdir -p build/$k; sed "s#/\*REEL\*/\"en\"#\"$k\"#" mitu.html > build/$k/reel.html; done`
3. Give each reel a `build/<reel>/music.wav`, made with mockingbird's `music` tool (`corporate.js`, or `lofi.js` for the café) and as long as the reel.
4. Render with mockingbird's `motion` tool: `script` is `build/<reel>/reel.html`, `size` is `1080x1920`, `fps` is 30, and `duration` is the length from step 1.

`build/` is kept out of git.
