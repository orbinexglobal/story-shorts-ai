"""
Story generation and scoring.

Generates `config.story.candidates_per_run` independent story
candidates, has each one self-scored by the model across six
dimensions (hook, curiosity, emotional flow, ending, simplicity,
retention), and keeps only the highest-scoring one — discarding the
rest, per the project spec. If the best candidate doesn't clear
`config.story.min_acceptable_score`, the run is aborted rather than
publishing a weak story.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config.logging_setup import get_logger
from config.settings import Config
from providers.base import TextProvider
from utils.json_extract import JsonExtractionError, extract_json

logger = get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "story_prompt.txt"
_SCORE_FIELDS = (
    "hook_score", "curiosity_score", "emotional_flow_score",
    "ending_score", "simplicity_score", "retention_score",
)
_MAX_ATTEMPTS = 3

# Non-Latin scripts (CJK, Cyrillic, Arabic, etc.) occasionally leak into
# free-model output as tokenizer garbage. The narration must be clean,
# readable English, so such stories are rejected and regenerated.
_GARBAGE_SCRIPT = re.compile(
    r"[\u0400-\u04FF"      # Cyrillic
    r"\u4E00-\u9FFF"       # CJK
    r"\u0600-\u06FF"       # Arabic
    r"\u0B80-\u0BFF"       # Tamil
    r"\u0E00-\u0E7F"       # Thai
    r"\u0900-\u097F"       # Devanagari
    r"]"
)

# Names of politicians / actors / athletes / other public figures.
# Stories must be pure fiction, so any hit (case-insensitive substring)
# is treated as a policy violation and the candidate is regenerated.
# Full names are preferred to keep false positives out of ordinary
# narration; highly distinctive single surnames (trump, putin, modi...)
# are listed on their own because their bare form is unmistakable.
_REAL_PERSON_NAMES = frozenset(
    name.lower()
    for name in [
        # ---- US presidents ----
        "george washington", "john adams", "thomas jefferson",
        "james madison", "james monroe", "john quincy adams",
        "andrew jackson", "martin van buren", "william henry harrison",
        "john tyler", "james k polk", "zachary taylor", "millard fillmore",
        "franklin pierce", "james buchanan", "abraham lincoln",
        "andrew johnson", "ulysses grant", "rutherford hayes",
        "james garfield", "chester arthur", "grover cleveland",
        "benjamin harrison", "william mckinley", "theodore roosevelt",
        "william howard taft", "woodrow wilson", "warren harding",
        "calvin coolidge", "herbert hoover", "franklin roosevelt",
        "fdr", "harry truman", "dwight eisenhower", "john f kennedy",
        "jfk", "lyndon johnson", "lbj", "richard nixon", "gerald ford",
        "jimmy carter", "ronald reagan", "george h w bush", "george bush",
        "bill clinton", "hillary clinton", "barack obama", "donald trump",
        "joe biden", "kamala harris", "jd vance", "james vance",
        "mike pence", "mike pompeo", "mike johnson", "kevin mccarthy",
        "paul ryan", "john mccain", "mitt romney", "bernie sanders",
        "elizabeth warren", "nancy pelosi", "chuck schumer", "mitch mcconnell",
        "hakeem jeffries", "ted cruz", "marco rubio", "lindsey graham",
        "alexandria ocasio-cortez", "aoc", "ilhan omar", "rashida tlaib",
        "tulsi gabbard", "pete buttigieg", "gavin newsom", "ron desantis",
        "dick cheney", "al gore", "john kerry", "colin powell",
        "condoleezza rice", "robert kennedy", "robert f kennedy",
        "kristi noem", "sarah huckabee sanders", "glenn youngkin",
        "george santos", "kari lake", "stacey abrams", "andrew cuomo",
        "eric adams", "bill de blasio", "rand paul", "josh hawley",
        # ---- India ----
        "narendra modi", "rahul gandhi", "sonia gandhi", "indira gandhi",
        "rajiv gandhi", "jawaharlal nehru", "nehru", "mahatma gandhi",
        "gandhi", "sardar patel", "vallabhbhai patel", "subhas chandra bose",
        "netaji", "rajendra prasad", "lal bahadur shastri", "shastri",
        "morarji desai", "charan singh", "v p singh", "chandra shekhar",
        "p v narasimha rao", "atal bihari vajpayee", "vajpayee",
        "manmohan singh", "pranab mukherjee", "a p j abdul kalam",
        "abdul kalam", "venkaiah naidu", "droupadi murmu",
        "amit shah", "rajnath singh", "s jaishankar", "nirmala sitharaman",
        "yogi adityanath", "adityanath", "arvind kejriwal", "kejriwal",
        "mamata banerjee", "m k stalin", "k chandrashekar rao",
        "nitish kumar", "naveen patnaik", "hd deve gowda", "h d kumaraswamy",
        "mayawati", "lalu prasad yadav", "mulayam singh yadav",
        "akhilesh yadav", "tejashwi yadav", "sharad pawar",
        "uddhav thackeray", "devendra fadnavis", "eknath shinde",
        "ashok gehlot", "siddaramaiah", "b s yediyurappa",
        "pinarayi vijayan", "hemant soren", "himanta biswa sarma",
        "farooq abdullah", "omar abdullah", "mehbooba mufti",
        "asaduddin owaisi", "owaisi", "smriti irani", "sushma swaraj",
        "nitin gadkari", "raju shetty", "jagdeep dhankhar",
        "jayalalithaa", "m karunanidhi", "kamaraj", "n t rama rao",
        "ntr", "chandrababu naidu", "ys jagan mohan reddy", "jagan",
        "pawan kalyan", "kcr", "manoj tiwari", "kanhaiya kumar",
        "br ambedkar", "ambedkar", "bhagat singh",
        "savarkar", "gandhi",
        # ---- UK & Europe ----
        "winston churchill", "margaret thatcher", "tony blair",
        "david cameron", "theresa may", "boris johnson", "rishi sunak",
        "keir starmer", "liz truss", "gordon brown", "john major",
        "jeremy corbyn", "nigel farage", "jacob rees-mogg", "nigel farage",
        "keir starmer", "angela merkel", "olaf scholz", "helmut kohl",
        "gerhard schroeder", "konrad adenauer", "adolf hitler", "hitler",
        "emmanuel macron", "marie le pen", "marine le pen", "nicolas sarkozy",
        "francois hollande", "jacques chirac", "francois mitterrand",
        "charles de gaulle", "nazi", "napoleon", "napoleon bonaparte",
        "vladimir lenin", "lenin", "joseph stalin", "stalin", "leonid brezhnev",
        "mikhail gorbachev", "gorbachev", "boris yeltsin", "nikita khrushchev",
        "vladimir putin", "putin", "dmitry medvedev", "sergey lavrov",
        "yevgeny prigozhin", "volodymyr zelensky", "zelensky", "petro poroshenko",
        "victor yanukovych", "alexander lukashenko", "lukashenko",
        "giorgia meloni", "silvio berlusconi", "mario draghi", "matteo renzi",
        "giuseppe conte", "benito mussolini", "mussolini", "francisco franco",
        "pedro sanchez", "mariano rajoy", "jose maria aznar", "juan carlos",
        "viktor orban", "orban", "vaclav havel", "lech walesa",
        "andrzej duda", "petr pavel", "andrej babis",
        "zuzana caputova", "robert fico", "klaus iohannis", "maia sandu",
        "ursula von der leyen", "charles michel", "jean-claude juncker",
        "david cameron", "mark rutte", "geert wilders",
        "alexander stubb", "sauli niinisto", "erling haaland",
        # ---- Asia ----
        "xi jinping", "mao zedong", "mao", "deng xiaoping",
        "jiang zemin", "hu jintao", "jinping", "kim jong un", "kim jong-il",
        "kim il sung", "moon jae-in", "park geun-hye", "yoon suk-yeol",
        "shinzo abe", "fumio kishida", "shigeru ishiba", "taro aso",
        "imran khan", "nawaz sharif", "shehbaz sharif",
        "asif ali zardari", "benazir bhutto", "zulfikar ali bhutto",
        "pervez musharraf", "arif alvi", "muhammad yunus", "sheikh hasina",
        "khaleda zia", "ho chi minh", "nguyen phu trong", "to lam",
        "joko widodo", "prabowo subianto", "sukarno", "suharto",
        "rodrigo duterte", "ferdinand marcos", "bongbong marcos",
        "lee kuan yew", "lee hsien loong", "mahathir mohamad", "najib razak",
        "anwar ibrahim", "hun sen", "hun manet", "aung san suu kyi",
        "suu kyi", "than shwe", "u nu",
        # ---- Middle East ----
        "netanyahu", "benjamin netanyahu", "yitzhak rabin", "golda meir",
        "shimon peres", "ehud olmert", "ariel sharon", "david ben-gurion",
        "ben-gurion", "yasser arafat", "arafat", "mahmoud abbas",
        "ismail haniyeh", "bashar al-assad", "assad", "hafez al-assad",
        "muammar gaddafi", "gaddafi", "hosni mubarak", "mubarak",
        "gamal abdel nasser", "nasser", "anwar sadat", "sadat",
        "abdel fattah el-sisi", "sisi", "mohammed morsi", "saddam hussein",
        "saddam", "ali khamenei", "khamenei", "ayatollah khomeini",
        "khomeini", "hassan rouhani", "ebrahim raisi", "raisi",
        "mahmoud ahmadinejad", "qasem soleimani", "mohammed bin salman",
        "mohammed bin zayed", "king salman", "recep tayyip erdogan",
        "erdogan", "mustafa kemal ataturk", "ataturk", "osama bin laden",
        "osama binladen", "abu bakr al-baghdadi", "ayman al-zawahiri",
        "mullah omar", "hamas", "isis", "taliban", "al-qaeda",
        # ---- Africa ----
        "nelson mandela", "jacob zuma", "thabo mbeki", "cyril ramaphosa",
        "robert mugabe", "mugabe", "julius nyerere", "jomo kenyatta",
        "uhuru kenyatta", "william ruto", "idi amin", "kwame nkrumah",
        "haile selassie", "omar al-bashir", "paul kagame", "yoweri museveni",
        "muhammadu buhari", "bola tinubu", "olusegun obasanjo",
        "goodluck jonathan", "atiku abubakar", "peter obi",
        "leopold senghor", "patrice lumumba", "joseph kabila", "felix tshisekedi",
        "abdelaziz bouteflika", "kofi annan", "desmond tutu",
        # ---- Latin America ----
        "fidel castro", "raul castro", "che guevara", "guevara",
        "hugo chavez", "nicolas maduro", "maduro", "evo morales",
        "daniel ortega", "salvador allende", "augusto pinochet",
        "jair bolsonaro", "bolsonaro", "luiz inacio lula da silva",
        "lula", "dilma rousseff", "getulio vargas", "cristina kirchner",
        "nestor kirchner", "mauricio macri", "javier milei", "milei",
        "andres manuel lopez obrador", "amlo", "claudia sheinbaum",
        "vicente fox", "enrique pena nieto", "felipe calderon",
        "juan peron", "eva peron", "simon bolivar", "jose mujica",
        "nayib bukele", "manuel zelaya", "xochitl garcia",
        # ---- Canada / Australia / NZ ----
        "justin trudeau", "trudeau", "pierre trudeau", "stephen harper",
        "jean chretien", "brian mulroney", "mackenzie king",
        "scott morrison", "kevin rudd", "julia gillard", "malcolm turnbull",
        "tony abbott", "julie bishop", "anthony albanese", "peter dutton",
        "jacinda ardern", "john key", "helen clark", "christopher luxon",
        # ---- Royals / historical ----
        "queen elizabeth", "princess diana", "king charles", "prince charles",
        "prince william", "prince harry", "meghan markle", "king george",
        "king henry", "king edward", "king louis", "queen victoria",
        "catherine middleton", "kate middleton",
        # ---- Business / tech ----
        "elon musk", "bill gates", "steve jobs", "mark zuckerberg",
        "jeff bezos", "oprah winfrey", "warren buffett", "jack ma",
        "sundar pichai", "satya nadella", "mukesh ambani", "gautam adani",
        "ambani", "adani", "zuckerberg", "bezos",
        # ---- Actors / musicians / celebrities ----
        "taylor swift", "justin bieber", "kim kardashian", "kanye west",
        "beyonce", "beyoncé", "ariana grande", "selena gomez", "dua lipa",
        "leonardo dicaprio", "tom cruise", "brad pitt", "angelina jolie",
        "johnny depp", "robert downey", "chris hemsworth", "scarlett johansson",
        "michael jackson", "freddie mercury", "elton john", "ed sheeran",
        "rihanna", "the weeknd", "eminem", "jay-z", "jennifer lopez",
        "shakira", "miley cyrus", "katy perry", "lady gaga", "madonna",
        "dwayne johnson", "vin diesel", "will smith", "morgan freeman",
        "denzel washington", "keanu reeves", "ryan reynolds", "hugh jackman",
        "jackie chan", "bruce lee", "david beckham", "zendaya",
        "kim jong", "oprah", "diddy", "jay leno", "jimmy fallon",
        # ---- Athletes ----
        "cristiano ronaldo", "lionel messi", "neymar", "virat kohli",
        "ms dhoni", "rohit sharma", "sachin tendulkar", "tendulkar",
        "michael jordan", "lebron james", "kobe bryant", "tiger woods",
        "usain bolt", "muhammad ali", "floyd mayweather", "conor mcgregor",
        "ronaldo", "messi", "dhoni", "kohli",
        # ---- Indian film stars ----
        "shah rukh khan", "shahrukh khan", "salman khan", "amitabh bachchan",
        "aamir khan", "ranveer singh", "deepika padukone", "priyanka chopra",
        "ranbir kapoor", "katrina kaif",         "srk", "hrithik roshan",
        "akshay kumar", "ajay devgn", "sanjay dutt", "prabhas",
        "allu arjun", "mahesh babu", "ajith", "rajinikanth",
        "kamal haasan", "nayanthara", "kiara advani",
        "alia bhatt", "anushka sharma", "kareena kapoor", "karisma kapoor",
        "nawazuddin", "rajkummar rao", "ayushmann khurrana", "vicky kaushal",
    ]
)


def _contains_real_person(text: str) -> bool:
    lowered = text.lower()
    return any(name in lowered for name in _REAL_PERSON_NAMES)


class StoryQualityError(Exception):
    """Raised when no generated candidate clears the quality threshold."""


@dataclass(frozen=True)
class StoryCandidate:
    text: str
    scores: dict[str, float]

    @property
    def overall_score(self) -> float:
        return sum(self.scores.values()) / len(self.scores)


def _build_prompt(cfg: Config) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(min_seconds=cfg.story.min_seconds, max_seconds=cfg.story.max_seconds)


def generate_story(text_provider: TextProvider, cfg: Config) -> StoryCandidate:
    """
    Generate several story candidates, score them, and return the best.

    Retries up to `_MAX_ATTEMPTS` rounds: unparseable, non-Latin-garbage,
    or low-scoring outputs are discarded and the provider is asked again
    (the text chain falls through to another model on repeated failure).

    Raises:
        StoryQualityError: if no clean candidate clears the threshold.
    """
    prompt = _build_prompt(cfg)

    for round_no in range(1, _MAX_ATTEMPTS + 1):
        candidates: list[StoryCandidate] = []

        for i in range(cfg.story.candidates_per_run):
            # Thinking models spend tokens on reasoning before emitting text, so
            # a generous output cap is required to avoid truncated JSON.
            raw = text_provider.generate(prompt, max_tokens=8192)
            try:
                parsed = extract_json(raw)
                story_text = str(parsed["story"]).strip()
                scores = {field: float(parsed[field]) for field in _SCORE_FIELDS}
            except (JsonExtractionError, KeyError, ValueError) as exc:
                logger.warning(
                    "Round %d, candidate %d/%d unparseable: %s",
                    round_no, i + 1, cfg.story.candidates_per_run, exc,
                )
                continue

            if not story_text or _GARBAGE_SCRIPT.search(story_text):
                logger.warning(
                    "Round %d, candidate %d/%d discarded: non-Latin garbage",
                    round_no, i + 1, cfg.story.candidates_per_run,
                )
                continue

            if _contains_real_person(story_text):
                logger.warning(
                    "Round %d, candidate %d/%d discarded: mentions a real person",
                    round_no, i + 1, cfg.story.candidates_per_run,
                )
                continue

            candidate = StoryCandidate(text=story_text, scores=scores)
            candidates.append(candidate)
            logger.info(
                "Round %d, candidate %d/%d generated, overall_score=%.1f",
                round_no, i + 1, cfg.story.candidates_per_run, candidate.overall_score,
            )

        if not candidates:
            logger.warning("Attempt %d/%d produced no usable candidate", round_no, _MAX_ATTEMPTS)
            continue

        best = max(candidates, key=lambda c: c.overall_score)
        if best.overall_score < cfg.story.min_acceptable_score:
            logger.warning(
                "Attempt %d/%d: best candidate scored %.1f (below %.1f); retrying",
                round_no, _MAX_ATTEMPTS, best.overall_score, cfg.story.min_acceptable_score,
            )
            continue

        logger.info(
            "Selected best candidate (score=%.1f) out of %d",
            best.overall_score, len(candidates),
        )
        return best

    raise StoryQualityError(
        f"No clean story cleared the {cfg.story.min_acceptable_score:.1f} "
        "quality threshold after multiple attempts."
    )
