"""Daily reels -> AI voice -> Instagram, Facebook, YouTube and TikTok. Modes: trivia infographics, narrated Reddit stories, or animated stories of classic books.

Claude runs through the Claude Code CLI (`claude -p`, your Claude login), so no API key is needed.
Posting goes to every platform that is set up (env vars; one failing doesn't stop the others):
  Instagram  IG_USER_ID, IG_TOKEN (instagram_basic, instagram_content_publish, instagram_manage_insights)
  Facebook   FB_PAGE_ID, FB_PAGE_TOKEN (pages_show_list, pages_read_engagement, pages_manage_posts)
             With a Meta system user token: python reelbot.py --meta  prints all four for each of your Pages
  YouTube    YT_CLIENT_ID, YT_CLIENT_SECRET (a Desktop OAuth client), then once: python reelbot.py --login youtube
  TikTok     TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI, then once: python reelbot.py --login tiktok
             TIKTOK_PRIVACY defaults to SELF_ONLY: TikTok allows only private posts until the app passes its audit
  Two pages, one niche each: put a page's settings in an env file (copy page.env.example) and pass --env books.env.
  Its platform settings replace the environment's, so a reel never lands on the other page; its YouTube/TikTok
  sign-ins go to books.tokens.json. schedule.ps1 runs each page on its own daily times.
  Feedback loop: every posted reel is logged (books.posts.json); each run pulls Instagram's views, average watch
  time and shares for reels 1-30 days old and tells Claude what did best and worst before it picks the next one.
  python reelbot.py              trivia infographic reel, posted
  python reelbot.py --reddit     drama/revenge Reddit story reel (r/AmItheAsshole, r/pettyrevenge, ...), posted
  python reelbot.py --book       animated story of a public-domain classic, told TED-Ed style, posted
  python reelbot.py --book "White Nights"   the same, for a book you choose
  --book draws its motion layer (book_motion.html: title, captions, mist, light) with mockingbird when installed,
  else burns plain captions in.
  add --dry-run to build without posting
  --book narrates with Kokoro (open-source, local) in the story's mood once set up, else Edge. Needs Python 3.10-3.12:
    py -3.11 -m venv .venv-kokoro
    .venv-kokoro/Scripts/pip install kokoro soundfile en_core_web_sm@https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
  python reelbot.py --demo       render a built-in trivia sample (no API calls) to test the pipeline
"""
import asyncio, base64, html, io, json, os, random, re, shutil, subprocess, sys, time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import edge_tts, requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel
from typing import Literal

HERE = Path(__file__).parent
VOICE = "en-US-AndrewMultilingualNeural"  # newer, more human voices: Andrew/Ava/Emma/BrianMultilingualNeural
RATE = "+20%"  # faster reads rushed and robotic
# voice polish: cut rumble, gentle compression for a fuller, steadier voice, then Instagram's -14 LUFS loudness
VOICE_FX = "highpass=f=70,bass=g=2:f=160,treble=g=-2:f=7000,acompressor=threshold=-20dB:ratio=3:attack=5:release=150:makeup=2,loudnorm=I=-14:TP=-1.5:LRA=7"
GRAPH = "v24.0"
W, H, PAD = 1080, 1920, 90
BOLD, REG = "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf"
BG, FG, ACCENT, MUTED = "#0f1729", "#f5f1e8", "#f4b942", "#8f9bb3"
# one niche (drama and revenge) so Instagram learns who to show the account to
SUBS = ["AmItheAsshole", "AITAH", "pettyrevenge", "ProRevenge", "MaliciousCompliance", "EntitledPeople",
        "TrueOffMyChest"]
MIN_WORDS, MAX_WORDS = 60, 1500  # source post length; Claude retells it in 150-300 words (about 60-110 s)
TOP_WINDOW = "all"  # most upvoted of: hour, day, week, month, year, all
# book reels: each one picks an animation style. art is the look of every illustration; fps is the camera's frame
# rate (12 stutters like stop-motion); zoom how far each move travels; shake a hand-moved jitter in pixels; cut the
# ffmpeg xfade between shots; glow a soft light at the top of the frame.
STYLES = {
    "flat vector": dict(art="flat 2D vector illustration in the style of an educational animated short, clean simple "
                            "shapes, limited muted palette, soft gradients, subtle paper grain, minimal detail, "
                            "characters with simple faces",
                        fps=30, zoom=0.06, shake=0, cut="fade", glow=False),
}
AIRS = ("mist", "snow", "rain", "embers", "dust", "none")  # drawn over every shot by book_motion.html
# how the narrator sounds, per story: Kokoro's speed, how long the silences between sentences are, how far the voice
# is lowered (rubberband: same speed and formants, so it stays one person and the captions stay in sync), and a
# faint room echo for the creepypasta feel.
MOODS = {
    "somber": dict(speed=0.95, pause=1.2, pitch=0.94, room=False),   # loss, death, regret
    "eerie": dict(speed=0.92, pause=1.3, pitch=0.91, room=True),     # horror, the uncanny: a creepypasta narrator
    "tense": dict(speed=1.05, pause=0.85, pitch=0.97, room=False),   # crime, danger, a chase
    "tender": dict(speed=0.97, pause=1.1, pitch=0.97, room=False),   # love, longing
    "wry": dict(speed=1.05, pause=0.9, pitch=1.0, room=False),       # satire, comedy, irony
}
KOKORO_PY = HERE / ".venv-kokoro" / "Scripts" / "python.exe"
KOKORO_VOICE = "am_onyx"  # deep American male; also try am_fenrir, bm_lewis or bm_george (b = British)
MOCKINGBIRD = Path.home() / ".mockingbird" / "bin" / "mockingbird.cmd"
MUSIC = HERE / "music"  # drop royalty-free tracks here (Pixabay Music, YouTube Audio Library); empty = synth drone


# ---------- Claude ----------

def ask(prompt: str, schema):
    """Structured answer from Claude via the Claude Code CLI, using your Claude login instead of an API key.
    --tools "" turns off every tool: the prompt carries untrusted Reddit text, so Claude may only answer."""
    exe = shutil.which("claude")
    if not exe:
        sys.exit("Claude Code CLI not found: install it and run `claude` once to log in")
    r = subprocess.run([exe, "-p", "--model", "sonnet", "--output-format", "json", "--json-schema", json.dumps(schema.model_json_schema()),
                        "--tools", "", "--strict-mcp-config", "--no-session-persistence"],
                       input=prompt, capture_output=True, text=True, encoding="utf-8")
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude failed ({r.returncode}): {r.stderr or r.stdout}") from None
    if out.get("is_error") or not out.get("structured_output"):
        raise RuntimeError(f"generation failed: {out.get('subtype')} {out.get('result')}")
    return schema.model_validate(out["structured_output"])


class Slide(BaseModel):
    big: str        # headline number, e.g. "8 min 20 s"
    text: str       # one short sentence shown on screen
    narration: str  # what the voice says on this slide


class Post(BaseModel):
    topic: str
    title: str
    hook: str       # narration for the title slide
    slides: list[Slide]
    caption: str


class Scene(BaseModel):
    narration: str  # 1-2 sentences of the script
    art: str        # the illustration on screen while it is spoken


class Film(BaseModel):
    topic: str      # "<book> by <author>", for the history list
    style: Literal[tuple(STYLES)]
    air: Literal[AIRS]
    mood: Literal[tuple(MOODS)]
    hook: str       # on-screen text over the opening seconds
    title: str
    author: str
    year: str       # first published
    scenes: list[Scene]
    caption: str


class Story(BaseModel):
    id: str         # chosen post id, or "" if none are suitable
    title: str
    story: str      # retold in Claude's words, not the author's
    caption: str


def generate(history: list[str]) -> Post:
    return ask(f"""You make Instagram Reel infographics about history and science trivia.
Pick ONE specific, surprising topic. Do not repeat any of these past topics: {history[-60:] or "none yet"}.

- title: max 7 words, curiosity-driven.
- hook: one spoken sentence (under 15 words) that makes people keep watching.
- slides: 4 or 5, each built around one striking number. "big" is that number with its unit (max 12 characters),
  "text" is one sentence under 18 words, "narration" is 1-2 conversational spoken sentences.
- Use only well-established, verifiable facts. If a figure is an estimate, say "about".
- caption: a hook line, one line of context, then 6-8 relevant hashtags.""", Post)


def generate_film(history: list[str], book: str | None = None, feedback: str = "", recent_styles=()) -> Film:
    pick = f"The book is {book}." if book else (
        "Pick ONE classic book published before 1929 that people have heard of but not read, with a story that makes "
        "people stop scrolling: obsession, betrayal, crime, madness, survival, forbidden love, or an author whose "
        "own life was as wild as the book.")
    return ask(f"""You write narration for short animated Instagram Reels that make people fall for classic books, the
way a great storyteller would tell one to a friend. {pick} Do not repeat any of these past topics:
{history[-60:] or "none yet"}.

The script is 110-150 words (45-60 seconds spoken; shorter reels get watched to the end, which is what spreads
them) and tells a story; it is not a summary or a list of lessons:
- The first sentence must stop a scroll within two seconds: open cold inside the book's most shocking or vivid
  moment, in the present tense, as if it is happening now, like "Mounting his skinny steed, the protagonist of
  Don Quixote charges an army of giants." No greeting, no "in this video", no slow scene-setting.
- Then pull back, as a twist rather than a resume: how this book came to exist, the author's surprising life or
  times. Name the book and author naturally mid-story, never as "This is X by Y".
- What made it daring in its day, and its heart: the characters, shown through concrete moments, not morals.
- End on a line that lingers: something true about people, said simply, maybe turned back on the viewer. No
  call to action, no lecture.

The voice is everything. Write like someone leaning in to tell a friend a story they can't stop thinking about,
not a documentary narrator and not an essay:
- Warm, a little conspiratorial, wry where the story allows. Contractions (he's, didn't, she'd).
- Rhythm: a long rolling sentence, then a short punch. Fragments are fine. So is starting with "And" or "But".
- Once or twice, talk to the viewer directly or ask the question they're already asking ("You'd think he'd run.
  He doesn't.", "Would you have waited?").
- Senses over adjectives: the cold of the railing, the smell of the river, the sound of the drum before the volley.
- Dashes and "..." where a speaker would pause for effect, sparingly; the narrator voice reads them as pauses.
- None of the words that make writing sound machine-made: tapestry, delve, testament, timeless, profound, journey,
  resonate, masterpiece, poignant, "a reminder that", "in a world where", "little did he know".
- Read every line aloud in your head; if it sounds written rather than spoken, rewrite it.
Every fact must be accurate: no invented quotes, dates or numbers; if unsure, leave it out.

- topic: "<title> by <author>". title, author, and year: the year it was first published.
- style: {" or ".join(STYLES) if len(STYLES) == 1 else f"one of: {', '.join(STYLES)}. Fit the book's mood, and don't reuse a style from the last few reels ({', '.join(recent_styles) or 'none yet'})"}.
- mood: how the narrator should sound for this story: somber (loss, death, regret), eerie (horror, the uncanny),
  tense (crime, danger), tender (love, longing) or wry (satire, comedy, irony).
- air: what drifts over every shot, from the book's setting: mist, snow, rain, embers (fire, candles, war),
  dust (sunlit rooms, deserts) or none.
- hook: on-screen text for the first three seconds, at most 7 words, that makes people need the rest without
  giving away the ending ("He fell in love in four nights.", "She married the man who ruined her."). True to the book.
- scenes: 8 to 11 in order, together forming the script. narration is 1-2 of its sentences. art describes the one
  illustration on screen meanwhile, under 30 words: who, where, doing what, framed like a film shot. Describe each
  recurring character the same way every time (e.g. "a tall thin old knight in dented armour with a grey beard").
- caption: line 1 a hook under 10 words, line 2 the title and author, then 6-8 relevant hashtags.
{feedback}""", Film)


def paint(scene: str, seed: int, style: str = STYLES["flat vector"]["art"]):
    """One illustration, from Cloudflare when it's set up (CF_ACCOUNT_ID, CF_API_TOKEN), else Pollinations.
    One seed per reel keeps the look consistent. Returns None on failure: the scene reuses the painting before it."""
    prompt = f"{scene}, {style}, period-accurate setting with no modern objects, no text, no letters"
    if os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"):
        return cloudflare_art(prompt, seed)
    return pollinations_art(prompt, seed)


def cloudflare_art(prompt: str, seed: int):
    """Flux 2 Klein on Cloudflare Workers AI: no logo and no wait. A portrait image costs about 250 of the 10,000
    neurons Cloudflare gives free each day, so two book reels a day stay free."""
    url = (f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID']}"
           "/ai/run/@cf/black-forest-labs/flux-2-klein-4b")
    form = {"prompt": prompt, "width": "1088", "height": "1920", "seed": str(seed)}
    for _ in range(3):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {os.environ['CF_API_TOKEN']}"}, timeout=180,
                              files={k: (None, v) for k, v in form.items()})  # multipart form, as the model expects
            if r.status_code == 429 or r.status_code >= 500:  # busy: try again shortly
                time.sleep(10)
                continue
            fb(r)
            return Image.open(io.BytesIO(base64.b64decode(r.json()["result"]["image"]))).convert("RGB")
        except (requests.RequestException, RuntimeError, KeyError, ValueError, OSError) as e:
            print(f"no art for {prompt[:60]!r}: {e}")
            return None
    print(f"no art for {prompt[:60]!r}: Cloudflare still busy after retries")
    return None


def pollinations_art(scene: str, seed: int):  # scene: the whole prompt
    """AI art from Pollinations (free, no key; anonymous images carry a small logo)."""
    for _ in range(4):
        try:
            r = requests.get("https://image.pollinations.ai/prompt/" + urllib.parse.quote(scene, safe=""),
                             params={"width": W, "height": H, "seed": seed, "nologo": "true"}, timeout=180)
            if r.status_code in (402, 429) or r.status_code >= 500:  # anonymous limit (1 image / 45 s, sent as 402) or overload
                time.sleep(46)  # ponytail: minutes of waiting per reel; a pollen key from enter.pollinations.ai lifts it
                continue
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except (requests.RequestException, OSError) as e:
            print(f"no art for {scene!r}: {e}")
            return None
    print(f"no art for {scene!r}: still {r.status_code} after retries")
    return None


# ---------- Reddit ----------

def fetch_reddit(sub: str) -> list[dict]:
    # Reddit's JSON API now needs an approved app; the public RSS feed still works without one.
    for _ in range(5):
        r = requests.get(f"https://www.reddit.com/r/{sub}/top/.rss", params={"t": TOP_WINDOW, "limit": 100},
                         headers={"User-Agent": "windows:reelbot:0.1"}, timeout=30)
        if r.status_code != 429 and r.text:
            break
        time.sleep(30)  # ponytail: unauthenticated RSS is rate-limited hard; fine for a few runs a day
    r.raise_for_status()
    ns, posts = {"a": "http://www.w3.org/2005/Atom"}, []
    for e in ET.fromstring(r.text).findall("a:entry", ns):
        content = e.findtext("a:content", "", ns)
        if '<div class="md">' not in content:  # link/image post, no text
            continue
        md = content.split('<div class="md">', 1)[1].split("</div><!-- SC_ON -->")[0]
        body = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"</p>|<br\s*/?>", "\n", md)))
        posts.append({"id": e.findtext("a:id", "", ns), "title": e.findtext("a:title", "", ns),
                      "author": e.findtext("a:author/a:name", "", ns).removeprefix("/u/"),
                      "body": re.sub(r"[ \t]+", " ", body).strip()})
    return posts


def pick_story(sub: str, posts: list[dict], seen: list[str], feedback: str = ""):
    # feed is already sorted by upvotes; keep that order and send the top 30 unused ones
    cands = [p for p in posts if p["id"] not in seen and MIN_WORDS <= len(p["body"].split()) <= MAX_WORDS][:30]
    if not cands:
        return None, None
    s = ask(f"""Below are the most upvoted r/{sub} posts (JSON), listed from most to least upvoted.
Pick the ONE post most likely to go viral as a narrated Instagram Reel: a clear conflict with real stakes, a person
viewers will take sides on, and a satisfying payoff or twist at the end. Upvotes are a good signal, not the only one.
A post is NOT suitable if it is a meta or moderator post, an UPDATE that needs an earlier post for context, or
anything sexual, graphic, hateful, or involving self-harm or harm to children. If none are suitable, return an empty id.

Prepare the chosen post for a text-to-speech narrator:
- story: retell it in your own words (do not copy the author's sentences), first person as the author, 150-300 words,
  shorter if the original is short. Keep every event, fact and the ending as the author told them; never invent or
  exaggerate. Write it the way a person tells a story to a friend, not the way an essay reads: contractions (I'd,
  didn't, she's), sentence lengths that vary (a long one, then a short punch), the odd natural connector ("So,",
  "Anyway,", "And get this,"), a brief honest reaction where the author would have one ("I was speechless."), and
  commas, dashes or "..." where a speaker would pause for effect. Use those sparingly; no "um" or "like" filler.
  No abbreviations (mother-in-law, not MIL), no profanity stronger than "hell" or "damn". Open straight into the
  conflict and end on the payoff line.
- title: the author's title with abbreviations spelled out (AITA -> Am I the a-hole, 27F -> 27 female).
- caption: line 1 a hook of at most 8 words that makes people watch, like "She did not see this coming." (true to
  the story, does not give away the ending); line 2 a short question that gets viewers to take a side in the comments;
  line 3 "Based on a story by u/<author> on r/{sub}"; then 6-8 relevant hashtags.

{feedback}

Posts: {json.dumps(cands)}""", Story)
    post = next((p for p in cands if p["id"] == s.id), None)
    return (s, post) if post else (None, None)


# ---------- rendering ----------

def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, f, width):
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=f) <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def draw_lines(draw, lines, f, y, fill, gap=1.25, x=PAD):
    for ln in lines:
        draw.text((x, y), ln, font=f, fill=fill)
        y += int(f.size * gap)
    return y


def render(label, big, text, i, n):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    d.text((PAD, 260), label, font=font(BOLD, 44), fill=MUTED)
    size = 150 if i == 0 else 200  # title wraps; stats shrink to stay on one line
    while i and size > 100 and d.textlength(big, font=font(BOLD, size)) > W - 2 * PAD:
        size -= 10
    bf = font(BOLD, size)
    y = draw_lines(d, wrap(d, big, bf, W - 2 * PAD), bf, 360, ACCENT if i else FG, 1.1)
    draw_lines(d, wrap(d, text, font(REG, 60), W - 2 * PAD), font(REG, 60), y + 60, FG)
    seg = (W - 2 * PAD) / n  # progress bar
    for k in range(n):
        d.rectangle([PAD + k * seg + 6, H - 200, PAD + (k + 1) * seg - 6, H - 188],
                    fill=ACCENT if k <= i else "#2a3550")
    return img


CARD_W = W - 2 * PAD - 60  # text width inside a post card
BODY = font(REG, 54)


def word_boxes(d, lines, f, x, y, lh):
    """Each word's box (x, y, w, h, word) in reading order, for the highlighter."""
    boxes = []
    for n, ln in enumerate(lines):
        words = ln.split(" ")
        for k, w in enumerate(words):
            wx = x + (d.textlength(" ".join(words[:k]) + " ", font=f) if k else 0)
            boxes.append((round(wx) - 6, y + n * lh - 2, round(d.textlength(w, font=f)) + 12, round(f.size * 1.3), w))
    return boxes


def render_card(sub, author, text, body=False):
    """A Reddit-style post card (generic look, no Reddit logo): the bold title, or one page of the story.
    Returns the image and every word's box, for the highlighter."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))  # transparent: background shows around the card
    d = ImageDraw.Draw(img)
    x0, x1, tf, gap = PAD - 20, W - PAD + 20, BODY if body else font(BOLD, 64), 1.35 if body else 1.25
    lines = wrap(d, text, tf, CARD_W)
    h = 200 + len(lines) * int(tf.size * gap)
    top = (H - h) // 2
    d.rounded_rectangle([x0, top, x1, top + h], radius=36, fill="#ffffff")
    d.ellipse([x0 + 50, top + 45, x0 + 110, top + 105], fill="#ff4500")
    hf, head = font(BOLD, 38), f"r/{sub}  ·  u/{author}  ·  retold"  # the story is Claude's retelling, say so
    if d.textlength(head, font=hf) > x1 - x0 - 180:
        head = f"r/{sub}  ·  retold"  # long names: the author is still credited in the caption
    d.text((x0 + 130, top + 50), head, font=hf, fill="#576f76")
    draw_lines(d, lines, tf, top + 140, "#1a1a1b", gap, x=x0 + 50)
    return img, word_boxes(d, lines, tf, x0 + 50, top + 140, int(tf.size * gap))


def pack(text, fits):
    """Group sentences into the fewest chunks for which fits(chunk) holds, breaking between sentences."""
    units = []
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        units += [s] if fits(s) else s.split()  # a run-on sentence too long for one chunk breaks between words
    out = []
    for u in units:
        if out and fits(f"{out[-1]} {u}"):
            out[-1] += " " + u
        else:
            out.append(u)
    return out


def pages(text, max_lines=12):
    """Split the story into card-sized pages."""
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return pack(text, lambda t: len(wrap(d, t, BODY, CARD_W)) <= max_lines)


def trivia_slides(post: Post, label="DID YOU KNOW?"):
    cards = [(label, post.title, "", post.hook)]
    cards += [(f"{i}/{len(post.slides)}", s.big, s.text, s.narration) for i, s in enumerate(post.slides, 1)]
    return [(render(*c[:3], i, len(cards)), c[3], False) for i, c in enumerate(cards)]


def reddit_slides(sub, author, title, story):
    # the post itself on screen: the title card, then the story page by page, each shown while it is read
    cards = [(render_card(sub, author, title), title)] + \
            [(render_card(sub, author, p, body=True), p) for p in pages(story)]
    return [(img, text, boxes) for (img, boxes), text in cards]


def match_words(spoken, boxes):
    """Pair each spoken word (start, end, word) with its box on the card. TTS drops punctuation, so compare
    letters only and look a few words ahead in case a word was skipped."""
    norm = lambda s: re.sub(r"\W", "", s.lower())
    hits, j = [], 0
    for start, end, w in spoken:
        a = norm(w)
        for k in range(j, min(j + 4, len(boxes))):
            b = norm(boxes[k][4])
            if a and b and (a.startswith(b) or b.startswith(a)):
                hits.append((start, end, boxes[k]))
                j = k + 1
                break
    return hits


def ts(s):
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02}:{s % 60:05.2f}"


def write_ass(spoken, boxes, path: Path):
    """Highlighter: a translucent gold box over each word on the card while it is spoken."""
    hits, events = match_words(spoken, boxes), []
    for n, (start, end, (x, y, w, h, _)) in enumerate(hits):
        stop = hits[n + 1][0] if n + 1 < len(hits) else end + 0.3  # hold until the next word starts
        events.append(f"Dialogue: 0,{ts(start)},{ts(stop)},W,,0,0,0,,{{\\an7\\pos(0,0)\\p1}}"
                      f"m {x} {y} l {x + w} {y} l {x + w} {y + h} l {x} {y + h}")
    gold = "&H70" + ACCENT[5:7] + ACCENT[3:5] + ACCENT[1:3]  # ASS colours are alpha+BGR; 70 = about 55% opaque
    path.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: W,Segoe UI,20,{gold},{gold},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n", encoding="utf-8")


# ---------- video ----------

async def speak(text, mp3):
    """Save the narration and return each word's (start, end, word) in seconds."""
    for attempt in range(3):  # Edge's free endpoint now and then sends no audio; a retry a few seconds later works
        words = []
        try:
            with open(mp3, "wb") as f:
                async for c in edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary").stream():
                    if c["type"] == "audio":
                        f.write(c["data"])
                    elif c["type"] == "WordBoundary":
                        words.append((c["offset"] / 1e7, (c["offset"] + c["duration"]) / 1e7, c["text"]))
            return words
        except edge_tts.exceptions.NoAudioReceived:
            if attempt == 2:
                raise
            await asyncio.sleep(5)


KOKORO_SCRIPT = """
import json, re, sys, numpy as np, soundfile as sf
from kokoro import KPipeline
voice, mood = sys.argv[1], json.loads(sys.argv[2])
pipe = KPipeline(lang_code=voice[0], repo_id="hexgrad/Kokoro-82M")  # a = American, b = British voices

def rest(sentence):  # seconds of silence after a sentence, from how it ends
    end = sentence.rstrip(" \\"'”’)")
    base = 0.75 if end.endswith(("...", "…")) else 0.55 if end.endswith("?") else 0.4 if end.endswith("!") else 0.45
    return base * mood["pause"]

out = []
for text, path in json.load(sys.stdin):
    audio, words, t = [], [], 0.0
    for sentence in [x for x in re.split(r"(?<=[.!?…])\\s+", text.strip()) if x]:  # each its own rise and fall
        chunk, local, tt, glue = [], [], 0.0, False
        for r in pipe(sentence, voice=voice, speed=mood["speed"]):
            for tk in r.tokens:
                if tk.start_ts is None:
                    continue
                if glue and local:  # no space before it: punctuation or a suffix, part of the last word
                    local[-1][1], local[-1][2] = tt + tk.end_ts, local[-1][2] + tk.text
                else:
                    local.append([tt + tk.start_ts, tt + tk.end_ts, tk.text])
                glue = not tk.whitespace
            chunk.append(r.audio.numpy())
            tt += len(chunk[-1]) / 24000
        a = np.concatenate(chunk)
        loud = np.flatnonzero(np.abs(a) > 0.02 * np.abs(a).max())  # trim Kokoro's own silence, keep 40 ms
        lo, hi = (max(0, loud[0] - 960), min(len(a), loud[-1] + 960)) if len(loud) else (0, len(a))
        audio.append(a[lo:hi])
        words += [[t + w0 - lo / 24000, t + w1 - lo / 24000, w] for w0, w1, w in local]
        t += (hi - lo) / 24000
        audio.append(np.zeros(int(24000 * rest(sentence)), dtype=np.float32))
        t += len(audio[-1]) / 24000
    sf.write(path, np.concatenate(audio[:-1]), 24000)  # no pause after the last one: the scene gap follows
    out.append(words)
print(json.dumps(out))
"""


def kokoro(items, mood: str = "somber"):
    """Narrate with Kokoro in its own Python (it doesn't install on 3.14), one sentence at a time with real pauses,
    in the story's mood. One process for all scenes, so the model loads once. Returns each item's words as
    (start, end, word), like speak()."""
    r = subprocess.run([KOKORO_PY, "-c", KOKORO_SCRIPT, KOKORO_VOICE, json.dumps(MOODS[mood])], check=True,
                       text=True, capture_output=True, encoding="utf-8",
                       input=json.dumps([[t, str(p)] for t, p in items]))
    return json.loads(r.stdout.strip().splitlines()[-1])


async def voice(items):
    return [await speak(t, p) for t, p in items]  # one at a time: parallel requests get dropped (NoAudioReceived)


def run(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True, cwd=cwd)


def duration(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


def drone(d: float) -> str:
    """A slow ambient pad, synthesized: a minor chord (root, fifth, minor third an octave up), each note beside a
    slightly detuned twin so it shimmers, swelling gently, then echoed into a wash. No samples, so no licence."""
    root = random.choice([98.0, 110.0, 123.47, 130.81])  # G2, A2, B2, C3: a different key each reel
    def channel(det):
        notes = "+".join(f"{a}*(sin(2*PI*{f:.2f}*t)+sin(2*PI*{f + det:.2f}*t))"
                         for f, a in ((root, .2), (root * 1.5, .12), (root * 2.378, .06)))
        return f"({notes})*(0.75+0.25*sin(2*PI*0.04*t))"
    return (f"aevalsrc={channel(0.3)}|{channel(0.45)}:s=48000:d={d:.2f},"
            "lowpass=f=1200,aecho=0.8:0.7:600|1100:0.3|0.2")


# background sound for each setting (the `air` a book reel picks), synthesized from noise: no samples, no licence
AMBIENCE = {
    "rain": "anoisesrc=c=pink:r=48000:a=0.6,highpass=f=500,lowpass=f=8000",                     # steady rain
    "snow": "anoisesrc=c=brown:r=48000:a=0.8,lowpass=f=600,tremolo=f=0.12:d=0.7",               # wind gusting
    "mist": "anoisesrc=c=brown:r=48000:a=0.6,lowpass=f=350,tremolo=f=0.1:d=0.5",                # a soft breeze
    "embers": ("anoisesrc=c=brown:r=48000:a=0.5,lowpass=f=300[roar];"                           # a fire: low roar
               "aevalsrc='if(lt(random(0),0.003),(random(1)-0.5)*1.5,0)':s=48000,highpass=f=900[pop];"  # + crackle
               "[roar][pop]amix=inputs=2:normalize=0"),
    "dust": "anoisesrc=c=brown:r=48000:a=0.4,lowpass=f=200",                                    # quiet room tone
}


def add_music(video: Path, air: str = "none"):
    """Quiet beds under the narration: a random track from music/ (looped) or the synth drone, and the setting's
    ambience (rain, wind, fire...) just under that."""
    d = duration(video)
    tracks = [p for p in MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a", ".flac")]
    src = ["-stream_loop", "-1", "-i", random.choice(tracks)] if tracks else ["-f", "lavfi", "-i", drone(d)]
    fades = f"afade=t=in:d=2,afade=t=out:st={max(d - 3, 0):.2f}:d=3"
    graph = f"[1:a]atrim=0:{d:.2f},loudnorm=I=-32:TP=-8,{fades}[m];"
    if air in AMBIENCE:
        src += ["-f", "lavfi", "-i", AMBIENCE[air]]
        graph += f"[2:a]atrim=0:{d:.2f},loudnorm=I=-33:TP=-9,{fades}[n];[0:a][m][n]amix=inputs=3"
    else:
        graph += "[0:a][m]amix=inputs=2"
    voice_only = video.with_name("voice_only.mp4")
    video.replace(voice_only)
    run("-i", voice_only, *src, "-filter_complex", graph + ":duration=first:normalize=0,aresample=48000[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", video)
    level(video)


def loudness(path) -> float:
    """Integrated loudness in LUFS."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8").stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def level(video: Path, target=-14.0):
    """Bring the finished mix to Instagram's -14 LUFS: measure it, apply the exact gain, limit the peaks.
    (One-pass loudnorm lands a dB or two short on mixes with long quiet pauses.)"""
    gain = target - loudness(video)
    if abs(gain) < 0.3:
        return
    mixed = video.with_name("unleveled.mp4")
    video.replace(mixed)
    run("-i", mixed, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.89:level=false", "-c:v", "copy", "-c:a", "aac",
        "-movflags", "+faststart", video)


def build(slides, caption: str, out: Path, pause=0.6, bg: Path | None = None) -> Path:
    """slides: list of (PIL image, narration, word boxes or None). Each image is overlaid on the background while
    its narration plays; word boxes add a highlighter that follows the voice word by word.
    bg: a gameplay clip (muted, cropped to 9:16, looped, random start), or None for a plain colour."""
    out = out.resolve()  # the concat list needs absolute paths
    out.mkdir(parents=True, exist_ok=True)
    for i, (img, _, _) in enumerate(slides):
        img.save(out / f"{i}.png")
    timings = asyncio.run(voice([(t, out / f"{i}.mp3") for i, (_, t, _) in enumerate(slides)]))
    t = random.uniform(0, duration(bg)) if bg else 0
    for i, (_, _, boxes) in enumerate(slides):
        subs = ""
        if boxes:
            write_ass(timings[i], boxes, out / f"{i}.ass")
            subs = f",ass={i}.ass"  # relative: ffmpeg runs inside `out`, avoids Windows path escaping
        src = (["-stream_loop", "-1", "-ss", f"{t:.3f}", "-i", bg] if bg
               else ["-f", "lavfi", "-i", f"color=c={BG.replace('#', '0x')}:s={W}x{H}:r=30"])
        run(*src, "-loop", "1", "-framerate", "30", "-i", out / f"{i}.png", "-i", out / f"{i}.mp3",
            "-filter_complex", f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30[b];"
                               f"[b][1:v]overlay{subs},format=yuv420p[v];[2:a]{VOICE_FX},apad=pad_dur={pause}[a]",
            "-map", "[v]", "-map", "[a]", "-shortest", "-c:v", "libx264", "-preset", "veryfast",
            "-c:a", "aac", "-ar", "48000", out / f"{i}.mp4", cwd=out)
        t += duration(out / f"{i}.mp4")  # next segment continues the gameplay where this one stopped
    (out / "list.txt").write_text("".join(f"file '{(out / f'{i}.mp4').as_posix()}'\n" for i in range(len(slides))))
    video = out / "reel.mp4"
    run("-f", "concat", "-safe", "0", "-i", out / "list.txt", "-c", "copy", "-movflags", "+faststart", video)
    (out / "caption.txt").write_text(caption, encoding="utf-8")
    return video


# camera moves on a still (zoompan expressions; n = frames in the shot), cycled so consecutive shots differ
MOVES = [("1+{a}*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),          # push in   (a = the style's zoom)
         ("1+{a}-{a}*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),     # pull out
         ("1+{a}", "(iw-iw/zoom)*on/{n}", "ih/2-ih/zoom/2"),            # pan right
         ("1+{a}", "iw/2-iw/zoom/2", "(ih-ih/zoom)*(1-on/{n})")]        # tilt up


def caption_groups(words):
    """Three words a caption, breaking early where a sentence or clause ends."""
    groups, g = [], []
    for w in words:
        g.append(w)
        if len(g) == 3 or (w[2][-1] in ".?!,;:" and w[2] not in ("St.", "Mr.", "Mrs.", "Dr.")):
            groups.append(g)
            g = []
    return groups + [g] if g else groups


def srt(words) -> str:
    """Captions for mockingbird's kit: one cue per spoken word, the group's text with that word *marked*, so the
    pill can follow the voice."""
    def stamp(x):
        return f"{int(x // 3600):02}:{int(x % 3600 // 60):02}:{x % 60:06.3f}".replace(".", ",")
    cues, groups = [], caption_groups(words)
    for n, g in enumerate(groups):
        end = min(groups[n + 1][0][0] if n + 1 < len(groups) else 1e9, g[-1][1] + 0.6)
        for k, (start, _, _) in enumerate(g):
            text = " ".join(f"*{w[2]}*" if j == k else w[2] for j, w in enumerate(g))
            cues.append(f"{len(cues) + 1}\n{stamp(start)} --> {stamp(g[k + 1][0] if k + 1 < len(g) else end)}\n{text}\n")
    return "\n".join(cues)


def write_captions(words, path: Path):
    """Plain burned-in captions, three words at a time: the fallback when mockingbird isn't installed."""
    groups = caption_groups(words)
    events = [f"Dialogue: 0,{ts(g[0][0])},{ts(groups[n + 1][0][0] if n + 1 < len(groups) else g[-1][1] + 0.4)},C,,0,0,0,,"
              + " ".join(w[2] for w in g).replace("{", "(").replace("}", ")") for n, g in enumerate(groups)]
    path.write_text(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: C,Segoe UI,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,{PAD},{PAD},620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events) + "\n", encoding="utf-8")


def mockingbird(tool: str, args: dict) -> str:
    """Call one mockingbird tool over MCP (JSON-RPC on stdio): `motion` has no command-line form."""
    p = subprocess.Popen([MOCKINGBIRD, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         encoding="utf-8")
    def send(msg):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", **msg}) + "\n")
        p.stdin.flush()
    def reply(i):
        for line in p.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == i:
                return msg
        raise RuntimeError("mockingbird exited without answering")
    try:
        send({"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                          "clientInfo": {"name": "reelbot", "version": "1"}}})
        reply(1)
        send({"method": "notifications/initialized"})
        send({"id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}})
        r = reply(2)
    finally:
        p.stdin.close()
        p.terminate()
    text = " ".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
    if "error" in r or r["result"].get("isError"):
        raise RuntimeError(f"mockingbird {tool} failed: {r.get('error') or text}")
    return text


def build_film(film: Film, out: Path, pause=0.35, fade=0.6) -> Path:
    """Animated story: one illustration per scene with a slow camera move, crossfades between shots, the narration
    and a music bed, then mockingbird's motion layer (or plain burned captions without it). A painting that fails
    reuses the one before it (with a different move)."""
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "script.json").write_text(film.model_dump_json(indent=1), encoding="utf-8")  # to read what was said
    seed = random.randrange(10**6)
    look = STYLES[film.style]
    arts = [paint(sc.art, seed, look["art"]) for sc in film.scenes]
    shot = next((a for a in arts if a), None) or Image.new("RGB", (W, H), BG)
    for i, a in enumerate(arts):
        shot = a or shot
        ImageOps.fit(shot, (W, H)).save(out / f"{i}.png")
    local = KOKORO_PY.exists()
    items = [(sc.narration, out / f"{i}.{'wav' if local else 'mp3'}") for i, sc in enumerate(film.scenes)]
    timings = kokoro(items, film.mood) if local else asyncio.run(voice(items))
    lengths = [duration(p) + pause for _, p in items]
    starts = [sum(lengths[:i]) for i in range(len(lengths))]
    words = [(t0 + a, t0 + b, w) for t0, spoken in zip(starts, timings) for a, b, w in spoken]
    animate = MOCKINGBIRD.exists()
    if not animate:
        write_captions(words, out / "captions.ass")

    n_sc, graph = len(film.scenes), []
    for i in range(n_sc):  # each shot runs `fade` longer so the next one can dissolve in over its tail
        n = round((lengths[i] + (fade if i < n_sc - 1 else 0)) * look["fps"])
        z, x, y = (e.format(n=n, a=look["zoom"]) for e in MOVES[i % len(MOVES)])
        if look["shake"]:  # a hand-moved camera: a small different nudge every frame
            x, y = f"{x}+{look['shake']}*sin(on*12.9898)", f"{y}+{look['shake']}*sin(on*78.233)"
        graph.append(f"[{i}:v]scale={2 * W}:{2 * H},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={look['fps']},"
                     f"fps=30,setsar=1,format=yuv420p[v{i}]")  # 2x upscale first: zoompan jitters on a small image
    last = "v0"
    for i in range(1, n_sc):
        graph.append(f"[{last}][v{i}]xfade=transition={look['cut']}:duration={fade}:offset={starts[i]:.3f}[x{i}]")
        last = f"x{i}"
    graph.append(f"[{last}]{'null' if animate else 'ass=captions.ass'}[v]")
    mood = MOODS[film.mood] if local else dict(pitch=1.0, room=False)
    lower = (f"rubberband=pitch={mood['pitch']}:formant=preserved," if mood["pitch"] != 1.0 else "")  # deeper, same timing
    lower += "aecho=0.85:0.5:45|90:0.15|0.1," if mood["room"] else ""  # a faint room around the voice
    graph += [f"[{n_sc + i}:a]{lower}apad=whole_dur={lengths[i]:.3f}[a{i}]" for i in range(n_sc)]
    graph.append("".join(f"[a{i}]" for i in range(n_sc)) + f"concat=n={n_sc}:v=0:a=1,{VOICE_FX},aresample=48000[a]")
    video = out / ("base.mp4" if animate else "reel.mp4")
    run(*[a for i in range(n_sc) for a in ("-i", out / f"{i}.png")], *[a for _, p in items for a in ("-i", p)],
        "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", video, cwd=out)
    add_music(video, film.air)
    if animate:  # title, captions that follow the voice, mist and light, drawn over the shots
        config = {"title": film.hook, "sub": f"{film.title} · {film.author}, {film.year}",
                  "shots": [round(x, 2) for x in starts[1:]], "air": film.air, "glow": look["glow"]}
        (out / "motion.html").write_text((HERE / "book_motion.html").read_text(encoding="utf-8").replace(
            "/*CONFIG*/{", f"{json.dumps(config, ensure_ascii=False)} || {{", 1), encoding="utf-8")
        video = out / "reel.mp4"
        mockingbird("motion", {"script": str(out / "motion.html"), "path": str(out / "base.mp4"), "fps": 30,
                               "captions": srt(words), "out": str(video)})
    (out / "caption.txt").write_text(film.caption, encoding="utf-8")
    return video


# ---------- posting ----------

TOKENS = HERE / "tokens.json"  # YouTube and TikTok sign-ins from --login; kept out of git
POSTS = HERE / "posts.json"    # every reel this page posted and its Instagram numbers, for the feedback loop


def use_env(path: Path):
    """Load one page's settings, replacing every platform setting from the environment so nothing posts to the
    other page by accident; that page's YouTube/TikTok sign-ins live beside it (books.env -> books.tokens.json)."""
    global TOKENS, POSTS
    if not path.exists():
        sys.exit(f"{path.name} not found: copy page.env.example to it and fill it in")
    for k in [k for _, env in PLATFORMS.values() for k in env] + ["TIKTOK_REDIRECT_URI", "TIKTOK_PRIVACY"]:
        os.environ.pop(k, None)
    for line in path.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and not k.strip().startswith("#"):
            os.environ[k.strip()] = v.strip().strip('"')
    TOKENS = path.with_suffix(".tokens.json")
    POSTS = path.with_suffix(".posts.json")


def tokens() -> dict:
    return json.loads(TOKENS.read_text()) if TOKENS.exists() else {}


def save_token(site: str, refresh: str):
    TOKENS.write_text(json.dumps({**tokens(), site: refresh}, indent=1))


def fb(r):
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text}")
    return r.json() if r.content else {}


def instagram(video: Path, caption: str) -> str:
    uid, tok = os.environ["IG_USER_ID"], os.environ["IG_TOKEN"]
    base, auth = f"https://graph.facebook.com/{GRAPH}", {"Authorization": f"OAuth {tok}"}
    cid = fb(requests.post(f"{base}/{uid}/media", headers=auth, timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "is_ai_generated": "true"}))["id"]
    data = video.read_bytes()
    fb(requests.post(f"https://rupload.facebook.com/ig-api-upload/{GRAPH}/{cid}", data=data, timeout=600,
                     headers={**auth, "offset": "0", "file_size": str(len(data))}))
    for _ in range(60):  # Instagram processes the video before it can be published
        s = fb(requests.get(f"{base}/{cid}", headers=auth, params={"fields": "status_code,status"}, timeout=30))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"processing failed: {s}")
        time.sleep(10)
    else:
        raise TimeoutError("video still processing after 10 minutes")
    return fb(requests.post(f"{base}/{uid}/media_publish", headers=auth, data={"creation_id": cid}, timeout=60))["id"]


def facebook(video: Path, caption: str) -> str:
    """A Reel on the Facebook Page: start an upload, send the file, publish it with the caption."""
    page, tok = os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_TOKEN"]
    base = f"https://graph.facebook.com/{GRAPH}/{page}/video_reels"
    vid = fb(requests.post(base, data={"upload_phase": "start", "access_token": tok}, timeout=60))["video_id"]
    data = video.read_bytes()
    fb(requests.post(f"https://rupload.facebook.com/video-upload/{GRAPH}/{vid}", data=data, timeout=600,
                     headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))}))
    fb(requests.post(base, timeout=60, data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                                             "description": caption, "access_token": tok}))
    return vid


def youtube(video: Path, caption: str) -> str:
    """A Short: vertical and under 3 minutes, so YouTube files it as one. The caption's first line is the title."""
    tok = fb(requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": tokens()["youtube"], "grant_type": "refresh_token"}))["access_token"]
    auth = {"Authorization": f"Bearer {tok}"}
    title = re.sub(r"[<>]", "", caption.splitlines()[0]).strip()[:100] or "New short"
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos", timeout=60,
                      params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={**auth, "X-Upload-Content-Type": "video/mp4"},
                      json={"snippet": {"title": title, "description": caption, "categoryId": "24"},
                            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False,
                                       "containsSyntheticMedia": True}})
    fb(r)
    return fb(requests.put(r.headers["Location"], data=video.read_bytes(), timeout=600,
                           headers={**auth, "Content-Type": "video/mp4"}))["id"]


def tiktok(video: Path, caption: str) -> str:
    """Direct post through TikTok's Content Posting API, labelled as AI-generated."""
    t = fb(requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": tokens()["tiktok"]}))
    if "access_token" not in t:
        raise RuntimeError(f"TikTok sign-in failed: {t}")
    save_token("tiktok", t["refresh_token"])  # TikTok can hand out a new one each time
    size = video.stat().st_size  # ponytail: one piece, fine up to TikTok's 64 MB chunk limit; reels are ~30 MB
    init = fb(requests.post("https://open.tiktokapis.com/v2/post/publish/video/init/", timeout=60,
                            headers={"Authorization": f"Bearer {t['access_token']}"}, json={
        "post_info": {"title": caption[:2200], "privacy_level": os.environ.get("TIKTOK_PRIVACY", "SELF_ONLY"),
                      "is_aigc": True},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}}))
    fb(requests.put(init["data"]["upload_url"], data=video.read_bytes(), timeout=600,
                    headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"}))
    return init["data"]["publish_id"]


PLATFORMS = {"instagram": (instagram, ["IG_USER_ID", "IG_TOKEN"]),
             "facebook": (facebook, ["FB_PAGE_ID", "FB_PAGE_TOKEN"]),
             "youtube": (youtube, ["YT_CLIENT_ID", "YT_CLIENT_SECRET"]),
             "tiktok": (tiktok, ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"])}


def ready() -> list[str]:
    """The platforms this page is set up for."""
    return [name for name, (_, env) in PLATFORMS.items()
            if all(os.environ.get(k) for k in env) and (name not in ("youtube", "tiktok") or name in tokens())]


def publish(video: Path, caption: str) -> dict:
    """Post to every platform that is set up; one failing doesn't stop the rest. Returns {platform: post id}."""
    done = {}
    for name in ready():
        try:
            done[name] = PLATFORMS[name][0](video, caption)
            print(f"posted to {name}:", done[name])
        except Exception as e:  # report it and carry on with the other platforms
            print(f"{name} failed: {e}")
    return done


def posts() -> list:
    return json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else []


def refresh_stats():
    """Pull Instagram's numbers for this page's reels posted 1 to 30 days ago (the first day undersells a reel;
    after a month it has settled). Best effort: a failed lookup never stops a run."""
    log, tok = posts(), os.environ.get("IG_TOKEN")
    for p in log:
        mid, age = p["ids"].get("instagram"), time.time() - p["at"]
        if not (tok and mid and 86400 < age < 30 * 86400):
            continue
        try:
            data = fb(requests.get(f"https://graph.facebook.com/{GRAPH}/{mid}/insights", timeout=30,
                                   headers={"Authorization": f"OAuth {tok}"},
                                   params={"metric": "views,reach,shares,saved,ig_reels_avg_watch_time"}))["data"]
            p["stats"] = {d["name"]: d.get("total_value", {}).get("value", (d.get("values") or [{}])[0].get("value", 0))
                          for d in data}
        except Exception as e:
            print(f"no Instagram numbers for {p['what']}: {e}")
    if log:
        POSTS.write_text(json.dumps(log, indent=1), encoding="utf-8")


def track_record(log: list) -> str:
    """What to tell Claude: the page's best and worst reels by views, once there are a few to compare."""
    rated = sorted((p for p in log if p.get("stats")), key=lambda p: p["stats"].get("views", 0), reverse=True)
    if len(rated) < 3:
        return ""
    def line(p):
        st = p["stats"]
        return (f"- {p['what']}: {st.get('views', 0)} views, {st.get('ig_reels_avg_watch_time', 0) / 1000:.0f} s "
                f"average watch, {st.get('shares', 0)} shares, {st.get('saved', 0)} saves")
    shown = rated if len(rated) <= 8 else rated[:5] + rated[-3:]
    return ("How this page's past reels did on Instagram, best first. Choose and write more like the top ones (their "
            "kind of story, opening and hook), and avoid what the bottom ones have in common:\n"
            + "\n".join(map(line, shown)))


def meta_setup():
    """Turn one Meta system user token into each Page's settings (its own never-expiring Page token, and the
    Instagram account linked to it), ready to paste into books.env / stories.env."""
    token = input("Paste the system user token: ").strip()
    pages = fb(requests.get(f"https://graph.facebook.com/{GRAPH}/me/accounts", timeout=30, params={
        "access_token": token, "fields": "name,id,access_token,instagram_business_account"}))["data"]
    if not pages:
        sys.exit("no Pages: assign your Facebook Pages to the system user in Business Settings")
    for pg in pages:
        print(f"\n# {pg['name']}\nFB_PAGE_ID={pg['id']}\nFB_PAGE_TOKEN={pg['access_token']}")
        if pg.get("instagram_business_account"):
            print(f"IG_USER_ID={pg['instagram_business_account']['id']}\nIG_TOKEN={token}")
        else:
            print("# no Instagram account linked to this Page yet")


def login(site: str):
    """One-time sign-in for YouTube or TikTok: approve in the browser, then paste back the address it sends you
    to (a "can't connect" page is fine, the code is in the address). Saves the refresh token to tokens.json."""
    if site == "youtube":
        cid, secret, redirect = os.environ["YT_CLIENT_ID"], os.environ["YT_CLIENT_SECRET"], "http://localhost"
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect, "response_type": "code", "access_type": "offline",
            "prompt": "consent", "scope": "https://www.googleapis.com/auth/youtube.upload"})
    elif site == "tiktok":
        cid, secret, redirect = (os.environ["TIKTOK_CLIENT_KEY"], os.environ["TIKTOK_CLIENT_SECRET"],
                                 os.environ["TIKTOK_REDIRECT_URI"])
        url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
            "client_key": cid, "redirect_uri": redirect, "response_type": "code", "scope": "video.publish",
            "state": "reelbot"})
    else:
        sys.exit("--login youtube or --login tiktok")
    print(f"Open this, approve, then copy the address you land on:\n{url}\n")
    code = urllib.parse.parse_qs(urllib.parse.urlparse(input("Address: ").strip()).query)["code"][0]
    token_url = ("https://oauth2.googleapis.com/token" if site == "youtube"
                 else "https://open.tiktokapis.com/v2/oauth/token/")
    t = fb(requests.post(token_url, timeout=30, data={
        "client_id" if site == "youtube" else "client_key": cid, "client_secret": secret, "code": code,
        "redirect_uri": redirect, "grant_type": "authorization_code"}))
    if "refresh_token" not in t:
        sys.exit(f"sign-in failed: {t}")
    save_token(site, t["refresh_token"])
    print(f"{site} signed in")


DEMO = Post(
    topic="speed of light", title="How Fast Is Light, Really?",
    hook="Light is the fastest thing in the universe, but space is big.",
    slides=[
        Slide(big="299,792 km/s", text="The speed of light in a vacuum.",
              narration="Light travels about three hundred thousand kilometres every second."),
        Slide(big="1.3 s", text="Time for moonlight to reach Earth.",
              narration="The light you see from the Moon left it about one point three seconds ago."),
        Slide(big="8 min 20 s", text="Time for sunlight to reach Earth.",
              narration="Sunlight is older. It left the Sun about eight minutes and twenty seconds ago."),
    ],
    caption="You never see the Sun as it is now.\n#science #space #physics #didyouknow #facts #light",
)


def main():
    if "--env" in sys.argv:
        use_env(HERE / sys.argv[sys.argv.index("--env") + 1])
    if "--meta" in sys.argv:
        return meta_setup()
    if "--login" in sys.argv:
        return login((sys.argv[sys.argv.index("--login") + 1:] or [""])[0])
    demo, dry, reddit, book = (a in sys.argv for a in ("--demo", "--dry-run", "--reddit", "--book"))
    if not (demo or dry or ready()):  # don't spend 20 minutes building a reel with nowhere to post it
        sys.exit("posted nowhere: set up at least one platform (see the top of reelbot.py)")
    hist_file = HERE / ("reddit_history.json" if reddit else "book_history.json" if book else "history.json")
    history = json.loads(hist_file.read_text()) if hist_file.exists() else []
    out = HERE / "out" / time.strftime("%Y-%m-%d_%H%M%S")
    extra = {}
    if not demo:
        refresh_stats()
    feedback = track_record(posts())

    if demo:
        video, key = build(trivia_slides(DEMO), DEMO.caption, out), None
    elif reddit:
        for sub in random.sample(SUBS, len(SUBS)):
            try:
                feed = fetch_reddit(sub)
            except requests.RequestException as e:  # one unreachable feed shouldn't sink the run
                print(f"skipping r/{sub}: {e}")
                continue
            story, post = pick_story(sub, feed, history, feedback)
            if story:
                break
        else:
            sys.exit("no suitable Reddit story found")
        caption, key, what = story.caption, post["id"], f"r/{sub}: {story.title}"
        clips = [p for p in (HERE / "bg").glob("*") if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm")]
        if not clips:
            print("no gameplay clips in bg/ - using a plain background")
        video = build(reddit_slides(sub, post["author"], story.title, story.story), caption, out,
                      pause=0.15, bg=random.choice(clips) if clips else None)
    elif book:
        name = sys.argv[sys.argv.index("--book") + 1:][:1]
        recent = [p["style"] for p in posts()[-3:] if p.get("style")]
        film = generate_film(history, name[0] if name and not name[0].startswith("--") else None, feedback, recent)
        caption, key, what = film.caption, film.topic, f'{film.topic} as {film.style}, hook "{film.hook}"'
        extra = {"style": film.style}
        video = build_film(film, out)
    else:
        p = generate(history)
        caption, key, what = p.caption, p.topic, p.title
        video = build(trivia_slides(p), caption, out)

    print("built", video)
    if demo or dry:
        return
    ids = publish(video, caption)
    if not ids:
        sys.exit("posted nowhere: set up at least one platform (see the top of reelbot.py)")
    hist_file.write_text(json.dumps(history + [key], indent=1))
    POSTS.write_text(json.dumps(posts() + [{"what": what, "at": time.time(), "ids": ids, **extra}], indent=1), encoding="utf-8")


def demo_feedback():
    log = [{"what": f"book {i}", "at": 0, "ids": {}, "stats": {"views": v, "ig_reels_avg_watch_time": 9000}}
           for i, v in enumerate([50, 9000, 300, 120, 7000, 15, 80, 640, 2200, 40])]
    text = track_record(log)
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert [ln.split(":")[0] for ln in lines] == ["- book 1", "- book 4", "- book 8", "- book 7", "- book 2",
                                                "- book 0", "- book 9", "- book 5"], lines  # top 5, bottom 3
    assert "9 s average watch" in lines[0] and track_record(log[:2]) == ""


if __name__ == "__main__":
    main()
