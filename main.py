import os
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from sorare_api import (
    PRO_COMPETITIONS,
    get_cards_for_discord_user,
    add_future_games_to_cards,
    select_date_range,
    filter_competition_cards,
    summarize_card_pool,
    contender_inseason_diagnostics,
    add_start_probabilities,
    add_set_piece_profiles,
    add_clean_sheet_probabilities,
    add_ratings,
    add_projected_points,
    build_four_streak_lineups,
)

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt in der .env")

if not GUILD_ID:
    raise RuntimeError("GUILD_ID fehlt in der .env")

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)

guild_object = discord.Object(id=int(GUILD_ID))


@bot.event
async def on_ready():
    print(f"Bot eingeloggt als: {bot.user}")
    print("Sorare Streak Builder gestartet.")
    print("Version: MLS + harter Startelf-Filter + öffentliche Auswahl")



competition_choices = [
    app_commands.Choice(name=label, value=key)
    for key, label in PRO_COMPETITIONS.items()
]



STREAK_POINT_TARGETS = {
    "bundesliga-de": [320, 360, 380, 420, 440, 470],
    "2-bundesliga": [320, 360, 380, 420, 440, 470],
    "premier-league-gb-eng": [320, 360, 380, 400, 430, 450],
    "laliga-es": [320, 360, 380, 420, 440, 470],
    "ligue-1-fr": [320, 360, 380, 410, 440, 460],
    "ligue-2-fr": [320, 360, 380, 420, 440, 470],
    "mlspa": [340, 380, 400, 420, 460],
    "austrian-bundesliga": [320, 360, 380, 420, 440, 470],
    "1-hnl": [320, 360, 380, 420, 440, 470],
    "primeira-liga-pt": [320, 360, 380, 410, 440, 460],
    "jupiler-pro-league": [320, 360, 380, 410, 440, 460],
    "contender": [320, 360, 380, 420, 440, 470],
}


def get_streak_point_choices(
    competition_key: str,
    selected_value: int | None = None,
):
    values = STREAK_POINT_TARGETS.get(
        competition_key,
        [320, 360, 380, 420, 440, 470],
    )

    return [
        discord.SelectOption(
            label=f"{value} Punkte",
            value=str(value),
            default=(selected_value == value),
        )
        for value in values
    ]


def get_streak_number(
    competition_key: str,
    target_points: int,
) -> int:
    values = STREAK_POINT_TARGETS.get(
        competition_key,
        [320, 360, 380, 420, 440, 470],
    )

    try:
        return values.index(target_points) + 1
    except ValueError:
        return 99


WEEKDAYS_DE = [
    "Mo",
    "Di",
    "Mi",
    "Do",
    "Fr",
    "Sa",
    "So",
]


def build_date_options(
    default_offset: int = 0,
    selected_date: str | None = None,
):
    """
    Discord erlaubt maximal 25 Einträge pro Select-Menü.
    Deshalb zeigen wir heute + die nächsten 20 Tage an.
    """
    today = datetime.now(timezone.utc).date()
    options = []

    for offset in range(21):
        day = today + timedelta(days=offset)
        weekday = WEEKDAYS_DE[day.weekday()]
        label = f"{weekday}, {day.strftime('%d.%m.%Y')}"

        is_default = (
            day.isoformat() == selected_date
            if selected_date is not None
            else offset == default_offset
        )

        options.append(
            discord.SelectOption(
                label=label,
                value=day.isoformat(),
                default=is_default,
            )
        )

    return options


class StartDateSelect(discord.ui.Select):
    def __init__(self, view_ref):
        self.view_ref = view_ref
        super().__init__(
            placeholder="📅 Von-Datum auswählen",
            min_values=1,
            max_values=1,
            options=build_date_options(
                default_offset=0,
                selected_date=view_ref.start_date,
            ),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.start_date = self.values[0]
        await self.view_ref.refresh_message(interaction)


class EndDateSelect(discord.ui.Select):
    def __init__(self, view_ref):
        self.view_ref = view_ref
        super().__init__(
            placeholder="📅 Bis-Datum auswählen",
            min_values=1,
            max_values=1,
            options=build_date_options(
                default_offset=4,
                selected_date=view_ref.end_date,
            ),
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.end_date = self.values[0]
        await self.view_ref.refresh_message(interaction)



class PointTargetSelect(discord.ui.Select):
    def __init__(self, view_ref):
        self.view_ref = view_ref
        super().__init__(
            placeholder="🎯 Streak-Punkteziel auswählen",
            min_values=1,
            max_values=1,
            options=get_streak_point_choices(
                view_ref.competition_key,
                view_ref.target_points,
            ),
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.target_points = int(self.values[0])
        await self.view_ref.refresh_message(interaction)


class StrategySelect(discord.ui.Select):
    def __init__(self, view_ref):
        self.view_ref = view_ref

        labels = {
            "safe": "🛡️ Safe",
            "balanced": "⚖️ Ausgeglichen",
            "risky": "🚀 Risky",
        }

        descriptions = {
            "safe": "Mehr Startelf-Sicherheit, Clean Sheet und Stacking",
            "balanced": "Ausgewogene Mischung aus Sicherheit und Qualität",
            "risky": "Mehr Einzelqualität und offensive Upside",
        }

        options = [
            discord.SelectOption(
                label=labels[value],
                value=value,
                description=descriptions[value],
                default=(view_ref.strategy_mode == value),
            )
            for value in ("safe", "balanced", "risky")
        ]

        super().__init__(
            placeholder="🧠 Strategie auswählen",
            min_values=1,
            max_values=1,
            options=options,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.strategy_mode = self.values[0]
        await self.view_ref.refresh_message(interaction)


class BuildTeamButton(discord.ui.Button):
    def __init__(self, view_ref):
        self.view_ref = view_ref
        super().__init__(
            label="Team bauen",
            style=discord.ButtonStyle.green,
            emoji="🔥",
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.view_ref.target_points is None:
            await interaction.response.send_message(
                "❌ Bitte zuerst dein Streak-Punkteziel auswählen.",
                ephemeral=True,
            )
            return

        start_dt = datetime.strptime(
            self.view_ref.start_date,
            "%Y-%m-%d",
        ).date()

        end_dt = datetime.strptime(
            self.view_ref.end_date,
            "%Y-%m-%d",
        ).date()

        if end_dt < start_dt:
            await interaction.response.send_message(
                "❌ Das Bis-Datum darf nicht vor dem Von-Datum liegen.",
                ephemeral=True,
            )
            return

        for item in self.view_ref.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=None,
            embed=self.view_ref.summary_embed(analysing=True),
            view=self.view_ref,
        )

        await run_streakteam_analysis(
            interaction=interaction,
            competition_key=self.view_ref.competition_key,
            competition_name=self.view_ref.competition_name,
            rarity=self.view_ref.rarity,
            rarity_name=self.view_ref.rarity_name,
            zielpunkte=self.view_ref.target_points,
            strategy_mode=self.view_ref.strategy_mode,
            von=self.view_ref.start_date,
            bis=self.view_ref.end_date,
        )


class DateRangeView(discord.ui.View):
    def __init__(
        self,
        owner_id: int,
        competition_key: str,
        competition_name: str,
        rarity: str,
        rarity_name: str,
    ):
        super().__init__(timeout=300)

        today = datetime.now(timezone.utc).date()

        self.owner_id = owner_id
        self.competition_key = competition_key
        self.competition_name = competition_name
        self.rarity = rarity
        self.rarity_name = rarity_name
        self.target_points = None
        self.strategy_mode = "balanced"

        self.start_date = today.isoformat()
        self.end_date = (today + timedelta(days=4)).isoformat()

        self.add_item(PointTargetSelect(self))
        self.add_item(StartDateSelect(self))
        self.add_item(EndDateSelect(self))
        self.add_item(StrategySelect(self))
        self.add_item(BuildTeamButton(self))

    def summary_text(self):
        start_display = datetime.strptime(
            self.start_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")

        end_display = datetime.strptime(
            self.end_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")

        target_text = (
            f"{self.target_points} Punkte"
            if self.target_points is not None
            else "noch auswählen"
        )

        return (
            "🔥 **Sorare Streak Builder**\n"
            "\n"
            f"🏆 **Wettbewerb:** {self.competition_name}\n"
            f"💎 **Seltenheit:** {self.rarity_name}\n"
            f"🎯 **Ziel:** {target_text}\n"
            f"📅 **Von:** {start_display}\n"
            f"📅 **Bis:** {end_display}\n"
            "\n"
            "👇 **Auswahl unten:**\n"
            "1. 🎯 Streak-Punkteziel\n"
            "2. 📅 Von-Datum\n"
            "3. 📅 Bis-Datum\n"
            "4. 🔥 Team bauen"
        )


    def summary_embed(self, analysing: bool = False):
        start_display = datetime.strptime(
            self.start_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")

        end_display = datetime.strptime(
            self.end_date,
            "%Y-%m-%d",
        ).strftime("%d.%m.%Y")

        target_text = (
            f"{self.target_points} Punkte"
            if self.target_points is not None
            else "noch auswählen"
        )

        embed = discord.Embed(
            title="🔥 Sorare Streak Builder",
            description=(
                "⏳ **Analyse läuft …**"
                if analysing
                else "Wähle unten Punkte und Zeitraum aus."
            ),
        )

        embed.add_field(
            name="🏆 Wettbewerb",
            value=self.competition_name,
            inline=False,
        )
        embed.add_field(
            name="💎 Seltenheit",
            value=self.rarity_name,
            inline=False,
        )
        embed.add_field(
            name="🎯 Ziel",
            value=target_text,
            inline=False,
        )

        strategy_names = {
            "safe": "🛡️ Safe",
            "balanced": "⚖️ Ausgeglichen",
            "risky": "🚀 Risky",
        }
        embed.add_field(
            name="🧠 Strategie",
            value=strategy_names.get(
                self.strategy_mode,
                "⚖️ Ausgeglichen",
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Von",
            value=start_display,
            inline=False,
        )
        embed.add_field(
            name="📅 Bis",
            value=end_display,
            inline=False,
        )

        return embed


    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ Diese Auswahl gehört zu einem anderen Nutzer.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh_message(
        self,
        interaction: discord.Interaction,
    ):
        self.clear_items()
        self.add_item(PointTargetSelect(self))
        self.add_item(StartDateSelect(self))
        self.add_item(EndDateSelect(self))
        self.add_item(StrategySelect(self))
        self.add_item(BuildTeamButton(self))

        await interaction.response.edit_message(
            content=None,
            embed=self.summary_embed(),
            view=self,
        )



@bot.tree.command(
    name="streakteam",
    description="Baut bis zu 4 Streak-Teams aus deinen spielberechtigten Karten.",
    guild=guild_object,
)
@app_commands.describe(
    wettbewerb="Welchen Pro/Hot-Streak-Wettbewerb willst du spielen?",
    seltenheit="Limited oder Rare",
)
@app_commands.choices(
    wettbewerb=competition_choices,
    seltenheit=[
        app_commands.Choice(name="Limited", value="limited"),
        app_commands.Choice(name="Rare", value="rare"),
    ],
)
async def streakteam(
    interaction: discord.Interaction,
    wettbewerb: app_commands.Choice[str],
    seltenheit: app_commands.Choice[str],
):
    competition_key = wettbewerb.value
    competition_name = PRO_COMPETITIONS.get(
        competition_key,
        wettbewerb.name,
    )

    rarity = seltenheit.value
    rarity_name = seltenheit.name

    view = DateRangeView(
        owner_id=interaction.user.id,
        competition_key=competition_key,
        competition_name=competition_name,
        rarity=rarity,
        rarity_name=rarity_name,
    )

    await interaction.response.send_message(
        embed=view.summary_embed(),
        view=view,
        ephemeral=False,
    )


async def run_streakteam_analysis(
    interaction: discord.Interaction,
    competition_key: str,
    competition_name: str,
    rarity: str,
    rarity_name: str,
    zielpunkte: int,
    strategy_mode: str,
    von: str,
    bis: str,
):
    try:
        print()
        print("=" * 72)
        print(
            f"/streakteam | {interaction.user.id} | "
            f"{competition_name} | {rarity_name} | Ziel {zielpunkte} | Strategie {strategy_mode} | {von} bis {bis}"
        )
        print("=" * 72)

        # 1) Alle Karten dieser Seltenheit, ALLE Saisons.
        result = await get_cards_for_discord_user(
            interaction.user.id,
            rarity=rarity,
        )

        if result.get("error") == "DISCORD_USER_NOT_MAPPED":
            await interaction.followup.send(
                "❌ Deine Discord-ID ist noch keinem Sorare-Account zugeordnet."
            )
            return

        cards = result.get("cards") or []
        sorare_slug = result.get("sorare_slug")

        if not cards:
            await interaction.followup.send(
                f"❌ Keine {rarity_name}-Karten gefunden."
            )
            return

        # 2) Mehrere zukünftige Spiele laden, damit der gewünschte
        # Zeitraum per Discord-Auswahl genutzt werden kann.
        cards = await add_future_games_to_cards(cards)

        before_range = len(cards)

        try:
            cards, fixtures_in_range = select_date_range(
                cards,
                start_date=von,
                end_date=bis,
            )
        except ValueError as exc:
            await interaction.followup.send(
                f"❌ {exc}"
            )
            return

        print(
            f"Zeitraum {von} bis {bis}: "
            f"{len(cards)}/{before_range} Karten mit Spiel"
        )

        fixture_gws = sorted(
            {
                fixture.get("game_week")
                for fixture in fixtures_in_range
                if fixture.get("game_week") is not None
            }
        )

        if fixture_gws:
            print(
                "[Zeitraum] Sorare GameWeeks: "
                + ", ".join(f"GW {gw}" for gw in fixture_gws)
            )

        if not cards:
            await interaction.followup.send(
                f"❌ Zwischen **{von}** und **{bis}** hat keiner deiner "
                "Spieler ein SO5-eligible Spiel."
            )
            return

        # 3) Diagnose des GameWeek-Pools vor dem Liga-Filter.
        pool_summary = summarize_card_pool(cards)

        print(
            f"[GW-Pool] Saison 2026: {pool_summary['current_season']} | "
            f"Sorare In-Season eligible: {pool_summary['api_inseason_eligible']} | "
            f"ältere Karten: {pool_summary['classic']}"
        )
        print("[GW-Pool] Nationale Ligen der Vereine:")
        for league, count in pool_summary["domestic_leagues"].most_common():
            print(f"  - {league}: {count}")

        print("[GW-Pool] Tatsächliche Spiele in dieser GW:")
        for competition, count in pool_summary["competitions"].most_common():
            print(f"  - {competition}: {count}")

        print("[GW-Pool] Saisons:")
        for season, count in sorted(
            pool_summary["seasons"].items(),
            key=lambda item: (item[0] is None, item[0]),
        ):
            print(f"  - {season}: {count}")

        if competition_key == "contender":
            diag = contender_inseason_diagnostics(cards)

            print()
            print("=" * 72)
            print(
                f"[CONTENDER 2026 DIAGNOSE] "
                f"{len(diag['rows'])} Saison-2026-Karten im Zeitraum {von} bis {bis}"
            )
            print("=" * 72)

            print(
                f"[CONTENDER AKZEPTIERT] {len(diag['accepted'])}"
            )
            if diag["accepted"]:
                for row in diag["accepted"]:
                    print(
                        f"  ✅ {row['player_name']} | "
                        f"{row['club_name']} | "
                        f"{row['domestic_league_name']} | "
                        f"Sorare eligible={row['api_in_season_eligible']} | "
                        f"Spiel: {row['match_competition']}"
                    )
            else:
                print("  - keine")

            print()
            print(
                f"[CONTENDER ABGELEHNT] {len(diag['rejected'])}"
            )
            if diag["rejected"]:
                for row in diag["rejected"]:
                    print(
                        f"  ❌ {row['player_name']} | "
                        f"{row['club_name']} | "
                        f"{row['domestic_league_name']} | "
                        f"Sorare eligible={row['api_in_season_eligible']} | "
                        f"Grund: {row['reason']} | "
                        f"Spiel: {row['match_competition']}"
                    )
            else:
                print("  - keine")

            print("=" * 72)
            print()

        # 4) Auf ausgewählten Wettbewerb filtern.
        cards = filter_competition_cards(
            cards,
            competition_key,
        )

        filtered_summary = summarize_card_pool(cards)

        print(
            f"[{competition_name}] Nach Berechtigungsfilter: {len(cards)} Karten | "
            f"In-Season: {filtered_summary['inseason']} | "
            f"Classic: {filtered_summary['classic']}"
        )

        print(f"[{competition_name}] Zugelassene nationale Ligen:")
        for league, count in filtered_summary["domestic_leagues"].most_common():
            print(f"  - {league}: {count}")

        print(f"[{competition_name}] Tatsächliche Spiele:")
        for competition, count in filtered_summary["competitions"].most_common():
            print(f"  - {competition}: {count}")

        if not cards:
            await interaction.followup.send(
                f"❌ Keine spielberechtigten {rarity_name}-Karten für "
                f"**{competition_name}** in dieser GameWeek gefunden."
            )
            return

        # 5) Official Sorare Startelf-Prognosen. KEIN eigener Fallback.
        cards = await add_start_probabilities(cards)

        # Harte Startelf-Regel:
        # Wenn Sorare eine offizielle Startelfwahrscheinlichkeit liefert
        # und diese unter 60% liegt, wird der Spieler NICHT berücksichtigt.
        # Fehlt die Sorare-Prognose komplett, erfinden wir weiterhin keinen
        # Wert und schließen den Spieler deshalb nicht automatisch aus.
        before_starter_filter = len(cards)
        cards = [
            card
            for card in cards
            if (
                card.get("starter_probability") is not None
                and float(card.get("starter_probability")) >= 60.0
            )
        ]

        removed_starter = before_starter_filter - len(cards)
        print(
            f"[Startelf-Filter] {removed_starter} Karten entfernt "
            f"(keine Sorare-Prognose oder Startelf < 60%) | {len(cards)} übrig"
        )

        if not cards:
            await interaction.followup.send(
                "❌ Nach dem Startelf-Filter ist keine spielberechtigte "
                "Karte mehr übrig. Es werden nur Spieler berücksichtigt, für die "
                "Sorare eine offizielle Startelfwahrscheinlichkeit von "
                "mindestens 60% liefert."
            )
            return

        # 6) Historische Standards für MID/ST:
        # Nur Elfmeter und Ecken aus Sorare/Opta.
        # Nur Spieler mit tatsächlich ausgeführten Standards bekommen einen Wert.
        cards = await add_set_piece_profiles(cards)

        # 7) Clean Sheet für TW/VER.
        cards = await add_clean_sheet_probabilities(cards)

        # 8) Rating.
        cards = add_ratings(cards)

        # 9) Ungefähre Sorare-Punkte inkl. echter Kartenboni.
        cards = add_projected_points(cards)

        streak_number = get_streak_number(
            competition_key,
            zielpunkte,
        )

        # Für Streak 1-3 sollen die Spieler möglichst gleichzeitig
        # oder nah beieinander spielen. Ab Streak 4 ist die Anstoßzeit
        # für die Team-Auswahl komplett egal.
        kickoff_cluster = streak_number <= 3

        teams = build_four_streak_lineups(
            cards,
            target_points=zielpunkte,
            strategy_mode=strategy_mode,
            kickoff_cluster=kickoff_cluster,
        )

        inseason_count = sum(
            1 for card in cards if card.get("in_season")
        )
        classic_count = sum(
            1 for card in cards if card.get("classic")
        )

        summary = discord.Embed(
            title=f"🔥 {competition_name} – {rarity_name}",
            description=(
                f"**Sorare:** `{sorare_slug}`\n"
                f"📅 **Zeitraum:** **{von} bis {bis}**\n"
                f"🎮 **Sorare GWs im Zeitraum:** "
                f"{', '.join(f'GW {gw}' for gw in fixture_gws) if fixture_gws else '—'}\n"
                f"🎯 **Aktuelles Ziel:** {zielpunkte} Punkte "
                f"(Streak {streak_number})\n"
                f"⏰ **Anstoßzeiten:** "
                f"{'maximal 6 Stunden auseinander' if kickoff_cluster else 'werden ab Streak 4 nicht berücksichtigt'}\n"
                f"✅ **Startelf-Filter:** Sorare-Prognose mindestens 60%\n"
                f"🥇 **Team 1:** immer bestes mögliches Team\n"
                f"🧠 **Strategie:** "
                f"{'🛡️ Safe' if strategy_mode == 'safe' else ('🚀 Risky' if strategy_mode == 'risky' else '⚖️ Ausgeglichen')}\n\n"
                f"✅ Spielberechtigte Karten: **{len(cards)}**\n"
                f"🆕 In-Season: **{inseason_count}**\n"
                f"🕰️ Classic: **{classic_count}**\n"
                f"🧩 Gebaute Teams: **{len(teams)}/4**"
            ),
        )

        if zielpunkte <= 340:
            strategy = (
                "Sehr niedrige Streak: starke Vereins-Stacks werden bevorzugt, "
                "bis hin zu 5 Spielern desselben Vereins."
            )
        elif zielpunkte <= 380:
            strategy = (
                "Niedrige/mittlere Streak: Vereins-Stacks werden deutlich "
                "bevorzugt, aber Qualität bleibt wichtig."
            )
        elif zielpunkte <= 420:
            strategy = (
                "Mittlere/hohe Streak: Mischung aus Stack und Einzelqualität."
            )
        else:
            strategy = (
                "Hohe Streak: maximale Einzelqualität hat Vorrang; "
                "Stacks geben nur noch einen kleinen Bonus."
            )

        summary.add_field(
            name="🧠 Strategie",
            value=strategy,
            inline=False,
        )

        summary.set_footer(
            text=(
                "Max. 1 Classic pro Team, mindestens 4 In-Season. "
                "Eigene Startelf-Prognosen sind deaktiviert."
            )
        )

        await interaction.followup.send(embed=summary)

        if not teams:
            if competition_key == "contender":
                diag = contender_inseason_diagnostics(
                    [
                        card
                        for card in cards
                        if card.get("season_year") == 2026
                    ]
                )

                accepted_names = [
                    row["player_name"]
                    for row in diag["accepted"][:10]
                ]

                accepted_text = (
                    ", ".join(accepted_names)
                    if accepted_names
                    else "keine"
                )

                await interaction.followup.send(
                    "❌ Mit den verfügbaren Karten konnte kein gültiges "
                    "5er-Team gebaut werden.\n\n"
                    f"**Contender In-Season 2026 akzeptiert:** "
                    f"{len(diag['accepted'])}\n"
                    f"**Spieler:** {accepted_text}\n\n"
                    "Im Terminal steht jetzt die vollständige Liste mit "
                    "allen akzeptierten und abgelehnten 2026-Karten."
                )
            else:
                await interaction.followup.send(
                    "❌ Mit den verfügbaren Karten konnte kein gültiges "
                    "5er-Team gebaut werden."
                )
            return

        position_emoji = {
            "TW": "🧤",
            "VER": "🛡️",
            "MID": "⚙️",
            "ST": "⚡",
        }

        for team in teams:
            kickoff_line = ""
            if kickoff_cluster:
                spread = team.get("kickoff_spread_minutes")
                if spread is not None:
                    if spread == 0:
                        kickoff_line = "⏰ Anstoß: **alle gleichzeitig**\n"
                    elif spread < 60:
                        kickoff_line = (
                            f"⏰ Anstoßfenster: **{spread} Min.**\n"
                        )
                    else:
                        hours = spread // 60
                        minutes = spread % 60
                        kickoff_line = (
                            f"⏰ Anstoßfenster: **{hours} Std. "
                            f"{minutes} Min.**\n"
                        )

            embed = discord.Embed(
                title=(
                    f"🔥 TEAM {team['number']} – "
                    f"≈ {team.get('projected_total', 0):.1f} Punkte"
                ),
                description=(
                    f"📈 Basis-Prognose: **{team.get('projected_base_total', 0):.1f}**\n"
                    f"✨ Mit Kartenboni: **{team.get('projected_total', 0):.1f}**\n"
                    f"⭐ Team-Rating: **{team['team_rating']}/100**\n"
                    + kickoff_line
                    + f"🏟️ Stack: **{team['stack_size']}× "
                    f"{team['stack_club']}**\n"
                    + (
                        "🧤🛡️ Defensiv-Stack: **"
                        + ", ".join(team.get("defensive_stacks") or [])
                        + "**\n"
                        if team.get("defensive_stacks")
                        else ""
                    )
                    + f"👑 Captain-Vorschlag: "
                    f"**{team['captain'].get('player_name')}**"
                    + (
                        f" · Captain-Score "
                        f"**{team.get('captain_score')}/100**"
                        if team.get("captain_score") is not None
                        else ""
                    )
                ),
            )

            for index, card in enumerate(team["cards"], start=1):
                position = card.get("position")
                emoji = position_emoji.get(position, "👤")
                game = card.get("next_game") or {}

                if game.get("home_away") == "H":
                    fixture_text = (
                        f"🏠 vs. {game.get('opponent_name') or '?'}"
                    )
                else:
                    fixture_text = (
                        f"✈️ bei {game.get('opponent_name') or '?'}"
                    )

                season_text = (
                    "🆕 In-Season"
                    if card.get("in_season")
                    else f"🕰️ Classic {card.get('season_year')}"
                )

                starter = card.get("starter_probability")
                if starter is None:
                    starter_text = "✅ Startelf: keine Sorare-Prognose"
                else:
                    starter_text = (
                        f"✅ Startelf: {starter:.0f}% · Sorare"
                    )

                cs_text = ""
                if position in ("TW", "VER"):
                    cs = card.get("clean_sheet_probability")
                    if cs is not None:
                        cs_text = f"\n🧤 Clean Sheet: {cs}%"

                matchup_text = ""
                if position in ("MID", "ST"):
                    matchup = card.get("attacking_matchup_score")
                    if matchup is not None:
                        matchup_text = (
                            f"\n⚔️ Offensiv-Matchup: {matchup}/100"
                        )

                set_piece_text = ""
                if position in ("MID", "ST"):
                    profile = card.get("set_piece_profile")
                    if profile:
                        parts = []

                        if profile.get("penalties", 0) > 0:
                            parts.append(
                                f"⚽ Elfmeter: {profile['penalties']}"
                            )

                        if profile.get("corners", 0) >= 10:
                            parts.append(
                                f"🚩 Ecken: {profile['corners']}"
                            )

                        # Nur anzeigen, wenn der Spieler diese Standards
                        # wirklich ausgeführt hat.
                        if parts:
                            set_piece_text = (
                                "\n🎯 "
                                + " · ".join(parts)
                            )

                bonus_parts = []

                if card.get("inseason_bonus_pct", 0) > 0:
                    bonus_parts.append(
                        f"In-Season +{card['inseason_bonus_pct']:.1f}%"
                    )

                if card.get("xp_bonus_pct", 0) > 0:
                    bonus_parts.append(
                        f"XP +{card['xp_bonus_pct']:.1f}%"
                    )

                if card.get("collection_bonus_pct", 0) > 0:
                    bonus_parts.append(
                        f"Sammlung +{card['collection_bonus_pct']:.1f}%"
                    )

                bonus_text = (
                    " · ".join(bonus_parts)
                    if bonus_parts
                    else "keine Kartenboni"
                )

                embed.add_field(
                    name=(
                        f"{index}. {emoji} "
                        f"{card.get('player_name')} · {position}"
                    ),
                    value=(
                        f"🔮 Punkte-Prognose: "
                        f"**{card.get('projected_base_points', 0):.1f}** "
                        f"→ **{card.get('projected_card_points', 0):.1f}** "
                        f"inkl. Bonus\n"
                        f"✨ Bonus: **{bonus_text}** "
                        f"(gesamt +{card.get('total_card_bonus_pct', 0):.1f}%)\n"
                        f"⭐ Rating: **{card.get('rating', 0):.1f}/100**\n"
                        f"📊 L40: **{card.get('l40', 0):.2f}**\n"
                        f"{fixture_text}\n"
                        f"{starter_text}{cs_text}{matchup_text}{set_piece_text}\n"
                        f"{season_text}"
                    ),
                    inline=False,
                )

            classic_used = sum(
                1
                for card in team["cards"]
                if card.get("classic")
            )

            embed.set_footer(
                text=(
                    f"Classic-Slots: {classic_used}/1 · "
                    f"In-Season: {5 - classic_used}/5"
                )
            )

            await interaction.followup.send(embed=embed)

    except Exception as exc:
        print(f"FEHLER /streakteam: {exc}")
        await interaction.followup.send(
            f"❌ Fehler:\n```{str(exc)[:1700]}```"
        )


@bot.event
async def setup_hook():
    try:
        synced = await bot.tree.sync(guild=guild_object)
        print(f"{len(synced)} Slash-Befehl(e) synchronisiert.")
    except Exception as exc:
        print(f"Fehler beim Synchronisieren: {exc}")


bot.run(DISCORD_TOKEN)
