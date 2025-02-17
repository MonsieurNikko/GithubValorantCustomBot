import asyncio
import random
import os
import pandas as pd
import json
from playwright.async_api import async_playwright
import google.generativeai as genai
import discord
from discord.ext import commands
import re
from dotenv import load_dotenv

load_dotenv()


TOKEN = os.getenv("DISCORD_TOKEN")
GENAI_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="v/", intents=intents)

# ✅ Directory for storing data per server
BASE_DIR = "server_data"
os.makedirs(BASE_DIR, exist_ok=True)

players = []
base_url = "https://tracker.gg/valorant/profile/riot/{}/overview"

chrome_executable_path = "C:/Program Files/Google/Chrome/Application/chrome.exe"

def sanitize_filename(name):
    """Removes special characters to create a valid filename."""
    return re.sub(r'[<>:"/\\|?*]', '', name)

async def create_server_files(guild):
    """Creates a folder and empty JSON/CSV files named after the server."""
    server_name = sanitize_filename(guild.name)
    server_path = os.path.join(BASE_DIR, server_name)

    os.makedirs(server_path, exist_ok=True)  # Ensure the server folder exists

    csv_path = os.path.join(server_path, f"{server_name}_stats.csv")
    json_path = os.path.join(server_path, f"{server_name}_stats.json")

    if not os.path.exists(csv_path):
        df = pd.DataFrame(columns=["Username", "Rank", "K/D Ratio", "ACS", "Win %", "Damage/Round"])
        df.to_csv(csv_path, index=False, encoding="utf-8")

    if not os.path.exists(json_path):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)

    print(f"✅ New database created for server: '{guild.name}'")

async def scrape(ctx, players: list):
    """Scrapes player stats and saves only new players to the server's dataset."""
    
    server_name = sanitize_filename(ctx.guild.name)
    server_path = os.path.join(BASE_DIR, server_name)
    json_path = os.path.join(server_path, f"{server_name}_stats.json")

    existing_data = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        except json.JSONDecodeError:
            existing_data = []

    existing_usernames = {player["Username"] for player in existing_data} 
    new_data = []

    async with async_playwright() as p:
        for player in players:
            formatted_player = player.replace("#", "%23")
            url = base_url.format(formatted_player)

            if player in existing_usernames:
                print(f"⚠ **{player} already exists!** Skipping...")
                continue

            print(f"\n🔹 **Scraping stats for {player}...**")

            try:
                # ✅ Launch Chrome in **visible mode**
                browser = await p.chromium.launch(
                    headless=False,  # ✅ Keep browser visible
                    executable_path=chrome_executable_path,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--start-maximized",
                        "--disable-popup-blocking",
                        "--disable-renderer-backgrounding",
                        "--no-sandbox",
                    ]
                )

                context = await browser.new_context()
                page = await context.new_page()

                print(f"🔹 **Opening URL:** {url}")
                await page.goto(url, timeout=60000)

                # ✅ Handle Cloudflare CAPTCHA
                cloudflare_texts = ["Verify you are human", "Just a moment...", "Checking your browser"]
                page_content = await page.content()

                if any(text.lower() in page_content.lower() for text in cloudflare_texts):
                    print(f"⚠ **Cloudflare detected!** Solve the CAPTCHA manually.")
                    await asyncio.sleep(20)

                private_profile_texts = [
                    f"{players[players.index(player)].lower()}'s profile is private."
                ]
                try:

                    private_message_element = page.locator("span.font-light.font-stylized.text-40.uppercase").first

                    if await private_message_element.is_visible():
                        private_message = await private_message_element.text_content()
                        private_message = private_message.lower().strip()
                    else:
                        private_message = ""

                except Exception as e:
                    private_message = ""
                    print(f"❌ **Error detecting private profile message:** {e}")

                print(f"🔹 **Private Profile Message:** {private_message}")
                if any(text in private_message for text in private_profile_texts):
                    print(f"⚠ **{player} has a private profile! Stats cannot be retrieved.**")
                    await ctx.send(f"⚠ **{player} has a private profile! Stats cannot be retrieved.**")

                    stats = {
                        "Username": players[players.index(player)],
                        "Rank": "Private Profile",
                        "Damage/Round": "N/A",
                        "K/D Ratio": "N/A",
                        "Headshot %": "N/A",
                        "Win %": "N/A",
                        "Wins": "N/A",
                        "KAST": "N/A",
                        "DDΔ/Round": "N/A",
                        "Kills": "N/A",
                        "Deaths": "N/A",
                        "Assists": "N/A",
                        "ACS": "N/A",
                        "KAD Ratio": "N/A",
                        "Kills/Round": "N/A",
                        "First Bloods": "N/A",
                        "Flawless Rounds": "N/A",
                        "Aces": "N/A"
                    }

                    new_data.append(stats)
                    await browser.close()
                    continue

                await page.wait_for_selector(".numbers", timeout=20000)

                stats = {"Username": player}

                try:
                    rank_block = page.locator(".rating-entry__rank-info").first
                    if rank_block:
                        rank_value = await rank_block.locator(".value").text_content()
                        stats["Rank"] = rank_value.strip()
                        print(f"🏆 Rank: {rank_value}")
                    else:
                        stats["Rank"] = "N/A"
                except Exception:
                    stats["Rank"] = "N/A"

                stat_blocks = await page.locator(".numbers").all()
                for block in stat_blocks:
                    try:
                        name = await block.locator(".name").text_content()
                        value = await block.locator(".value").text_content()
                        stats[name.strip()] = value.strip()
                    except Exception:
                        continue

                new_data.append(stats)

                await browser.close()

            except Exception as e:
                print(f"❌ **Error scraping {player}:** {e}")

    if new_data:
        existing_data.extend(new_data)
        await save_to_files(existing_data, ctx.guild) 
        await ctx.send(f"✅ **New players added!**\n{', '.join([p['Username'] for p in new_data])}")
    else:
        await ctx.send("⚠ **No new data added.** All players already exist.")

    return new_data, existing_data



async def save_to_files(scraped_data, guild):
    """Saves player data to the correct server folder."""
    server_name = sanitize_filename(guild.name)
    server_path = os.path.join(BASE_DIR, server_name)
    json_path = os.path.join(server_path, f"{server_name}_stats.json")
    csv_path = os.path.join(server_path, f"{server_name}_stats.csv")

    if scraped_data:
        df = pd.DataFrame(scraped_data)
        df.to_csv(csv_path, index=False, encoding="utf-8")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(scraped_data, f, indent=4, ensure_ascii=False)

        print(f"✅ Data saved for server: '{guild.name}'")


async def analyze_with_ai(filepath: str):
    """Analyzes player stats directly from a JSON or CSV file."""

    if not os.path.exists(filepath):
        print(f"⚠ Error: File '{filepath}' not found. Please check the path.")
        return

    if filepath.endswith(".json"):
        with open(filepath, "r", encoding="utf-8") as f:
            scraped_data = json.load(f)
    elif filepath.endswith(".csv"):
        scraped_data = pd.read_csv(filepath).to_dict(orient="records")
    else:
        print("⚠ Unsupported format! Please use a CSV or JSON file.")
        return

    if not scraped_data:
        print("⚠ The file is empty or corrupted.")
        return

    stats_text = json.dumps(scraped_data, indent=2)

    model = genai.GenerativeModel("gemini-1.5-pro")
    try:
        response = model.generate_content(f"""
    **Create two optimally balanced Valorant teams using these 10 players.**  
    ---

    ### **Key Balancing Factors (Most Important First)**:
    🔹 **K/D Ratio (Combat efficiency)** – Must be **very close** between both teams.  
    🔹 **ACS (Average Combat Score) – Ensures equal fight impact.**  
    🔹 **Damage/Round (Overall consistency & firepower)** – Must also be balanced.  
    🔹 **Win % (Effectiveness in ranked matches).**  
    🔹 **First Bloods (Aggression & Entry power).**  
    🔹 **KAST (Kill/Assist/Survive/Trade – Player reliability).**  
    🔹 **Rank (Used ONLY as a tiebreaker, NOT a primary factor).**  

    ---
    ### **Handling Private Profiles:**  
    ✅ **If a player's profile is private**, you must still **include them** in the teams.  
    ✅ **Use available information (rank, username)** and balance based on the team averages.  
    ✅ **If no stats are available, assume neutral values close to the team average.**  
    ✅ **Ensure no major imbalance due to missing stats.**
    ---

    ### **Team Balancing Rules:**
    ✅ **Strict balancing required!** Both teams must have **nearly equal** average **K/D, ACS, and DMG/Round**.  
    ✅ **Max difference allowed** between teams:  
    - **K/D Ratio ≤ ±2%**  
    - **ACS ≤ ±2%**  
    - **DMG/Round ≤ ±2%**  
    ✅ **Ranks must be equally distributed** – No team should have **more high-rank players than the other**.  
    ✅ **Clearly show the FULL usernames of each player.**  
    ✅ **Provide precise team averages for all key stats.**
    ✅ **No need reasoning**  

    ---

    ### **Expected Output Format (Concise & Clear)**  
    **🏆 Team 1**  
    - **Nikkodinho#HAN (Ascendant 3)**, K/D: 1.08, Win%: 52.7%, ACS: 248, DMG/Rnd: 150.5, First Bloods: 120  
    - **Ngôn Lào#kezin (Ascendant 2)**, K/D: 1.03, Win%: 49.0%, ACS: 218, DMG/Rnd: 145.2, First Bloods: 112  
    - **YungTobi Sờ Đích#TOBI (Platinum 1)**, K/D: 0.88, Win%: 58.5%, ACS: 197, DMG/Rnd: 130.1, First Bloods: 95  
    - **itsmetrucc#uno (Ascendant 1)**, K/D: 1.02, Win%: 49.0%, ACS: 224, DMG/Rnd: 140.7, First Bloods: 105  
    - **Virus#LAJV (Ascendant 1)**, K/D: 0.77, Win%: 50.4%, ACS: 181, DMG/Rnd: 128.3, First Bloods: 85  

    **🏆 Team 2**  
    - **ImDaMinh#7777 (Ascendant 1)**, K/D: 1.06, Win%: 52.6%, ACS: 207, DMG/Rnd: 140.5, First Bloods: 110  
    - **Một Mẩu#1803 (Diamond 2)**, K/D: 0.83, Win%: 52.4%, ACS: 172, DMG/Rnd: 138.9, First Bloods: 98  
    - **K1N#gnouh (Ascendant 1)**, K/D: 1.14, Win%: 51.2%, ACS: 224, DMG/Rnd: 147.8, First Bloods: 118  
    - **HungAww#Viet (Ascendant 2)**, K/D: 1.22, Win%: 55.9%, ACS: 270, DMG/Rnd: 155.6, First Bloods: 130  
    - **ChocoPyke#1535 (Diamond 2)**, K/D: 1.03, Win%: 53.7%, ACS: 231, DMG/Rnd: 150.2, First Bloods: 115  

    📊 **Team Averages:**  
    - **Team 1**: **Rank: Ascendant 1 (19.2), K/D: 0.96, Win%: 51.9%, ACS: 214.4, DMG/Rnd: 138.9, First Bloods: 103.4, KAST: 70.5%**  
    - **Team 2**: **Rank: Ascendant 1 (19.3), K/D: 1.04, Win%: 52.8%, ACS: 217.1, DMG/Rnd: 143.2, First Bloods: 114.2, KAST: 71.2%**  

    **Now, generate two optimally balanced teams using these 10 players:**{stats_text}
        """, stream=False)

        ai_analysis = response.text.strip() if response.text else "⚠ No response received from the AI."

        print("\n🎯 **AI Analysis (Gemini) :**\n" + ai_analysis)

        with open("ai_analysis.txt", "w", encoding="utf-8") as f:
            f.write(ai_analysis)
        print("✅ AI analysis saved in 'ai_analysis.txt'")
        return response.text.strip()

    except Exception as e:
        print(f"⚠ Error generating AI response: {e}")
        return "⚠ AI analysis failed."

def load_existing_data(guild):
    """Loads the player stats for the current server."""
    server_name = sanitize_filename(guild.name)
    json_path = os.path.join(BASE_DIR, server_name, f"{server_name}_stats.json")

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            print(f"❌ Error: JSON file is corrupted for server {guild.name}. Resetting data.")
            return []
    return []


@bot.command(name="gt")
async def generate_teams(ctx):
    """Generates balanced teams if there are exactly 10 players in the server database."""
    existing_data = load_existing_data(ctx.guild)

    if len(existing_data) != 10:
        await ctx.send(f"⚠ **You need exactly 10 players to generate teams.**\n"
                       f"Currently available: **{len(existing_data)}**\n"
                       f"Use `v/st <player>` to add more players.")
        return

    await ctx.send("📥 **Processing player stats... Please wait!**")

    json_path = os.path.join(BASE_DIR, sanitize_filename(ctx.guild.name), f"{sanitize_filename(ctx.guild.name)}_stats.json")
    result = await analyze_with_ai(json_path)

    await ctx.send(f"🎯 **Generated Teams:**\n```{result}```")


@bot.command(name="st")
async def scrape_command(ctx, *, players: str):
    if not players:
        await ctx.send("⚠ **Enter at least one player name!** Example: `v/st Player#1234`")
        return

    raw_players = players.split(",")
    formatted_players = [player.strip() for player in raw_players]

    await ctx.send(f"🔄 **Checking stats for:** {', '.join(formatted_players)}...")

    result = await scrape(ctx, formatted_players)
    if result is None:
        await ctx.send("⚠ **Scraping failed!** Please try again later.")
        return

    new_data, existing_data = result
    message = ""

    for player in formatted_players:
        player_stats = next((p for p in existing_data if p["Username"] == player), None)
        if player_stats:
            message += f"\n✅ **Existing stats for {player}:**\n"
            for stat, value in player_stats.items():
                if stat != "Username":
                    message += f"🔹 {stat}: {value}\n"

    if message:
        await ctx.send(message)
    else:
        await ctx.send("⚠ **No data found for the requested players.** Check the usernames and try again.")


@bot.command(name="r")
async def remove_player(ctx, *, player: str):
    """Removes a player from the saved stats of the current server."""
    server_name = sanitize_filename(ctx.guild.name)
    server_path = os.path.join(BASE_DIR, server_name)
    json_path = os.path.join(server_path, f"{server_name}_stats.json")
    csv_path = os.path.join(server_path, f"{server_name}_stats.csv")

    if not os.path.exists(json_path):
        await ctx.send(f"⚠ **No stats file found for this server!**")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            existing_data = json.load(f)
        except json.JSONDecodeError:
            await ctx.send("⚠ **The JSON file is corrupted!**")
            return

    player_data = next((p for p in existing_data if p["Username"].lower() == player.lower()), None)

    if player_data:
        existing_data = [p for p in existing_data if p["Username"].lower() != player.lower()]

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=4, ensure_ascii=False)

        df = pd.DataFrame(existing_data)
        df.to_csv(csv_path, index=False, encoding="utf-8")

        await ctx.send(f"✅ **{player} has been removed from the stats!**")
    else:
        await ctx.send(f"⚠ **{player} not found in the saved stats!**")


bot.remove_command("help")
@bot.command(name="help", aliases=["commands"])
async def help_command(ctx):
    embed = discord.Embed(
        title="Commands - ValoCustom",
        description="Here are all available commands:",
        color=discord.Color.red()
    )
    embed.add_field(
        name="`v/st player#TAG,...`",
        value="➜ Add player(s) to the list. Need 10 players to start a custom match.",
        inline=False
    )
    embed.add_field(
        name="`v/gt`",
        value="➜ Generate team arrangement.",
        inline=False
    )
    embed.add_field(
        name="`v/r player#TAG`",
        value="➜ Remove a player from the list.",
        inline=False
    )
    embed.add_field(
        name="`v/clear`",
        value="➜ Clear the entire player list.",
        inline=False
    )
    await ctx.send(embed=embed)


@bot.command(name="clear")
async def clear_data(ctx):
    """Clears all player stats for the current server."""
    server_name = sanitize_filename(ctx.guild.name)
    server_path = os.path.join(BASE_DIR, server_name)
    json_path = os.path.join(server_path, f"{server_name}_stats.json")
    csv_path = os.path.join(server_path, f"{server_name}_stats.csv")

    # Vérifie si le fichier JSON existe
    if not os.path.exists(json_path):
        await ctx.send(f"⚠ **No stats file found for this server!**")
        return

    # Supprime toutes les données et écrase les fichiers avec des listes vides
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([], f, indent=4, ensure_ascii=False)

    df = pd.DataFrame(columns=["Username", "Rank", "K/D Ratio", "ACS", "Win %", "Damage/Round"])
    df.to_csv(csv_path, index=False, encoding="utf-8")

    await ctx.send(f"✅ **All player stats have been cleared for this server!**")
    print(f"🔄 **Data cleared for server: {server_name}**")


@bot.command(name="sl")
async def show_list(ctx):
    """Displays the list of players currently saved for the server."""
    server_name = sanitize_filename(ctx.guild.name)
    server_path = os.path.join(BASE_DIR, server_name)
    json_path = os.path.join(server_path, f"{server_name}_stats.json")
    csv_path = os.path.join(server_path, f"{server_name}_stats.csv")

    if not os.path.exists(json_path):
        await ctx.send(f"⚠ **No stats file found for this server!**")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            existing_data = json.load(f)
        except json.JSONDecodeError:
            await ctx.send("⚠ **The JSON file is corrupted!**")
            return

    players = [p["Username"] for p in existing_data]
    if players:
        await ctx.send(f"📊 **Current Player List:**\n{', '.join(players)}"
                       f"\n\n**Total Players:** {len(players)}")
    else:
        await ctx.send("⚠ **No players found in the list!**")


@bot.event
async def on_guild_join(guild):
    """Triggered when the bot joins a new server."""
    await create_server_files(guild)
    print(f"🔹 Bot joined a new server: {guild.name} (ID: {guild.id})")


@bot.event
async def on_ready():
    print(f"✅ Bot is ready! Logged in as {bot.user}")
    for guild in bot.guilds:
        await create_server_files(guild)


if __name__ == "__main__":
    bot.run(TOKEN)

