"""Daily reels -> AI voice -> Instagram. Modes: trivia infographics, narrated Reddit stories, or animated stories of classic books.

Claude runs through the Claude Code CLI (`claude -p`, your Claude login), so no API key is needed.
Env (only for posting): IG_USER_ID, IG_TOKEN
  python reelbot.py              trivia infographic reel, posted
  python reelbot.py --reddit     drama/revenge Reddit story reel (r/AmItheAsshole, r/pettyrevenge, ...), posted
  python reelbot.py --book       animated story of a public-domain classic, told TED-Ed style, posted
  python reelbot.py --book "White Nights"   the same, for a book you choose
  --book draws its motion layer (book_motion.html: title, captions, mist, light) with mockingbird when installed,
  else burns plain captions in.
  add --dry-run to build without posting
  --book narrates with Kokoro (open-source, local) once set up, else Edge. Setup, needs Python 3.10-3.12:
    py -3.11 -m venv .venv-kokoro
    .venv-kokoro/Scripts/pip install kokoro soundfile en_core_web_sm@https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
  python reelbot.py --demo       render a built-in trivia sample (no API calls) to test the pipeline
"""
import asyncio, html, io, json, os, random, re, shutil, subprocess, sys, time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import edge_tts, requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel

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
# book reels: illustrations in one storybook-animation look, camera moves, a quiet music bed under the voice
ART_STYLE = ("still from a 2D animated short film, hand-painted storybook illustration, textured brushwork, muted warm "
             "palette, soft cinematic light, no text, no letters")
KOKORO_PY = HERE / ".venv-kokoro" / "Scripts" / "python.exe"
KOKORO_VOICE, KOKORO_SPEED = "am_michael", "1.2"  # male; af_heart is the best-rated (female)
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


def generate_film(history: list[str], book: str | None = None) -> Film:
    pick = f"The book is {book}." if book else ("Pick ONE classic book published before 1929 (a novel, epic, play, "
                                                "philosophy or history) that people have heard of but not read.")
    return ask(f"""You write narration for short animated Instagram Reels in the style of TED-Ed's "Why should you
read...?" videos. {pick} Do not repeat any of these past topics: {history[-60:] or "none yet"}.

The script is 140-190 words (about 70 seconds spoken) and tells a story; it is not a summary or a list of lessons:
- Open cold inside the book's most vivid moment, in the present tense, as if it is happening now, like
  "Mounting his skinny steed, the protagonist of Don Quixote charges an army of giants." No greeting, no "in this video".
- Pull back: name the book and author, and the surprising life or times behind it.
- What the book did that was new or daring, and what it was written against.
- Its heart: the central characters or idea, shown through concrete moments rather than morals.
- End on one resonant line about what the book says about being human. No call to action.
Write for the ear: varied sentence lengths, concrete images, plain words. Every fact must be accurate: no invented
quotes, dates or numbers; if unsure, leave it out.

- topic: "<title> by <author>". title, author, and year: the year it was first published.
- scenes: 8 to 11 in order, together forming the script. narration is 1-2 of its sentences. art describes the one
  illustration on screen meanwhile, under 30 words: who, where, doing what, framed like a film shot. Describe each
  recurring character the same way every time (e.g. "a tall thin old knight in dented armour with a grey beard").
- caption: line 1 a hook under 10 words, line 2 the title and author, then 6-8 relevant hashtags.""", Film)


def paint(scene: str, seed: int):
    """AI art from Pollinations (free, no key; anonymous images carry a small logo). One seed per reel keeps the look
    consistent. Returns None on failure."""
    for _ in range(4):
        try:
            r = requests.get("https://image.pollinations.ai/prompt/" + urllib.parse.quote(f"{scene}, {ART_STYLE}", safe=""),
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


def pick_story(sub: str, posts: list[dict], seen: list[str]):
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
import json, sys, numpy as np, soundfile as sf
from kokoro import KPipeline
pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
out = []
for text, path in json.load(sys.stdin):
    audio, words, t, glue = [], [], 0.0, False
    for r in pipe(text, voice=sys.argv[1], speed=float(sys.argv[2])):
        for tk in r.tokens:
            if tk.start_ts is None:
                continue
            if glue and words:  # no space before it: punctuation or a suffix, part of the last word
                words[-1][1], words[-1][2] = t + tk.end_ts, words[-1][2] + tk.text
            else:
                words.append([t + tk.start_ts, t + tk.end_ts, tk.text])
            glue = not tk.whitespace
        audio.append(r.audio.numpy())
        t += len(audio[-1]) / 24000
    sf.write(path, np.concatenate(audio), 24000)
    out.append(words)
print(json.dumps(out))
"""


def kokoro(items):
    """Narrate with Kokoro in its own Python (it doesn't install on 3.14). One process for all scenes, so the model
    loads once. Returns each item's words as (start, end, word), like speak()."""
    r = subprocess.run([KOKORO_PY, "-c", KOKORO_SCRIPT, KOKORO_VOICE, KOKORO_SPEED], check=True, text=True,
                       capture_output=True, encoding="utf-8", input=json.dumps([[t, str(p)] for t, p in items]))
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


def add_music(video: Path):
    """Quiet bed under the narration: a random track from music/ (looped), else the synth drone."""
    d = duration(video)
    tracks = [p for p in MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a", ".flac")]
    src = ["-stream_loop", "-1", "-i", random.choice(tracks)] if tracks else ["-f", "lavfi", "-i", drone(d)]
    voice_only = video.with_name("voice_only.mp4")
    video.replace(voice_only)
    run("-i", voice_only, *src, "-filter_complex",
        f"[1:a]atrim=0:{d:.2f},loudnorm=I=-32:TP=-8,afade=t=in:d=2,afade=t=out:st={max(d - 3, 0):.2f}:d=3[m];"
        "[0:a][m]amix=inputs=2:duration=first:normalize=0,aresample=48000[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", video)


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
MOVES = [("1+0.12*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),        # push in
         ("1.12-0.12*on/{n}", "iw/2-iw/zoom/2", "ih/2-ih/zoom/2"),     # pull out
         ("1.12", "(iw-iw/zoom)*on/{n}", "ih/2-ih/zoom/2"),             # pan right
         ("1.12", "iw/2-iw/zoom/2", "(ih-ih/zoom)*(1-on/{n})")]         # tilt up


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
    seed = random.randrange(10**6)
    arts = [paint(sc.art, seed) for sc in film.scenes]
    shot = next((a for a in arts if a), None) or Image.new("RGB", (W, H), BG)
    for i, a in enumerate(arts):
        shot = a or shot
        ImageOps.fit(shot, (W, H)).save(out / f"{i}.png")
    ext = "wav" if KOKORO_PY.exists() else "mp3"
    items = [(sc.narration, out / f"{i}.{ext}") for i, sc in enumerate(film.scenes)]
    timings = kokoro(items) if ext == "wav" else asyncio.run(voice(items))
    lengths = [duration(p) + pause for _, p in items]
    starts = [sum(lengths[:i]) for i in range(len(lengths))]
    words = [(t0 + a, t0 + b, w) for t0, spoken in zip(starts, timings) for a, b, w in spoken]
    animate = MOCKINGBIRD.exists()
    if not animate:
        write_captions(words, out / "captions.ass")

    n_sc, graph = len(film.scenes), []
    for i in range(n_sc):  # each shot runs `fade` longer so the next one can dissolve in over its tail
        n = round((lengths[i] + (fade if i < n_sc - 1 else 0)) * 30)
        z, x, y = (e.format(n=n) for e in MOVES[i % len(MOVES)])
        graph.append(f"[{i}:v]scale={2 * W}:{2 * H},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps=30,"
                     f"setsar=1,format=yuv420p[v{i}]")  # 2x upscale first: zoompan jitters on a small image
    last = "v0"
    for i in range(1, n_sc):
        graph.append(f"[{last}][v{i}]xfade=transition=fade:duration={fade}:offset={starts[i]:.3f}[x{i}]")
        last = f"x{i}"
    graph.append(f"[{last}]{'null' if animate else 'ass=captions.ass'}[v]")
    graph += [f"[{n_sc + i}:a]apad=whole_dur={lengths[i]:.3f}[a{i}]" for i in range(n_sc)]
    graph.append("".join(f"[a{i}]" for i in range(n_sc)) + f"concat=n={n_sc}:v=0:a=1,{VOICE_FX},aresample=48000[a]")
    video = out / ("base.mp4" if animate else "reel.mp4")
    run(*[a for i in range(n_sc) for a in ("-i", out / f"{i}.png")], *[a for _, p in items for a in ("-i", p)],
        "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-c:a", "aac", "-movflags", "+faststart", video, cwd=out)
    add_music(video)
    if animate:  # title, captions that follow the voice, mist and light, drawn over the shots
        config = {"title": film.title, "sub": f"{film.author} · {film.year}", "shots": [round(x, 2) for x in starts[1:]]}
        (out / "motion.html").write_text((HERE / "book_motion.html").read_text(encoding="utf-8").replace(
            "/*CONFIG*/{", f"{json.dumps(config, ensure_ascii=False)} || {{", 1), encoding="utf-8")
        video = out / "reel.mp4"
        mockingbird("motion", {"script": str(out / "motion.html"), "path": str(out / "base.mp4"), "fps": 30,
                               "captions": srt(words), "out": str(video)})
    (out / "caption.txt").write_text(film.caption, encoding="utf-8")
    return video


# ---------- Instagram ----------

def fb(r):
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text}")
    return r.json()


def upload(video: Path, caption: str) -> str:
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
    demo, dry, reddit, book = (a in sys.argv for a in ("--demo", "--dry-run", "--reddit", "--book"))
    hist_file = HERE / ("reddit_history.json" if reddit else "book_history.json" if book else "history.json")
    history = json.loads(hist_file.read_text()) if hist_file.exists() else []
    out = HERE / "out" / time.strftime("%Y-%m-%d_%H%M%S")

    if demo:
        video, key = build(trivia_slides(DEMO), DEMO.caption, out), None
    elif reddit:
        for sub in random.sample(SUBS, len(SUBS)):
            try:
                posts = fetch_reddit(sub)
            except requests.RequestException as e:  # one unreachable feed shouldn't sink the run
                print(f"skipping r/{sub}: {e}")
                continue
            story, post = pick_story(sub, posts, history)
            if story:
                break
        else:
            sys.exit("no suitable Reddit story found")
        caption, key = story.caption, post["id"]
        clips = [p for p in (HERE / "bg").glob("*") if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm")]
        if not clips:
            print("no gameplay clips in bg/ - using a plain background")
        video = build(reddit_slides(sub, post["author"], story.title, story.story), caption, out,
                      pause=0.15, bg=random.choice(clips) if clips else None)
    elif book:
        name = sys.argv[sys.argv.index("--book") + 1:][:1]
        film = generate_film(history, name[0] if name and not name[0].startswith("--") else None)
        caption, key = film.caption, film.topic
        video = build_film(film, out)
    else:
        p = generate(history)
        caption, key = p.caption, p.topic
        video = build(trivia_slides(p), caption, out)

    print("built", video)
    if demo or dry:
        return
    print("posted", upload(video, caption))
    hist_file.write_text(json.dumps(history + [key], indent=1))


if __name__ == "__main__":
    main()
