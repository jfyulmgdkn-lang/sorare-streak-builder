import os
import asyncio
import math
import unicodedata
from datetime import datetime, timezone
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv

load_dotenv()

SORARE_API_URL = "https://api.sorare.com/graphql"
SORARE_API_KEY = os.getenv("SORARE_API_KEY")

CURRENT_SEASON_YEAR = 2026

DISCORD_TO_SORARE: Dict[int, str] = {
    652050886985777189: "adixyz",
    486198451626049537: "bartholomaus",
    628316534539812865: "pidel",
    463614748366340096: "sweggaausbrazil",
    235803999167709195: "golden_goal-699e9a95-45ec-4764-8771-a26226e5d4e9",
    344185350161170442: "orsa-b186064b-a1fd-427c-b15a-8f47077f11ef",
    228944337793318912: "rabise",
    246679363502735370: "lublol",
    1083049525830242384: "ksc_jockel",
    209387327229919233: "once",
    593253225973547019: "lost_drian",
    898242220740718593: "podrickson",
    1162305763306385441: "salapele-99",
    712804219698282497: "kurve1887",
    543042637087637504: "max-ntl-f9ab356a-f9e9-4a11-b76f-2a7fd50bc316",
    376728638734860290: "fidelitas-14c9ae75-c292-474e-8608-1cc1b62d11ba",
    344541166147993601: "cano35",
}

# Sorare 27: eigenständige Pro/Hot-Streak-Wettbewerbe Limited + Rare.
PRO_COMPETITIONS = {
    "english": "English League",
    "ligue1": "Ligue 1",
    "laliga": "LALIGA EA SPORTS",
    "bundesliga": "Bundesliga",
    "mlspa": "MLS",
    "portugal": "Liga Portugal",
    "eredivisie": "Eredivisie",
    "jupiler": "Jupiler Pro League",
    "scotland": "Scottish Premiership",
    "jleague": "J.League",
    "championship": "English Second Division",
    "contender": "Contender",
}

# Für IN-SEASON Contender dürfen ausschließlich diese Wettbewerbe rein.
# Wir prüfen zuerst die bekannten Sorare-Slugs und nutzen die Namen nur
# als Fallback. Dadurch können MLS, Champions League usw. nicht mehr
# versehentlich als Contender In-Season durchrutschen.
CONTENDER_INSEASON_SLUGS = {
    "2-bundesliga",
    "austrian-bundesliga",
    "1-hnl",
    "ligue-2-fr",
}

# In-Season Contender besteht aktuell aus diesen vier Pools.
CONTENDER_INSEASON_ALIASES = [
    ("2 bundesliga", "2. Bundesliga"),
    ("2-bundesliga", "2. Bundesliga"),
    ("2 bundesliga de", "2. Bundesliga"),
    ("austrian bundesliga", "Austrian Bundesliga"),
    ("austrian-bundesliga", "Austrian Bundesliga"),
    ("bundesliga at", "Austrian Bundesliga"),
    ("1 hnl", "SuperSport HNL"),
    ("1-hnl", "SuperSport HNL"),
    ("supersport hnl", "SuperSport HNL"),
    ("hnl", "SuperSport HNL"),
    ("croatian", "SuperSport HNL"),
    ("ligue 2", "Ligue 2 BKT"),
    ("ligue-2", "Ligue 2 BKT"),
    ("ligue 2 fr", "Ligue 2 BKT"),
    ("ligue-2-fr", "Ligue 2 BKT"),
]

# Vom Nutzer gewünschter Classic-Pool für den einen möglichen Classic-Slot
# in Contender. Zusätzlich sind die vier In-Season-Contender-Ligen erlaubt.
CONTENDER_CLASSIC_ALIASES = CONTENDER_INSEASON_ALIASES + [
    ("laliga hypermotion", "LALIGA HYPERMOTION"),
    ("segunda division", "LALIGA HYPERMOTION"),
    ("laliga-2", "LALIGA HYPERMOTION"),
    ("super lig", "Süper Lig"),
    ("turkey", "Süper Lig"),
    ("serie a", "Serie A"),
    ("superliga argentina", "Superliga Argentina de Fútbol"),
    ("argentina", "Superliga Argentina de Fútbol"),
    ("liga mx", "Liga MX"),
    ("mexico", "Liga MX"),
    ("brasileirao", "Campeonato Brasileiro Série A"),
    ("brasileiro serie a", "Campeonato Brasileiro Série A"),
    ("brazil", "Campeonato Brasileiro Série A"),
    ("serie b", "Serie B"),
    ("danish superliga", "Danish Superliga"),
    ("superliga dk", "Danish Superliga"),
    ("denmark", "Danish Superliga"),
    ("eliteserien", "Eliteserien"),
    ("norway", "Eliteserien"),
    ("super league", "Super League"),
    ("greece", "Super League"),
    ("russian premier league", "Russian Premier League"),
    ("russia", "Russian Premier League"),
    ("primera a", "Primera A"),
    ("colombia", "Primera A"),
    ("primera division del peru", "Primera División del Perú"),
    ("peru", "Primera División del Perú"),
    ("primera division de chile", "Primera División de Chile"),
    ("chile", "Primera División de Chile"),
    ("liga pro", "Liga Pro"),
    ("ecuador", "Liga Pro"),
    ("chinese super league", "Chinese Super League"),
    ("china", "Chinese Super League"),
]

DEDICATED_ALIASES = {
    "mlspa": [
        ("mlspa", "MLS"),
        ("mls", "MLS"),
        ("major league soccer", "MLS"),
    ],
    "english": [
        ("premier-league-gb-eng", "Premier League"),
        ("premier league", "Premier League"),
        ("english league", "English League"),
    ],
    "ligue1": [
        ("ligue-1-fr", "Ligue 1"),
        ("ligue 1", "Ligue 1"),
    ],
    "laliga": [
        ("laliga-es", "LALIGA EA SPORTS"),
        ("laliga ea sports", "LALIGA EA SPORTS"),
        ("laliga ea", "LALIGA EA SPORTS"),
        ("primera division spain", "LALIGA EA SPORTS"),
    ],
    "bundesliga": [
        ("bundesliga-de", "Bundesliga"),
        ("bundesliga", "Bundesliga"),
    ],
    "portugal": [
        ("primeira-liga-pt", "Liga Portugal"),
        ("primeira liga", "Liga Portugal"),
        ("liga portugal", "Liga Portugal"),
    ],
    "eredivisie": [
        ("eredivisie", "Eredivisie"),
        ("vriendenloterij eredivisie", "Eredivisie"),
    ],
    "jupiler": [
        ("jupiler-pro-league", "Jupiler Pro League"),
        ("jupiler pro league", "Jupiler Pro League"),
    ],
    "scotland": [
        ("scottish-premiership", "Scottish Premiership"),
        ("scottish premiership", "Scottish Premiership"),
        ("premiership scotland", "Scottish Premiership"),
    ],
    "jleague": [
        ("j1-league", "J.League"),
        ("j league", "J.League"),
        ("j1 league", "J.League"),
        ("j league division 1", "J.League"),
    ],
    "championship": [
        ("english-championship", "English Second Division"),
        ("championship", "English Second Division"),
        ("english second division", "English Second Division"),
        ("english second division players", "English Second Division"),
        ("efl championship", "English Second Division"),
    ],
}



USER_CARDS_QUERY = """
query UserCards($userSlug: String!, $after: String) {
  user(slug: $userSlug) {
    slug
    nickname

    cards(first: 100, after: $after) {
      nodes {
        slug
        rarityTyped
        seasonYear

        ... on Card {
          positionTyped
          inSeasonEligible
          powerBreakdown {
            xpBasisPoints
            seasonBasisPoints
            collectionBasisPoints
          }
        }

        anyPlayer {
          slug
          displayName
          activeClub {
            slug
            name
          }

          ... on Player {
            rawPlayerGameScores(last: 40)
          }
        }
      }

      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""




FUTURE_GAMES_QUERY = """
query PlayerFutureGames($playerSlug: String!) {
  anyPlayer(slug: $playerSlug) {
    slug

    anyFutureGames(first: 12) {
      nodes {
        date

        homeTeam {
          slug
          name
        }

        awayTeam {
          slug
          name
        }

        so5Fixture {
          slug
          gameWeek
          shortDisplayName
          longDisplayName
          startDate
          endDate
        }

        ... on Game {
          id
          competition {
            slug
            displayName
          }
        }
      }
    }

    ... on Player {
      activeClub {
        slug
        name
        domesticLeague {
          slug
          displayName
        }
      }
    }
  }
}
"""



PLAYER_SET_PIECE_QUERY = """
query PlayerSetPieces($playerSlug: String!) {
  anyPlayer(slug: $playerSlug) {
    slug

    ... on Player {
      allPlayerGameScores(last: 15) {
        nodes {
          ... on PlayerGameScore {
            anyPlayerGameStats {
              ... on PlayerGameStats {
                gameStarted
                minsPlayed
                penaltyTaken
                cornerTaken
              }
            }
          }
        }
      }
    }
  }
}
"""


STARTER_ODDS_QUERY = """
query StarterOdds($playerSlug: String!) {
  players(slugs: [$playerSlug]) {
    slug

    ... on Player {
      nextClassicFixturePlayingStatusOdds {
        starterOddsBasisPoints
        substituteOddsBasisPoints
        nonPlayingOddsBasisPoints
        reliability
      }
    }
  }
}
"""


COMPETITION_RECENT_GAMES_QUERY = """
query CompetitionRecentGames($competitionSlug: String!, $after: String) {
  football {
    competition(slug: $competitionSlug) {
      slug
      displayName

      pastGames(first: 100, after: $after) {
        nodes {
          id
          date
          statusTyped
          homeScore
          awayScore

          homeTeam {
            slug
            name
          }

          awayTeam {
            slug
            name
          }
        }

        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""


async def sorare_request(
    query: str,
    variables: Optional[dict] = None,
    timeout_seconds: int = 60,
) -> dict:
    if not SORARE_API_KEY:
        raise RuntimeError("SORARE_API_KEY fehlt in der .env-Datei.")

    headers = {
        "APIKEY": SORARE_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "variables": variables or {},
    }

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            SORARE_API_URL,
            headers=headers,
            json=payload,
        ) as response:
            text = await response.text()

            if response.status != 200:
                raise RuntimeError(
                    f"Sorare API HTTP {response.status}: {text}"
                )

            data = await response.json()

            if data.get("errors"):
                messages = [
                    error.get("message", str(error))
                    if isinstance(error, dict)
                    else str(error)
                    for error in data["errors"]
                ]
                raise RuntimeError(
                    "Sorare GraphQL Fehler: " + " | ".join(messages)
                )

            return data.get("data") or {}


def normalize_text(value: Optional[str]) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(
        text.lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", " ")
        .split()
    )


def normalize_position(position: Optional[str]) -> str:
    mapping = {
        "Goalkeeper": "TW",
        "Defender": "VER",
        "Midfielder": "MID",
        "Forward": "ST",
    }
    return mapping.get(position or "", position or "?")


def calculate_l40(scores: List[float]) -> float:
    values = []
    for score in scores or []:
        try:
            if score is not None:
                values.append(float(score))
        except (TypeError, ValueError):
            pass

    return round(sum(values) / len(values), 2) if values else 0.0


def get_sorare_slug_for_discord_user(discord_user_id: int) -> Optional[str]:
    return DISCORD_TO_SORARE.get(int(discord_user_id))


async def get_user_cards(
    user_slug: str,
    rarity: str,
) -> dict:
    after = None
    user_info = None
    cards: List[dict] = []
    rarity = rarity.lower()
    page = 0

    while True:
        page += 1
        data = await sorare_request(
            USER_CARDS_QUERY,
            {"userSlug": user_slug, "after": after},
        )

        user = data.get("user")
        if not user:
            return {"user": None, "cards": []}

        if user_info is None:
            user_info = {
                "slug": user.get("slug"),
                "nickname": user.get("nickname"),
            }

        connection = user.get("cards") or {}
        nodes = connection.get("nodes") or []

        for card in nodes:
            card_rarity = str(card.get("rarityTyped") or "").lower()
            if card_rarity != rarity:
                continue

            player = card.get("anyPlayer") or {}
            club = player.get("activeClub") or {}
            raw_scores = player.get("rawPlayerGameScores") or []
            power_breakdown = card.get("powerBreakdown") or {}

            # Sorare liefert die Bonuswerte in Basis Points:
            # 100 Basis Points = 1,00%.
            xp_bonus_pct = (
                float(power_breakdown.get("xpBasisPoints") or 0) / 100.0
            )
            collection_bonus_pct = (
                float(power_breakdown.get("collectionBasisPoints") or 0) / 100.0
            )

            # Season-Bonus laut Sorare API. Falls die API an dieser Stelle
            # wider Erwarten 0 liefert, gilt für unsere In-Season-Karte
            # weiterhin die vom Nutzer gewünschte 5%-Regel.
            api_season_bonus_pct = (
                float(power_breakdown.get("seasonBasisPoints") or 0) / 100.0
            )

            cards.append({
                "card_slug": card.get("slug"),
                "rarity": card.get("rarityTyped"),
                "season_year": card.get("seasonYear"),
                "api_in_season_eligible": bool(card.get("inSeasonEligible")),
                # Für 2026/27 behandeln wir Karten der Saison 2026 als
                # aktuelle Saison. Die tatsächliche Contender-In-Season-
                # Berechtigung wird beim Wettbewerbsfilter zusätzlich über
                # inSeasonEligible geprüft.
                "current_season_card": card.get("seasonYear") == CURRENT_SEASON_YEAR,
                "in_season": card.get("seasonYear") == CURRENT_SEASON_YEAR,
                "classic": card.get("seasonYear") != CURRENT_SEASON_YEAR,
                "position_raw": card.get("positionTyped"),
                "position": normalize_position(card.get("positionTyped")),
                "player_slug": player.get("slug"),
                "player_name": player.get("displayName"),
                "club_slug": club.get("slug"),
                "club_name": club.get("name"),
                "l40": calculate_l40(raw_scores),
                "xp_bonus_pct": round(xp_bonus_pct, 2),
                "collection_bonus_pct": round(collection_bonus_pct, 2),
                "api_season_bonus_pct": round(api_season_bonus_pct, 2),
            })

        page_info = connection.get("pageInfo") or {}

        print(
            f"[Karten Seite {page}] {len(nodes)} geprüft | "
            f"{len(cards)} {rarity.title()}-Karten gefunden"
        )

        if not page_info.get("hasNextPage"):
            break

        after = page_info.get("endCursor")
        if not after:
            break

        await asyncio.sleep(0.08)

    return {"user": user_info, "cards": cards}


async def get_cards_for_discord_user(
    discord_user_id: int,
    rarity: str,
) -> dict:
    sorare_slug = get_sorare_slug_for_discord_user(discord_user_id)

    if not sorare_slug:
        return {
            "user": None,
            "cards": [],
            "sorare_slug": None,
            "error": "DISCORD_USER_NOT_MAPPED",
        }

    result = await get_user_cards(sorare_slug, rarity)
    result["sorare_slug"] = sorare_slug
    result["error"] = None
    return result



async def get_player_future_games(player_slug: str) -> List[dict]:
    """
    Lädt mehrere zukünftige Spiele eines Spielers.
    Dadurch können wir im Discord zwischen der nächsten und der
    darauffolgenden GameWeek auswählen.
    """
    data = await sorare_request(
        FUTURE_GAMES_QUERY,
        {"playerSlug": player_slug},
    )

    player = data.get("anyPlayer")
    if not player:
        return []

    club = player.get("activeClub") or {}
    club_slug = club.get("slug")
    domestic_league = club.get("domesticLeague") or {}

    connection = player.get("anyFutureGames") or {}
    nodes = connection.get("nodes") or []

    result = []

    for game in nodes:
        fixture = game.get("so5Fixture") or {}
        fixture_slug = fixture.get("slug")

        # Nur echte Sorare-Classic-Fixtures.
        if not fixture_slug:
            continue

        home = game.get("homeTeam") or {}
        away = game.get("awayTeam") or {}

        if club_slug == home.get("slug"):
            home_away = "H"
            opponent = away
        elif club_slug == away.get("slug"):
            home_away = "A"
            opponent = home
        else:
            home_away = "?"
            opponent = {}

        competition = game.get("competition") or {}

        result.append({
            "game_id": game.get("id"),
            "date": game.get("date"),
            "home_away": home_away,
            "team_slug": club_slug,
            "team_name": club.get("name"),
            "domestic_league_slug": domestic_league.get("slug"),
            "domestic_league_name": domestic_league.get("displayName"),
            "opponent_slug": opponent.get("slug"),
            "opponent_name": opponent.get("name"),
            "competition_slug": competition.get("slug"),
            "competition_name": competition.get("displayName"),
            "fixture_slug": fixture_slug,
            "game_week": fixture.get("gameWeek"),
            "fixture_short_name": fixture.get("shortDisplayName"),
            "fixture_long_name": fixture.get("longDisplayName"),
            "fixture_start": fixture.get("startDate"),
            "fixture_end": fixture.get("endDate"),
        })

    result.sort(
        key=lambda row: (
            row.get("fixture_start") or "9999",
            row.get("date") or "9999",
        )
    )

    return result


async def add_future_games_to_cards(
    cards: List[dict],
    max_concurrent: int = 3,
) -> List[dict]:
    unique_players = {
        card.get("player_slug")
        for card in cards
        if card.get("player_slug")
    }

    semaphore = asyncio.Semaphore(max_concurrent)
    cache: Dict[str, List[dict]] = {}

    async def load_one(slug: str):
        async with semaphore:
            try:
                cache[slug] = await get_player_future_games(slug)
            except Exception as exc:
                print(f"[Zukünftige Spiele] {slug}: {exc}")
                cache[slug] = []

            await asyncio.sleep(0.04)

    await asyncio.gather(
        *(load_one(slug) for slug in unique_players)
    )

    enriched = []

    for card in cards:
        item = dict(card)
        item["future_games"] = cache.get(
            card.get("player_slug"),
            [],
        )
        enriched.append(item)

    return enriched


def get_available_game_weeks(cards: List[dict]) -> List[dict]:
    """
    Sammelt alle unterschiedlichen zukünftigen SO5-Fixtures aus den
    Karten des Nutzers. Nur GameWeeks, in denen mindestens ein eigener
    Spieler ein Spiel hat, erscheinen.
    """
    fixtures: Dict[str, dict] = {}

    for card in cards:
        for game in card.get("future_games") or []:
            slug = game.get("fixture_slug")
            start = game.get("fixture_start")

            if not slug or not start:
                continue

            if slug not in fixtures:
                fixtures[slug] = {
                    "slug": slug,
                    "game_week": game.get("game_week"),
                    "short_name": game.get("fixture_short_name"),
                    "long_name": game.get("fixture_long_name"),
                    "start_date": start,
                    "end_date": game.get("fixture_end"),
                    "player_count": 0,
                }

            fixtures[slug]["player_count"] += 1

    result = list(fixtures.values())
    result.sort(
        key=lambda row: row.get("start_date") or "9999"
    )
    return result


def _parse_sorare_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None


def select_date_range(
    cards: List[dict],
    start_date: str,
    end_date: str,
) -> Tuple[List[dict], List[dict]]:
    """
    Wählt alle Spieler, die mindestens ein SO5-eligible Spiel im
    gewünschten Zeitraum haben.

    start_date/end_date müssen YYYY-MM-DD sein.

    Zeitraum:
      Starttag 00:00 UTC
      Endtag   23:59:59 UTC

    Hat ein Spieler mehrere Spiele im Zeitraum, wird für die aktuelle
    Bewertung das zeitlich erste Spiel verwendet. Alle gefundenen Spiele
    bleiben zusätzlich unter games_in_range gespeichert.
    """
    try:
        start_dt = datetime.strptime(
            start_date,
            "%Y-%m-%d",
        ).replace(tzinfo=timezone.utc)

        end_dt = datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).replace(
            hour=23,
            minute=59,
            second=59,
            tzinfo=timezone.utc,
        )
    except ValueError:
        raise ValueError(
            "Datum bitte im Format YYYY-MM-DD eingeben, "
            "z. B. 2026-09-04."
        )

    if end_dt < start_dt:
        raise ValueError(
            "Das Bis-Datum darf nicht vor dem Von-Datum liegen."
        )

    filtered = []
    fixtures: Dict[str, dict] = {}

    for card in cards:
        matching_games = []

        for game in card.get("future_games") or []:
            game_dt = _parse_sorare_datetime(game.get("date"))
            if game_dt is None:
                continue

            if start_dt <= game_dt <= end_dt:
                matching_games.append(game)

                fixture_slug = game.get("fixture_slug")
                if fixture_slug and fixture_slug not in fixtures:
                    fixtures[fixture_slug] = {
                        "slug": fixture_slug,
                        "game_week": game.get("game_week"),
                        "short_name": game.get("fixture_short_name"),
                        "long_name": game.get("fixture_long_name"),
                        "start_date": game.get("fixture_start"),
                        "end_date": game.get("fixture_end"),
                    }

        if not matching_games:
            continue

        matching_games.sort(
            key=lambda game: game.get("date") or "9999"
        )

        item = dict(card)
        item["games_in_range"] = matching_games
        item["next_game"] = matching_games[0]
        filtered.append(item)

    fixture_list = list(fixtures.values())
    fixture_list.sort(
        key=lambda row: row.get("start_date") or "9999"
    )

    return filtered, fixture_list


def _match_aliases(
    competition_name: Optional[str],
    competition_slug: Optional[str],
    aliases: List[Tuple[str, str]],
) -> Optional[str]:
    haystack = (
        normalize_text(competition_name)
        + " "
        + normalize_text(competition_slug)
    )

    for needle, label in aliases:
        if normalize_text(needle) in haystack:
            return label

    return None


def _match_aliases_exact(
    competition_name: Optional[str],
    competition_slug: Optional[str],
    aliases: List[Tuple[str, str]],
) -> Optional[str]:
    """
    Strikter Match für einzelne Liga-Auswahlen.

    WICHTIG:
    Hier gibt es KEIN Teilstring-Matching mehr.
    Dadurch kann z.B. "Bundesliga" NICHT mehr versehentlich
    "2. Bundesliga" treffen.
    """
    normalized_name = normalize_text(competition_name)
    normalized_slug = normalize_text(competition_slug)

    for needle, label in aliases:
        candidates = {
            normalize_text(needle),
            normalize_text(label),
        }

        if normalized_name in candidates:
            return label

        if normalized_slug in candidates:
            return label

    return None

def card_is_eligible_for_competition(
    card: dict,
    competition_key: str,
) -> bool:
    game = card.get("next_game") or {}

    # Für die Wettbewerbsberechtigung ist die nationale Liga des Vereins
    # entscheidend, nicht der Wettbewerb des konkreten Spiels.
    # Beispiel: Ein 2.-Bundesliga-Spieler kann in derselben Sorare-GW
    # im DFB-Pokal/Europa/etc. spielen; er bleibt trotzdem ein
    # 2.-Bundesliga-/Contender-Spieler.
    domestic_name = game.get("domestic_league_name")
    domestic_slug = game.get("domestic_league_slug")

    match_name = game.get("competition_name")
    match_slug = game.get("competition_slug")

    name = domestic_name or match_name
    slug = domestic_slug or match_slug

    # Es muss wirklich ein Sorare-eligible Spiel in der GW geben.
    if not game.get("fixture_slug"):
        return False

    if competition_key == "contender":
        normalized_slug = str(slug or "").lower()

        # IN-SEASON CONTENDER:
        # Nur die vier echten Contender-In-Season-Ligen:
        # 2. Bundesliga, Austrian Bundesliga, HNL und Ligue 2.
        #
        # WICHTIG:
        # MLS, Champions League, Premier League usw. werden hier selbst dann
        # ausgeschlossen, wenn die Karte Saison 2026 und inSeasonEligible ist.
        inseason_label = _match_aliases(
            name,
            slug,
            CONTENDER_INSEASON_ALIASES,
        )

        is_contender_inseason_competition = (
            normalized_slug in CONTENDER_INSEASON_SLUGS
            or inseason_label is not None
        )

        if (
            card.get("current_season_card")
            and card.get("api_in_season_eligible")
            and is_contender_inseason_competition
        ):
            card["in_season"] = True
            card["classic"] = False
            card["contender_inseason_league"] = (
                inseason_label
                or name
                or slug
            )
            return True

        # CLASSIC CONTENDER:
        # Ältere Karten dürfen ausschließlich aus dem von dir festgelegten
        # erweiterten Classic-Ligenpool kommen.
        #
        # Eine aktuelle 2026-Karte aus MLS/UCL soll NICHT als Classic
        # "umetikettiert" werden, nur weil sie In-Season für Contender
        # nicht zulässig ist.
        if not card.get("current_season_card"):
            classic_label = _match_aliases(
                name,
                slug,
                CONTENDER_CLASSIC_ALIASES,
            )

            if classic_label is not None:
                card["in_season"] = False
                card["classic"] = True
                card["contender_classic_league"] = classic_label
                return True

        return False

    # EINZELNE LIGA:
    # Ab hier gilt ein harter, exakter Liga-Filter.
    # Kein Teilstring-Matching mehr, damit sich Ligen nicht gegenseitig
    # "fangen" können (z.B. Bundesliga vs. 2. Bundesliga).
    aliases = DEDICATED_ALIASES.get(competition_key, [])

    if not aliases:
        return False

    return _match_aliases_exact(
        name,
        slug,
        aliases,
    ) is not None



def summarize_card_pool(cards: List[dict]) -> dict:
    competitions = Counter()
    domestic_leagues = Counter()
    seasons = Counter()

    for card in cards:
        game = card.get("next_game") or {}

        competition_name = (
            game.get("competition_name")
            or game.get("competition_slug")
            or "Unbekannt"
        )
        competitions[competition_name] += 1

        domestic_name = (
            game.get("domestic_league_name")
            or game.get("domestic_league_slug")
            or "Unbekannt"
        )
        domestic_leagues[domestic_name] += 1

        seasons[card.get("season_year")] += 1

    return {
        "competitions": competitions,
        "domestic_leagues": domestic_leagues,
        "seasons": seasons,
        "inseason": sum(1 for card in cards if card.get("in_season")),
        "classic": sum(1 for card in cards if card.get("classic")),
        "api_inseason_eligible": sum(
            1 for card in cards if card.get("api_in_season_eligible")
        ),
        "current_season": sum(
            1 for card in cards if card.get("current_season_card")
        ),
    }



def contender_inseason_diagnostics(cards: List[dict]) -> dict:
    """
    Detaillierte Diagnose für Contender:
    - alle Saison-2026-Karten in der gewählten Sorare-GW
    - nationale Liga
    - konkreter Spielwettbewerb
    - Sorare inSeasonEligible
    - ob die Karte als Contender In-Season akzeptiert wird
    """
    rows = []

    for card in cards:
        if card.get("season_year") != CURRENT_SEASON_YEAR:
            continue

        game = card.get("next_game") or {}

        domestic_name = (
            game.get("domestic_league_name")
            or game.get("domestic_league_slug")
            or "Unbekannt"
        )
        domestic_slug = game.get("domestic_league_slug")

        match_name = (
            game.get("competition_name")
            or game.get("competition_slug")
            or "Unbekannt"
        )

        inseason_label = _match_aliases(
            domestic_name,
            domestic_slug,
            CONTENDER_INSEASON_ALIASES,
        )

        normalized_slug = str(domestic_slug or "").lower()

        is_contender_league = (
            normalized_slug in CONTENDER_INSEASON_SLUGS
            or inseason_label is not None
        )

        sorare_eligible = bool(card.get("api_in_season_eligible"))

        accepted = (
            sorare_eligible
            and is_contender_league
        )

        rows.append({
            "player_name": card.get("player_name") or "Unbekannt",
            "player_slug": card.get("player_slug"),
            "club_name": card.get("club_name") or "Unbekannt",
            "domestic_league_name": domestic_name,
            "domestic_league_slug": domestic_slug,
            "match_competition": match_name,
            "api_in_season_eligible": sorare_eligible,
            "accepted": accepted,
            "reason": (
                "OK"
                if accepted
                else (
                    "Sorare inSeasonEligible = false"
                    if not sorare_eligible
                    else "Nationale Liga ist nicht Contender In-Season"
                )
            ),
        })

    rows.sort(
        key=lambda row: (
            0 if row["accepted"] else 1,
            normalize_text(row["domestic_league_name"]),
            normalize_text(row["club_name"]),
            normalize_text(row["player_name"]),
        )
    )

    return {
        "rows": rows,
        "accepted": [row for row in rows if row["accepted"]],
        "rejected": [row for row in rows if not row["accepted"]],
    }


def filter_competition_cards(
    cards: List[dict],
    competition_key: str,
) -> List[dict]:
    filtered = [
        card
        for card in cards
        if card_is_eligible_for_competition(card, competition_key)
    ]

    print(
        f"[Liga-Filter] Auswahl={competition_key} | "
        f"{len(filtered)}/{len(cards)} Karten zugelassen"
    )

    # Zusätzliche Diagnose: zeigt exakt, welche Domestic-League-Slugs
    # nach dem Filter tatsächlich übrig sind.
    remaining_leagues = Counter(
        (
            (card.get("next_game") or {}).get("domestic_league_slug")
            or (card.get("next_game") or {}).get("domestic_league_name")
            or "Unbekannt"
        )
        for card in filtered
    )

    for league, count in remaining_leagues.most_common():
        print(f"[Liga-Filter]   {league}: {count}")

    return filtered


async def get_player_start_probability(player_slug: str) -> Optional[dict]:
    data = await sorare_request(
        STARTER_ODDS_QUERY,
        {"playerSlug": player_slug},
    )

    players = data.get("players") or []
    if not players:
        return None

    player = players[0] or {}
    odds = player.get("nextClassicFixturePlayingStatusOdds")
    if not odds:
        return None

    starter = odds.get("starterOddsBasisPoints")
    if starter is None:
        return None

    return {
        "starter_probability": round(float(starter) / 100.0, 1),
        "starter_reliability": odds.get("reliability"),
        "starter_source": "SORARE",
    }


async def add_start_probabilities(
    cards: List[dict],
    max_concurrent: int = 3,
) -> List[dict]:
    unique_players = {
        card.get("player_slug")
        for card in cards
        if card.get("player_slug")
    }

    semaphore = asyncio.Semaphore(max_concurrent)
    cache: Dict[str, Optional[dict]] = {}

    async def load_one(slug: str):
        async with semaphore:
            try:
                cache[slug] = await get_player_start_probability(slug)
            except Exception as exc:
                print(f"[Startelf] {slug}: {exc}")
                cache[slug] = None
            await asyncio.sleep(0.04)

    await asyncio.gather(*(load_one(slug) for slug in unique_players))

    result = []
    for card in cards:
        item = dict(card)
        odds = cache.get(card.get("player_slug"))
        item["starter_probability"] = (
            odds.get("starter_probability") if odds else None
        )
        item["starter_reliability"] = (
            odds.get("starter_reliability") if odds else None
        )
        item["starter_source"] = "SORARE" if odds else None
        result.append(item)

    return result


async def get_competition_recent_games(
    competition_slug: str,
    max_pages: int = 2,
) -> List[dict]:
    after = None
    games = []

    for _ in range(max_pages):
        data = await sorare_request(
            COMPETITION_RECENT_GAMES_QUERY,
            {
                "competitionSlug": competition_slug,
                "after": after,
            },
        )

        competition = (
            (data.get("football") or {}).get("competition")
        )
        if not competition:
            break

        connection = competition.get("pastGames") or {}
        games.extend(connection.get("nodes") or [])

        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break

        after = page_info.get("endCursor")
        if not after:
            break

    games.sort(
        key=lambda game: game.get("date") or "",
        reverse=True,
    )
    return games


def _team_goals_for_against(game: dict, team_slug: str):
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}

    if home.get("slug") == team_slug:
        return game.get("homeScore"), game.get("awayScore")
    if away.get("slug") == team_slug:
        return game.get("awayScore"), game.get("homeScore")
    return None, None


def build_team_form(
    games: List[dict],
    team_slug: str,
    last_games: int = 8,
) -> Optional[dict]:
    rows = []

    for game in games:
        gf, ga = _team_goals_for_against(game, team_slug)
        if gf is None or ga is None:
            continue

        rows.append((int(gf), int(ga)))
        if len(rows) >= last_games:
            break

    if not rows:
        return None

    return {
        "avg_for": sum(x[0] for x in rows) / len(rows),
        "avg_against": sum(x[1] for x in rows) / len(rows),
        "clean_sheet_rate": (
            sum(1 for x in rows if x[1] == 0) / len(rows)
        ),
    }


def calculate_clean_sheet_probability(
    team_form: Optional[dict],
    opponent_form: Optional[dict],
    home_away: Optional[str],
) -> Optional[int]:
    if not team_form or not opponent_form:
        return None

    cs_rate = float(team_form["clean_sheet_rate"])
    ga = float(team_form["avg_against"])
    opponent_gf = float(opponent_form["avg_for"])

    defense = max(0.0, min(1.0, 1.0 - ga / 2.5))
    weak_attack = max(
        0.0,
        min(1.0, 1.0 - opponent_gf / 2.5),
    )

    p = cs_rate * 0.50 + defense * 0.25 + weak_attack * 0.25

    if home_away == "H":
        p += 0.04
    elif home_away == "A":
        p -= 0.04

    return round(max(0.10, min(0.80, p)) * 100)


def calculate_attacking_matchup_score(
    team_form: Optional[dict],
    opponent_form: Optional[dict],
    home_away: Optional[str],
) -> Optional[int]:
    """
    Matchup-Wert für MID/ST aus echten letzten Ligaspielen.

    Berücksichtigt:
    - wie viele Tore der eigene Verein zuletzt erzielt
    - wie viele Tore der Gegner zuletzt kassiert
    - wie häufig der Gegner zuletzt ohne Gegentor blieb
    - Heim/Auswärts

    50 = ungefähr neutral, höher = attraktiveres offensives Matchup.
    """
    if not team_form or not opponent_form:
        return None

    team_gf = float(team_form["avg_for"])
    opponent_ga = float(opponent_form["avg_against"])
    opponent_cs = float(opponent_form["clean_sheet_rate"])

    attack_form = max(
        0.0,
        min(1.0, team_gf / 2.5),
    )
    weak_defense = max(
        0.0,
        min(1.0, opponent_ga / 2.5),
    )
    low_cs_rate = max(
        0.0,
        min(1.0, 1.0 - opponent_cs),
    )

    score = (
        attack_form * 0.35
        + weak_defense * 0.45
        + low_cs_rate * 0.20
    )

    if home_away == "H":
        score += 0.05
    elif home_away == "A":
        score -= 0.05

    return round(max(0.10, min(0.90, score)) * 100)


async def add_clean_sheet_probabilities(
    cards: List[dict],
    max_concurrent: int = 2,
) -> List[dict]:
    competition_slugs = {
        (card.get("next_game") or {}).get("competition_slug")
        for card in cards
        if (card.get("next_game") or {}).get("competition_slug")
    }

    semaphore = asyncio.Semaphore(max_concurrent)
    games_cache: Dict[str, List[dict]] = {}

    async def load_one(slug: str):
        async with semaphore:
            try:
                games_cache[slug] = await get_competition_recent_games(slug)
                print(
                    f"[Clean Sheet] {slug}: "
                    f"{len(games_cache[slug])} Spiele"
                )
            except Exception as exc:
                print(f"[Clean Sheet] {slug}: {exc}")
                games_cache[slug] = []
            await asyncio.sleep(0.05)

    await asyncio.gather(*(load_one(slug) for slug in competition_slugs))

    form_cache: Dict[Tuple[str, str], Optional[dict]] = {}

    def form(comp_slug: str, team_slug: str):
        key = (comp_slug, team_slug)
        if key not in form_cache:
            form_cache[key] = build_team_form(
                games_cache.get(comp_slug, []),
                team_slug,
            )
        return form_cache[key]

    result = []

    for card in cards:
        item = dict(card)
        game = card.get("next_game") or {}
        comp = game.get("competition_slug")
        team = game.get("team_slug")
        opponent = game.get("opponent_slug")

        probability = None
        attacking_matchup = None

        if comp and team and opponent:
            team_form = form(comp, team)
            opponent_form = form(comp, opponent)

            probability = calculate_clean_sheet_probability(
                team_form,
                opponent_form,
                game.get("home_away"),
            )

            if card.get("position") in ("MID", "ST"):
                attacking_matchup = calculate_attacking_matchup_score(
                    team_form,
                    opponent_form,
                    game.get("home_away"),
                )

        item["clean_sheet_probability"] = probability
        item["attacking_matchup_score"] = attacking_matchup
        result.append(item)

    return result


def _weighted_rating(components: List[Tuple[Optional[float], float]]) -> float:
    used = [
        (value, weight)
        for value, weight in components
        if value is not None
    ]

    if not used:
        return 0.0

    total_weight = sum(weight for _, weight in used)
    return sum(value * weight for value, weight in used) / total_weight



async def get_player_set_piece_profile(
    player_slug: str,
) -> Optional[dict]:
    """
    Ermittelt ausschließlich Elfmeterschüsse und Ecken aus echten
    historischen Sorare/Opta-Spielstatistiken.

    Spieler ohne ausgeführten Elfmeter UND ohne ausgeführte Ecke
    bekommen kein Standard-Profil.
    """
    data = await sorare_request(
        PLAYER_SET_PIECE_QUERY,
        {"playerSlug": player_slug},
    )

    player = data.get("anyPlayer") or {}
    connection = player.get("allPlayerGameScores") or {}
    nodes = connection.get("nodes") or []

    appearances = 0
    penalties = 0
    corners = 0

    for node in nodes:
        stats = (node or {}).get("anyPlayerGameStats") or {}

        mins = stats.get("minsPlayed")
        if mins is not None and float(mins or 0) > 0:
            appearances += 1

        penalties += int(stats.get("penaltyTaken") or 0)
        corners += int(stats.get("cornerTaken") or 0)

    # Ganz wichtig:
    # Nur Spieler, die tatsächlich mindestens einen Elfmeter ODER
    # mindestens eine Ecke ausgeführt haben, bekommen ein Profil.
    if penalties == 0 and corners < 10:
        return None

    # Penalties stärker gewichten als Ecken.
    # Nur diese beiden Kategorien beeinflussen das Rating.
    score = min(
        100.0,
        penalties * 30.0
        + (corners * 4.0 if corners >= 10 else 0.0),
    )

    return {
        "appearances": appearances,
        "penalties": penalties,
        "corners": corners,
        "set_piece_score": round(score, 1),
        "source": "SORARE/OPTA HISTORIE",
    }


async def add_set_piece_profiles(
    cards: List[dict],
    max_concurrent: int = 3,
) -> List[dict]:
    unique_players = {
        card.get("player_slug")
        for card in cards
        if card.get("player_slug")
        and card.get("position") in ("MID", "ST")
    }

    semaphore = asyncio.Semaphore(max_concurrent)
    cache: Dict[str, Optional[dict]] = {}

    async def load_one(slug: str):
        async with semaphore:
            try:
                cache[slug] = await get_player_set_piece_profile(slug)
            except Exception as exc:
                # Standards sind ein Zusatzsignal. Wenn Sorare für einen
                # Spieler keine passenden Daten liefert, läuft der Builder
                # ohne erfundene Ersatzwerte weiter.
                print(f"[Standards] {slug}: {exc}")
                cache[slug] = None
            await asyncio.sleep(0.04)

    await asyncio.gather(*(load_one(slug) for slug in unique_players))

    result = []
    for card in cards:
        item = dict(card)
        profile = cache.get(card.get("player_slug"))

        item["set_piece_profile"] = profile
        item["set_piece_score"] = (
            profile.get("set_piece_score")
            if profile
            else None
        )
        result.append(item)

    return result

def calculate_card_rating(card: dict) -> float:
    l40_score = max(
        0.0,
        min(100.0, (card.get("l40", 0.0) / 80.0) * 100),
    )
    starter = card.get("starter_probability")
    cs = card.get("clean_sheet_probability")
    set_piece_score = card.get("set_piece_score")
    attacking_matchup = card.get("attacking_matchup_score")

    game = card.get("next_game") or {}
    home_score = 60.0 if game.get("home_away") == "H" else 45.0

    position = card.get("position")

    if position == "TW":
        rating = _weighted_rating([
            (cs, 0.35),
            (starter, 0.30),
            (l40_score, 0.30),
            (home_score, 0.05),
        ])
    elif position == "VER":
        rating = _weighted_rating([
            (cs, 0.30),
            (starter, 0.25),
            (l40_score, 0.35),
            (home_score, 0.10),
        ])
    else:
        # Elfmeter und Ecken sind jetzt ein Zusatzsignal für MID/ST.
        # Fehlen Standarddaten oder Sorare-Startelf-%, renormalisiert
        # _weighted_rating automatisch die vorhandenen Komponenten.
        rating = _weighted_rating([
            (starter, 0.20),
            (l40_score, 0.45),
            (set_piece_score, 0.15),
            (attacking_matchup, 0.15),
            (home_score, 0.05),
        ])

    return round(rating, 1)



def estimate_player_base_points(card: dict) -> float:
    """
    Ungefähre Sorare-Basispunkte für das kommende Spiel.

    Ausgangspunkt ist der echte L40 des Spielers.
    Danach werden nur bereits vorhandene Signale leicht eingerechnet:
    - offizielle Sorare-Startelfwahrscheinlichkeit
    - Clean-Sheet-Chance bei TW/VER
    - Offensiv-Matchup bei MID/ST
    - Elfmeter/Ecken bei MID/ST
    - Heim/Auswärts

    Das ist bewusst eine PROGNOSE und kein garantierter Score.
    """
    base = float(card.get("l40") or 0.0)

    starter = card.get("starter_probability")
    if starter is not None:
        starter = float(starter)
        # 60% liegt etwas unter neutral, 100% nahezu ohne Abschlag.
        starter_factor = 0.82 + (starter / 100.0) * 0.18
        base *= starter_factor

    position = card.get("position")
    game = card.get("next_game") or {}

    if position in ("TW", "VER"):
        cs = card.get("clean_sheet_probability")
        if cs is not None:
            # 35% ungefähr neutral.
            base += (float(cs) - 35.0) * 0.18

    if position in ("MID", "ST"):
        matchup = card.get("attacking_matchup_score")
        if matchup is not None:
            # 50/100 ungefähr neutral.
            base += (float(matchup) - 50.0) * 0.12

        set_piece_score = card.get("set_piece_score")
        if set_piece_score is not None:
            # Standards sind ein Zusatzsignal, aber kein dominanter Faktor.
            base += (float(set_piece_score) / 100.0) * 4.0

    if game.get("home_away") == "H":
        base += 1.0
    elif game.get("home_away") == "A":
        base -= 1.0

    return round(max(0.0, min(100.0, base)), 1)


def add_projected_points(cards: List[dict]) -> List[dict]:
    """
    Ergänzt:
    - projected_base_points: geschätzter Spieler-Score vor Kartenboni
    - projected_card_points: geschätzter Karten-Score inkl.
      In-Season + XP + Sammlungsbonus
    """
    result = []

    for card in cards:
        item = dict(card)

        base_points = estimate_player_base_points(item)

        xp_bonus = float(item.get("xp_bonus_pct") or 0.0)
        collection_bonus = float(
            item.get("collection_bonus_pct") or 0.0
        )

        # Für In-Season gilt 5%. Classic bekommt keinen Season-Bonus.
        inseason_bonus = 5.0 if item.get("in_season") else 0.0

        total_card_bonus = (
            inseason_bonus
            + xp_bonus
            + collection_bonus
        )

        projected_card_points = (
            base_points * (1.0 + total_card_bonus / 100.0)
        )

        item["inseason_bonus_pct"] = round(inseason_bonus, 2)
        item["total_card_bonus_pct"] = round(total_card_bonus, 2)
        item["projected_base_points"] = round(base_points, 1)
        item["projected_card_points"] = round(
            projected_card_points,
            1,
        )

        result.append(item)

    return result

def add_ratings(cards: List[dict]) -> List[dict]:
    result = []
    for card in cards:
        item = dict(card)
        item["rating"] = calculate_card_rating(item)
        result.append(item)
    return result


def _best_card_for_player(cards: List[dict]) -> List[dict]:
    grouped = defaultdict(list)
    for card in cards:
        grouped[card.get("player_slug")].append(card)

    result = []

    for player_cards in grouped.values():
        # Bei gleicher Leistung In-Season bevorzugen, damit der Classic-Slot
        # für einen echten Mehrwert frei bleibt.
        player_cards.sort(
            key=lambda c: (
                c.get("rating", 0),
                1 if c.get("in_season") else 0,
                c.get("season_year") or 0,
            ),
            reverse=True,
        )
        result.extend(player_cards)

    return result


def _lineup_valid(lineup: List[dict]) -> bool:
    if len(lineup) != 5:
        return False

    players = [card.get("player_slug") for card in lineup]
    if len(set(players)) != 5:
        return False

    if sum(1 for card in lineup if card.get("classic")) > 1:
        return False

    if sum(1 for card in lineup if card.get("in_season")) < 4:
        return False

    positions = Counter(card.get("position") for card in lineup)

    if positions["TW"] != 1:
        return False
    if positions["VER"] < 1:
        return False
    if positions["MID"] < 1:
        return False
    if positions["ST"] < 1:
        return False

    return True


def _stack_profile(
    target_points: int,
    strategy_mode: str = "balanced",
) -> dict:
    if target_points <= 340:
        profile = {
            "pick_bonus": 24.0,
            "stack_bonus": {1: 0, 2: 10, 3: 28, 4: 58, 5: 95},
            "gk_def_bonus": 24.0,
            "quality_floor": 22.0,
        }
    elif target_points <= 380:
        profile = {
            "pick_bonus": 15.0,
            "stack_bonus": {1: 0, 2: 8, 3: 20, 4: 38, 5: 58},
            "gk_def_bonus": 18.0,
            "quality_floor": 16.0,
        }
    elif target_points <= 420:
        profile = {
            "pick_bonus": 7.0,
            "stack_bonus": {1: 0, 2: 5, 3: 12, 4: 22, 5: 30},
            "gk_def_bonus": 11.0,
            "quality_floor": 10.0,
        }
    else:
        profile = {
            "pick_bonus": 1.5,
            "stack_bonus": {1: 0, 2: 2, 3: 4, 4: 7, 5: 10},
            "gk_def_bonus": 5.0,
            "quality_floor": 4.0,
        }

    # Safe: mehr Stack + Defensive Korrelation, weniger Bereitschaft
    # schwächere Einzelspieler außerhalb einer stabilen Struktur zu nehmen.
    if strategy_mode == "safe":
        profile["pick_bonus"] *= 1.20
        profile["gk_def_bonus"] *= 1.25
        profile["stack_bonus"] = {
            size: bonus * 1.20
            for size, bonus in profile["stack_bonus"].items()
        }

    # Risky: weniger Stack-Zwang, mehr Einzelqualität/Upside.
    elif strategy_mode == "risky":
        profile["pick_bonus"] *= 0.55
        profile["gk_def_bonus"] *= 0.65
        profile["stack_bonus"] = {
            size: bonus * 0.55
            for size, bonus in profile["stack_bonus"].items()
        }
        profile["quality_floor"] *= 0.60

    return profile


def _strategy_card_bonus(
    card: dict,
    strategy_mode: str,
) -> float:
    """
    Zusatzsignal für die Teamwahl.
    Das normale Karten-Rating bleibt unverändert und transparent.
    """
    if strategy_mode == "balanced":
        return 0.0

    starter = card.get("starter_probability")
    cs = card.get("clean_sheet_probability")
    l40 = float(card.get("l40") or 0.0)
    position = card.get("position")
    profile = card.get("set_piece_profile") or {}

    if strategy_mode == "safe":
        bonus = 0.0

        # Offizielle Sorare-Startelfprognose ist im Safe-Modus besonders wichtig.
        if starter is not None:
            bonus += (float(starter) - 50.0) * 0.12

        # TW/VER mit hoher Clean-Sheet-Chance werden zusätzlich belohnt.
        if position in ("TW", "VER") and cs is not None:
            bonus += (float(cs) - 35.0) * 0.10

        return bonus

    if strategy_mode == "risky":
        # Risky sucht mehr Upside: starkes L40 und Standards bei MID/ST.
        bonus = max(0.0, l40 - 55.0) * 0.18

        if position in ("MID", "ST"):
            penalties = int(profile.get("penalties") or 0)
            corners = int(profile.get("corners") or 0)

            if penalties > 0:
                bonus += min(8.0, penalties * 2.5)

            if corners >= 10:
                bonus += min(6.0, (corners - 9) * 0.20)

        return bonus

    return 0.0


def _pick_best(
    pool: List[dict],
    position: str,
    used_players: set,
    classic_used: int,
    preferred_club: Optional[str] = None,
    stack_weight: float = 0.0,
    lineup: Optional[List[dict]] = None,
    target_points: int = 380,
    strategy_mode: str = "balanced",
    kickoff_cluster: bool = False,
) -> Optional[dict]:
    candidates = []
    profile = _stack_profile(target_points, strategy_mode)
    lineup = lineup or []

    position_pool = []

    for card in pool:
        if card.get("position") != position:
            continue
        if card.get("player_slug") in used_players:
            continue
        if card.get("classic") and classic_used >= 1:
            continue

        # Für Streak 1-3 ist das jetzt eine HARTE Regel:
        # Zwischen dem frühesten und spätesten Anstoß im Team dürfen
        # maximal 6 Stunden (= 360 Minuten) liegen.
        if kickoff_cluster and lineup:
            spread = _kickoff_spread_minutes(lineup + [card])
            if spread is not None and spread > 360:
                continue

        position_pool.append(card)

    if not position_pool:
        return None

    best_raw = max(card.get("rating", 0) for card in position_pool)

    for card in position_pool:
        rating = card.get("rating", 0)

        # Ein Stack-Spieler darf nicht beliebig schwach sein.
        # Bei niedrigen Zielen akzeptieren wir mehr Qualitätsverlust,
        # bei hohen Zielen fast keinen.
        quality_gap = best_raw - rating
        if (
            preferred_club
            and card.get("club_slug") == preferred_club
            and quality_gap > profile["quality_floor"]
        ):
            stack_bonus = 0.0
        else:
            stack_bonus = (
                stack_weight
                if preferred_club
                and card.get("club_slug") == preferred_club
                else 0.0
            )

        # GK + VER desselben Clubs besonders wertvoll:
        # ein Clean Sheet hilft beiden Karten gleichzeitig.
        defensive_pair_bonus = 0.0
        if position in ("TW", "VER"):
            for selected in lineup:
                if (
                    selected.get("club_slug") == card.get("club_slug")
                    and {selected.get("position"), position} == {"TW", "VER"}
                ):
                    defensive_pair_bonus = profile["gk_def_bonus"]
                    break

        inseason_bonus = 1.5 if card.get("in_season") else 0.0

        candidates.append(
            (
                rating
                + stack_bonus
                + defensive_pair_bonus
                + inseason_bonus
                + _strategy_card_bonus(card, strategy_mode),
                card,
            )
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _build_lineup_from_anchor(
    pool: List[dict],
    anchor_club: Optional[str],
    target_points: int,
    strategy_mode: str = "balanced",
    kickoff_cluster: bool = False,
) -> Optional[List[dict]]:
    profile = _stack_profile(target_points, strategy_mode)
    stack_weight = profile["pick_bonus"]

    used_players = set()
    lineup = []
    classic_used = 0

    for position in ["TW", "VER", "MID", "ST"]:
        card = _pick_best(
            pool,
            position,
            used_players,
            classic_used,
            preferred_club=anchor_club,
            stack_weight=stack_weight,
            lineup=lineup,
            target_points=target_points,
            strategy_mode=strategy_mode,
            kickoff_cluster=kickoff_cluster,
        )

        if card is None:
            return None

        lineup.append(card)
        used_players.add(card.get("player_slug"))
        classic_used += int(bool(card.get("classic")))

    extras = []
    for position in ["VER", "MID", "ST"]:
        card = _pick_best(
            pool,
            position,
            used_players,
            classic_used,
            preferred_club=anchor_club,
            stack_weight=stack_weight,
            lineup=lineup,
            target_points=target_points,
            strategy_mode=strategy_mode,
            kickoff_cluster=kickoff_cluster,
        )
        if card:
            extras.append(card)

    if not extras:
        return None

    # Beim Extra nicht nur Einzelrating betrachten, sondern den Wert des
    # vollständigen Lineups. So kann ein sinnvoller 4er/5er Stack gewinnen.
    extra_candidates = []
    for extra in extras:
        candidate_lineup = lineup + [extra]
        if _lineup_valid(candidate_lineup):
            extra_candidates.append(
                (
                    _lineup_value(candidate_lineup, target_points, strategy_mode, kickoff_cluster),
                    extra,
                )
            )

    if not extra_candidates:
        return None

    extra_candidates.sort(key=lambda x: x[0], reverse=True)
    lineup.append(extra_candidates[0][1])

    if not _lineup_valid(lineup):
        return None

    # Zusätzliche Sicherheitsprüfung: Bei Streak 1-3 darf kein
    # vollständiges Team mehr als 6 Stunden Anstoß-Abstand haben.
    if kickoff_cluster:
        spread = _kickoff_spread_minutes(lineup)
        if spread is not None and spread > 360:
            return None

    return lineup



def _card_kickoff_datetime(card: dict) -> Optional[datetime]:
    game = card.get("next_game") or {}
    return _parse_sorare_datetime(game.get("date"))


def _kickoff_spread_minutes(lineup: List[dict]) -> Optional[int]:
    times = [
        _card_kickoff_datetime(card)
        for card in lineup
    ]
    times = [dt for dt in times if dt is not None]

    if len(times) < 2:
        return None

    spread = max(times) - min(times)
    return round(spread.total_seconds() / 60)


def _kickoff_cluster_bonus(
    lineup: List[dict],
    kickoff_cluster: bool,
) -> float:
    """
    Für Streak 1-3 sollen die fünf Spieler möglichst gleichzeitig
    oder zeitlich nah beieinander spielen. Zusätzlich gilt eine harte
    Obergrenze von 6 Stunden zwischen erstem und letztem Anstoß.

    Streak 4+ ignoriert die Anstoßzeiten vollständig.
    """
    if not kickoff_cluster:
        return 0.0

    spread = _kickoff_spread_minutes(lineup)
    if spread is None:
        return 0.0

    # Sehr starke Bevorzugung gleicher/naher Anstoßzeiten.
    if spread <= 15:
        return 70.0
    if spread <= 45:
        return 55.0
    if spread <= 90:
        return 40.0
    if spread <= 120:
        return 28.0
    if spread <= 180:
        return 12.0
    if spread <= 240:
        return -10.0
    if spread <= 300:
        return -25.0
    if spread <= 360:
        return -40.0

    # Eigentlich bereits durch den harten Filter ausgeschlossen.
    # Dieser Rückgabewert ist nur ein zusätzlicher Schutz.
    return -1000000.0

def _lineup_value(
    lineup: List[dict],
    target_points: int,
    strategy_mode: str = "balanced",
    kickoff_cluster: bool = False,
) -> float:
    profile = _stack_profile(target_points, strategy_mode)
    base = sum(
        card.get("rating", 0)
        + _strategy_card_bonus(card, strategy_mode)
        for card in lineup
    )

    clubs = Counter(card.get("club_slug") for card in lineup)
    max_stack = max(clubs.values()) if clubs else 1
    stack_bonus = profile["stack_bonus"].get(max_stack, 0)

    # Expliziter GK+DEF-Bonus pro Club.
    defensive_pair_bonus = 0.0
    for club_slug in clubs:
        positions = {
            card.get("position")
            for card in lineup
            if card.get("club_slug") == club_slug
        }
        if "TW" in positions and "VER" in positions:
            defensive_pair_bonus += profile["gk_def_bonus"]

    kickoff_bonus = _kickoff_cluster_bonus(
        lineup,
        kickoff_cluster,
    )

    return (
        base
        + stack_bonus
        + defensive_pair_bonus
        + kickoff_bonus
    )


def _candidate_signature(lineup: List[dict]) -> tuple:
    return tuple(
        sorted(
            str(card.get("card_slug") or card.get("player_slug"))
            for card in lineup
        )
    )


def _generate_lineup_candidates(
    pool: List[dict],
    target_points: int,
    strategy_mode: str = "balanced",
    kickoff_cluster: bool = False,
) -> List[Tuple[float, List[dict]]]:
    clubs = Counter(
        card.get("club_slug")
        for card in pool
        if card.get("club_slug")
    )

    anchors = [club for club, _ in clubs.most_common(30)]

    # Hohe Ziele testen die reine Qualitätsvariante zuerst.
    if target_points >= 420:
        anchors = [None] + anchors
    else:
        anchors = anchors + [None]

    candidates = []
    seen = set()

    for anchor in anchors:
        lineup = _build_lineup_from_anchor(
            pool,
            anchor,
            target_points,
            strategy_mode,
            kickoff_cluster,
        )
        if not lineup:
            continue

        if kickoff_cluster:
            spread = _kickoff_spread_minutes(lineup)
            if spread is not None and spread > 360:
                continue

        signature = _candidate_signature(lineup)
        if signature in seen:
            continue
        seen.add(signature)

        candidates.append(
            (_lineup_value(lineup, target_points, strategy_mode, kickoff_cluster), lineup)
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates



def _captain_score(
    card: dict,
    strategy_mode: str = "balanced",
) -> float:
    """
    Captain-Auswahl nur für Feldspieler.

    Safe:
      Startelf-Sicherheit + stabiles L40 besonders wichtig.
    Ausgeglichen:
      L40 + Gesamt-Rating + Matchup + Standards.
    Risky:
      mehr Upside durch L40, offensives Matchup und Elfmeter/Ecken.

    Es werden ausschließlich vorhandene Daten verwendet.
    Fehlende Sorare-Prognosen bekommen keinen erfundenen Ersatzwert.
    """
    if card.get("position") == "TW":
        return -1e9

    rating = float(card.get("rating") or 0.0)
    l40 = float(card.get("l40") or 0.0)
    starter = card.get("starter_probability")
    matchup = card.get("attacking_matchup_score")
    profile = card.get("set_piece_profile") or {}

    penalties = int(profile.get("penalties") or 0)
    corners = int(profile.get("corners") or 0)

    # L40 auf ungefähr 0-100 normieren, passend zum Kartenrating.
    l40_score = max(0.0, min(100.0, (l40 / 80.0) * 100.0))

    if strategy_mode == "safe":
        components = [
            (rating, 0.40),
            (l40_score, 0.35),
            (
                float(starter)
                if starter is not None
                else None,
                0.25,
            ),
        ]
        return _weighted_rating(components)

    if strategy_mode == "risky":
        set_piece_upside = None
        if card.get("position") in ("MID", "ST"):
            if penalties > 0 or corners >= 10:
                set_piece_upside = min(
                    100.0,
                    penalties * 30.0
                    + (
                        corners * 4.0
                        if corners >= 10
                        else 0.0
                    ),
                )

        components = [
            (l40_score, 0.40),
            (rating, 0.25),
            (
                float(matchup)
                if matchup is not None
                else None,
                0.20,
            ),
            (set_piece_upside, 0.15),
        ]
        return _weighted_rating(components)

    # Balanced / Ausgeglichen
    set_piece_signal = None
    if card.get("position") in ("MID", "ST"):
        if penalties > 0 or corners >= 10:
            set_piece_signal = min(
                100.0,
                penalties * 30.0
                + (
                    corners * 4.0
                    if corners >= 10
                    else 0.0
                ),
            )

    components = [
        (rating, 0.40),
        (l40_score, 0.35),
        (
            float(matchup)
            if matchup is not None
            else None,
            0.15,
        ),
        (set_piece_signal, 0.10),
    ]
    return _weighted_rating(components)


def _select_captain(
    lineup: List[dict],
    strategy_mode: str = "balanced",
) -> Optional[dict]:
    field_players = [
        card
        for card in lineup
        if card.get("position") != "TW"
    ]

    if not field_players:
        return None

    return max(
        field_players,
        key=lambda card: _captain_score(
            card,
            strategy_mode,
        ),
    )

def build_four_streak_lineups(
    cards: List[dict],
    target_points: int,
    strategy_mode: str = "balanced",
    kickoff_cluster: bool = False,
) -> List[dict]:
    """
    Baut bis zu vier komplette Teams.

    FESTE REGEL:
    - TEAM 1 ist immer das stärkste aktuell mögliche Einzelteam.
    - Für TEAM 1 gibt es KEIN Look-ahead und KEIN Kartensparen.
    - Erst nachdem TEAM 1 feststeht, werden dessen Karten entfernt.
    - TEAM 2-4 dürfen anschließend weiterhin mit Look-ahead geplant werden.
    - dieselbe Karte wird weiterhin nur einmal verwendet.
    """
    full_pool = list(cards)
    teams_raw = []
    used_card_slugs = set()

    for team_number in range(1, 5):
        available_pool = [
            card
            for card in full_pool
            if str(card.get("card_slug") or card.get("player_slug"))
            not in used_card_slugs
        ]

        candidates = _generate_lineup_candidates(
            available_pool,
            target_points,
            strategy_mode,
            kickoff_cluster,
        )

        if not candidates:
            break

        if team_number == 1:
            # WICHTIG:
            # Der erste Kandidat ist nach _lineup_value absteigend sortiert.
            # Team 1 bekommt daher kompromisslos das beste mögliche Team.
            # Keine Rücksicht auf Team 2-4.
            current_value, lineup = candidates[0]

        else:
            # Ab Team 2 darf weiterhin ein kleiner Look-ahead helfen,
            # damit die restlichen Karten sinnvoll genutzt werden.
            best_plan_value = float("-inf")
            best_choice = None

            for current_value, candidate_lineup in candidates[:12]:
                candidate_slugs = {
                    str(card.get("card_slug") or card.get("player_slug"))
                    for card in candidate_lineup
                }

                remaining_after = [
                    card
                    for card in available_pool
                    if str(card.get("card_slug") or card.get("player_slug"))
                    not in candidate_slugs
                ]

                future_candidates = _generate_lineup_candidates(
                    remaining_after,
                    target_points,
                    strategy_mode,
                    kickoff_cluster,
                )

                future_value = (
                    future_candidates[0][0]
                    if future_candidates
                    else 0.0
                )

                plan_value = current_value + future_value * 0.72

                if plan_value > best_plan_value:
                    best_plan_value = plan_value
                    best_choice = (current_value, candidate_lineup)

            if best_choice is None:
                break

            current_value, lineup = best_choice

        clubs_used = Counter(
            card.get("club_name") for card in lineup
        )
        max_stack = max(clubs_used.values()) if clubs_used else 1

        captain = _select_captain(
            lineup,
            strategy_mode,
        )

        defensive_stacks = []
        club_slugs = {
            card.get("club_slug")
            for card in lineup
            if card.get("club_slug")
        }

        for club_slug in club_slugs:
            club_cards = [
                card
                for card in lineup
                if card.get("club_slug") == club_slug
            ]
            positions = {card.get("position") for card in club_cards}

            if "TW" in positions and "VER" in positions:
                club_name = next(
                    (
                        card.get("club_name")
                        for card in club_cards
                        if card.get("club_name")
                    ),
                    club_slug,
                )
                defensive_stacks.append(club_name)

        kickoff_times = [
            _card_kickoff_datetime(card)
            for card in lineup
        ]
        kickoff_times = [
            dt for dt in kickoff_times
            if dt is not None
        ]

        kickoff_spread = _kickoff_spread_minutes(lineup)

        projected_base_total = round(
            sum(
                float(card.get("projected_base_points") or 0.0)
                for card in lineup
            ),
            1,
        )

        projected_bonus_total = round(
            sum(
                float(card.get("projected_card_points") or 0.0)
                for card in lineup
            ),
            1,
        )

        teams_raw.append({
            "number": team_number,
            "cards": lineup,
            "projected_base_total": projected_base_total,
            "projected_total": projected_bonus_total,
            "kickoff_spread_minutes": kickoff_spread,
            "kickoff_first": (
                min(kickoff_times).isoformat()
                if kickoff_times
                else None
            ),
            "kickoff_last": (
                max(kickoff_times).isoformat()
                if kickoff_times
                else None
            ),
            "captain": captain,
            "captain_score": (
                round(_captain_score(captain, strategy_mode), 1)
                if captain
                else None
            ),
            "stack_size": max_stack,
            "stack_club": (
                clubs_used.most_common(1)[0][0]
                if clubs_used
                else "-"
            ),
            "defensive_stacks": defensive_stacks,
            "team_rating": round(
                sum(card.get("rating", 0) for card in lineup) / 5,
                1,
            ),
            "lineup_value": round(current_value, 1),
        })

        # Erst JETZT werden die Karten des fest gewählten Teams gesperrt.
        for card in lineup:
            used_card_slugs.add(
                str(card.get("card_slug") or card.get("player_slug"))
            )

    return teams_raw

