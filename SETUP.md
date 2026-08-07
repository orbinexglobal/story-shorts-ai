# SETUP.md — StoryShorts AI

This guide assumes you've never done any of this before. Follow it in
order. It takes about 45-60 minutes the first time, almost all of it
waiting on account/API setup screens rather than typing.

By the end, you'll be able to run:

```bash
python main.py --test    # makes 5 Shorts, renders them to output/, doesn't upload
python main.py           # makes 5 Shorts, uploads them to YouTube
```

and have GitHub Actions run it automatically once a day (each run makes
the full 5-Short batch).

---

## 0. Before you start — prerequisites

You need a local `.env` file with your API keys and YouTube credentials
(the sections below show how to get them):

```
OPENROUTER_API_KEY=sk-or-...
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...
```

and at least one source video in `assets/gameplay/` to cut Shorts from.

---

## 1. Install Python

You need Python 3.11 or newer.

- **Windows**: Download from https://www.python.org/downloads/ and run
  the installer. **Check the box "Add Python to PATH"** on the first
  screen before clicking Install.
- **macOS**: Install via [Homebrew](https://brew.sh): `brew install python`
- **Linux**: `sudo apt install python3 python3-pip` (Debian/Ubuntu) or
  your distro's equivalent.

Verify it worked:

```bash
python3 --version
```

You should see `Python 3.11.x` or higher.

## 2. Install ffmpeg

This project renders video with ffmpeg directly — no other video
editor is required.

- **Windows**: Download a build from https://www.gyan.dev/ffmpeg/builds/
  (get the "essentials" zip), unzip it somewhere permanent (e.g.
  `C:\ffmpeg`), then add `C:\ffmpeg\bin` to your System PATH
  (Settings → System → About → Advanced system settings → Environment
  Variables → edit `Path` → add the folder).
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

Verify:

```bash
ffmpeg -version
ffprobe -version
```

Both should print a version number, not "command not found".

## 3. Get the project onto your machine and into GitHub

1. Unzip the project you were given, or clone it if it's already a
   git repo.
2. Go to https://github.com/new and create a new repository (private
   is fine — recommended, since this repo will reference your
   channel's content strategy). Don't initialize it with a README
   (you already have one).
3. In a terminal, inside the project folder:

   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

## 4. Install Python dependencies locally

```bash
cd story-shorts-ai
pip install -r requirements.txt
```

If `pip` isn't found, try `pip3` or `python3 -m pip install -r requirements.txt`.

## 5. Add your gameplay and music assets

The pipeline never downloads gameplay footage — you provide it, and
you're responsible for making sure you have the rights to use it.

1. Put one or more `.mp4` (or `.mov`/`.mkv`/`.webm`) gameplay clips
   into `assets/gameplay/`. Each should be at least ~60 seconds long
   so there's room to pick a random start point.
2. Put one or more royalty-free music tracks (`.mp3`/`.wav`/`.m4a`/`.ogg`)
   into `assets/music/`. Make sure you actually have the rights to use
   each track — check the license it was released under.

Quick local test once you have at least one file in each folder:

```bash
python main.py --test
```

If gameplay/music are still missing, the health check will tell you
exactly that instead of crashing partway through.

## 6. Create a Gemini API key (recommended — free tier)

1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account.
3. Click "Create API key". Choose or create a Google Cloud project
   when prompted.
4. Copy the key that appears.

You'll add this as a GitHub Secret (`GEMINI_API_KEY`) in step 9, and
optionally as a local environment variable for testing (step 8).

## 7. Create an OpenRouter API key (free-tier fallback)

1. Go to https://openrouter.ai and sign up.
2. Go to https://openrouter.ai/keys → "Create Key".
3. Copy the key.

This becomes `OPENROUTER_API_KEY`.

## 7b. Create a Groq API key (second fallback)

1. Go to https://console.groq.com/keys
2. Sign up / sign in, then "Create API Key".
3. Copy the key.

This becomes `GROQ_API_KEY`.

> You don't need all three — the pipeline tries them in the order set
> in `config/config.yaml` (`ai_providers.fallback_order`) and skips any
> provider whose key isn't set. But having at least two configured
> means one provider having a bad day doesn't stop your channel.

## 8. Set up the YouTube Data API and get a refresh token

This is the longest step. Take it slowly.

### 8a. Create a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Click the project dropdown at the top → "New Project".
3. Name it anything (e.g. "StoryShorts AI") → Create.
4. Make sure it's selected in the project dropdown.

### 8b. Enable the YouTube Data API v3

1. Go to https://console.cloud.google.com/apis/library/youtube.googleapis.com
2. Make sure your new project is selected (top bar).
3. Click "Enable".

### 8c. Configure the OAuth consent screen

1. Go to https://console.cloud.google.com/apis/credentials/consent
2. Choose "External" → Create.
3. Fill in an app name (e.g. "StoryShorts AI"), your email for the
   support email and developer contact fields. Save and continue
   through the Scopes and Test users screens (you can skip adding
   scopes here — they're requested in code).
4. On the "Test users" screen, add your own Google account's email
   address. While the app is in "Testing" mode, only test users you
   list here can authorize it — that's fine, it's only you.
5. Save and finish.

### 8d. Create OAuth client credentials

1. Go to https://console.cloud.google.com/apis/credentials
2. Click "Create Credentials" → "OAuth client ID".
3. Application type: **Desktop app**. Name it anything.
4. Click Create, then "Download JSON" on the credential that appears.
5. Save that file as `client_secret.json` in your project folder
   (it's already in `.gitignore` — never commit it).

### 8e. Generate your refresh token

Run the helper script included in this project:

```bash
pip install google-auth-oauthlib   # already in requirements.txt
python scripts/get_youtube_refresh_token.py --client-secrets client_secret.json
```

This opens your browser. Sign in with the same Google account that
owns (or manages) your YouTube channel, and approve the upload
permission. You'll see a warning that the app isn't verified — click
"Advanced" → "Go to StoryShorts AI (unsafe)" — this is expected for an
app still in Testing mode that only you use.

The script prints three values:

```
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...
```

Copy all three somewhere safe — you'll paste them into GitHub Secrets
next.

## 9. Add everything as GitHub Secrets

1. In your GitHub repo, go to Settings → Secrets and variables →
   Actions → "New repository secret".
2. Add each of these one at a time (name exactly as shown, value from
   the steps above):

   | Secret name              | From step |
   |---------------------------|-----------|
   | `GEMINI_API_KEY`           | 6         |
   | `OPENROUTER_API_KEY`       | 7         |
   | `GROQ_API_KEY`              | 7b        |
   | `YOUTUBE_CLIENT_ID`         | 8e        |
   | `YOUTUBE_CLIENT_SECRET`     | 8e        |
   | `YOUTUBE_REFRESH_TOKEN`     | 8e        |

## 10. Test locally with real credentials

Export the same variables as environment variables in your terminal
(this is temporary, just for this session):

**macOS/Linux:**
```bash
export GEMINI_API_KEY="..."
export OPENROUTER_API_KEY="..."
export GROQ_API_KEY="..."
```

**Windows (PowerShell):**
```powershell
$env:GEMINI_API_KEY="..."
$env:OPENROUTER_API_KEY="..."
$env:GROQ_API_KEY="..."
```

Then run:

```bash
python main.py --test
```

This generates a real story, real narration, and a real rendered
video in `output/`, but does **not** upload. Watch the video. If it
looks right, you're ready for a real upload:

```bash
python main.py
```

(This one will actually publish to your YouTube channel using the
visibility set in `config/config.yaml` — `youtube.visibility`, default
`"public"`. Set it to `"private"` or `"unlisted"` first if you want to
review uploads manually before they go public.)

## 11. Turn on GitHub Actions

Actions are enabled by default once you push a workflow file, which is
already included at `.github/workflows/pipeline.yml`. To confirm and
trigger a first run manually:

1. Go to your repo → "Actions" tab.
2. If prompted, click "I understand my workflows, go ahead and enable
   them".
3. Click "StoryShorts AI Pipeline" in the left sidebar → "Run
   workflow" → Run workflow. This runs it once immediately so you can
   check it works before waiting for the schedule.
4. After it finishes, click into the run to see the console logs.

After that, it runs automatically once a day (cron `30 8 * * *` in
`.github/workflows/pipeline.yml`). Each run makes the full daily batch
of 5 Shorts (`config/config.yaml` → `schedule.shorts_per_day`).

## 12. Ongoing maintenance

You shouldn't need to do much. Occasionally:

- Check YouTube Studio analytics.
- Check the Actions tab for any failed runs (you'll see a red ✗; click
  in and read the logs — the health check step gives specific, plain
  English reasons for most failures).
- Add fresh gameplay/music assets occasionally for variety.
- Watch your free-tier usage on each provider's dashboard; if one
  starts rejecting requests, the pipeline automatically falls back to
  the next configured provider.

---

## Testing

```bash
python -m pytest tests/
```

## Common errors and solutions

**"Config file not found at config/config.yaml"**
You're running `main.py` from the wrong directory. `cd` into the
`story-shorts-ai` folder first.

**"ffmpeg is not installed or not on PATH"**
Revisit step 2. On Windows this is almost always a PATH problem —
restart your terminal after editing PATH, or restart your computer.

**"No text-generation API key is set"**
None of `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` are set
in your environment (locally) or GitHub Secrets (in Actions). Revisit
steps 6-7b and 9-10.

**"assets/gameplay is empty"** / **"assets/music is empty"**
Add files per step 5.

**"Missing YouTube upload credentials"**
Only shown on a real (non `--test`) run. Revisit step 8 and make sure
all three `YOUTUBE_*` values are set.

**GitHub Actions run fails at "Install ffmpeg"**
Rare, usually a transient Ubuntu package mirror issue — click
"Re-run jobs".

**YouTube upload fails with an auth error even though secrets are set**
Refresh tokens can be invalidated if you change your Google account
password, revoke app access, or don't use the app for 6 months (for
apps still in "Testing" mode on the OAuth consent screen). Re-run step
8e to generate a new refresh token and update the
`YOUTUBE_REFRESH_TOKEN` secret.

**Videos are being rejected / flagged as reused or low-value by YouTube**
This is a content-quality problem, not a bug — see `docs/PHASES.md`
and the story-scoring thresholds in `config/config.yaml`
(`story.min_acceptable_score`). Raising that threshold produces fewer
but higher-quality uploads.
