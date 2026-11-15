"""Daily reels -> AI voice -> Instagram. Two modes: trivia infographics, or narrated Reddit stories.

Claude runs through the Claude Code CLI (`claude -p`, your Claude login), so no API key is needed.
Env (only for posting): IG_USER_ID, IG_TOKEN
  python reelbot.py              trivia infographic reel, posted
  python reelbot.py --reddit     drama/revenge Reddit story reel (r/AmItheAsshole, r/pettyrevenge, ...), posted
  add --dry-run to build without posting
  python reelbot.py --demo       render a built-in trivia sample (no API calls) to test the pipeline
"""
import asyncio, html, json, os, random, re, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

import edge_tts, requests
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

HERE = Path(__file__).parent
VOICE = "en-US-BrianMultilingualNeural"  # newer, more human voices: Andrew/Ava/Emma/BrianMultilingualNeural
RATE = "+50%"  # 1.5x speed
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


# ---------- Claude ----------

def ask(prompt: str, schema):
    """Structured answer from Claude via the Claude Code CLI, using your Claude login instead of an API key.
    --tools "" turns off every tool: the prompt carries untrusted Reddit text, so Claude may only answer."""
    exe = shutil.which("claude")
    if not exe:
        sys.exit("Claude Code CLI not found: install it and run `claude` once to log in")
    r = subprocess.run([exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema.model_json_schema()),
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


def trivia_slides(post: Post):
    cards = [("DID YOU KNOW?", post.title, "", post.hook)]
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


def write_ass(spoken, boxes, path: Path):
    """Highlighter: a translucent gold box over each word on the card while it is spoken."""
    def ts(s):
        return f"{int(s // 3600)}:{int(s % 3600 // 60):02}:{s % 60:05.2f}"
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
    words = []
    with open(mp3, "wb") as f:
        async for c in edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary").stream():
            if c["type"] == "audio":
                f.write(c["data"])
            elif c["type"] == "WordBoundary":
                words.append((c["offset"] / 1e7, (c["offset"] + c["duration"]) / 1e7, c["text"]))
    return words


async def voice(items):
    return [await speak(t, p) for t, p in items]  # one at a time: parallel requests get dropped (NoAudioReceived)


def run(*args, cwd=None):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *map(str, args)], check=True, cwd=cwd)


def duration(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(path)], capture_output=True, text=True, check=True).stdout)


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
    demo, dry, reddit = "--demo" in sys.argv, "--dry-run" in sys.argv, "--reddit" in sys.argv
    hist_file = HERE / ("reddit_history.json" if reddit else "history.json")
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
