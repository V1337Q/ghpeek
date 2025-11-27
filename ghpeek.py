#!/usr/bin/env python3

import argparse
import os
import json
import re
import tempfile
import subprocess
from collections import OrderedDict
from datetime import timedelta
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from rich.console import Console
from rich.table import Table
from rich.padding import Padding
from rich.columns import Columns
from rich.prompt import IntPrompt

console = Console()

API_BASE = "https://api.github.com/users/{}"
PROFILE_BASE = "https://github.com/{}"
GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"

def display_profile_picture(avatar_url, username):
    """Display profile picture using kitty +kitten icat."""
    try:
        # Download the image to a temporary file
        response = requests.get(avatar_url, timeout=10)
        if response.status_code != 200:
            return False
            
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
            tmp_file.write(response.content)
            temp_filename = tmp_file.name
        
        # Use kitty +kitten icat to display the image
        result = subprocess.run([
            'kitty', '+kitten', 'icat', 
            temp_filename
        ])
        
        # Clean up the temporary file
        os.unlink(temp_filename)
        
        if result.returncode == 0:
            console.print(f"[dim](Profile picture displayed)[/dim]\n")
            return True
        else:
            console.print("[yellow]Failed to display profile picture[/yellow]\n")
            return False
        
    except Exception as e:
        console.print(f"[yellow]Failed to load profile picture: {e}[/yellow]\n")
        return False


def fetch_user_api(username):
    """Fetch basic public user info via GitHub REST API."""
    url = API_BASE.format(username)
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 404:
        return None, f"User '{username}' not found (API)."
    if r.status_code != 200:
        return None, f"API error {r.status_code}: {r.text[:200]}"
    return r.json(), None

def fetch_recent_activity(username, count=30):
    """Fetch recent user activity (commits, etc.)."""
    if not TOKEN:
        return None, "GITHUB_TOKEN not set; needed for recent activity."
    
    url = f"https://api.github.com/users/{username}/events"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "ghpeek/1.0"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"API error {r.status_code}: {r.text[:200]}"
            
        events = r.json()
        if not events:
            return None, "No recent activity found."
        
        recent_activity = []
        
        for event in events:
            if len(recent_activity) >= count:
                break
                
            event_type = event.get('type')
            repo_name = event.get('repo', {}).get('name', 'Unknown')
            date = event.get('created_at', '')
            
            if event_type == 'PushEvent':
                commits = event.get('payload', {}).get('commits', [])
                for commit in commits:
                    if len(recent_activity) >= count:
                        break
                    recent_activity.append({
                        'type': 'commit',
                        'repo': repo_name,
                        'message': commit.get('message', 'No message').split('\n')[0],
                        'sha': commit.get('sha', '')[:7],
                        'url': commit.get('url', ''),
                        'date': date
                    })
                    
            elif event_type in ['CreateEvent', 'DeleteEvent', 'WatchEvent', 'ForkEvent', 'IssuesEvent', 'PullRequestEvent']:
                # Other notable events
                if len(recent_activity) >= count:
                    break
                    
                action = event.get('payload', {}).get('action', '')
                ref_type = event.get('payload', {}).get('ref_type', '')
                
                if event_type == 'CreateEvent':
                    message = f"Created {ref_type}"
                elif event_type == 'DeleteEvent':
                    message = f"Deleted {ref_type}"
                elif event_type == 'WatchEvent':
                    message = "Starred repository"
                elif event_type == 'ForkEvent':
                    message = "Forked repository"
                elif event_type == 'IssuesEvent':
                    message = f"{action} issue"
                elif event_type == 'PullRequestEvent':
                    message = f"{action} pull request"
                else:
                    message = f"{event_type} {action}"
                
                recent_activity.append({
                    'type': event_type.lower(),
                    'repo': repo_name,
                    'message': message,
                    'sha': '',
                    'url': event.get('repo', {}).get('url', '').replace('api.github.com/repos', 'github.com'),
                    'date': date
                })
        
        if not recent_activity:
            return None, "No recent activity found."
            
        return recent_activity, None
        
    except Exception as e:
        return None, f"Error fetching recent activity: {str(e)}"

def display_recent_commits(username, count=10):
    activity, err = fetch_recent_activity(username, count)
    if err:
        console.print(f"[yellow]Recent activity: {err}[/yellow]")
        return
    
    if not activity:
        console.print("[dim]No recent activity found.[/dim]")
        return
    
    console.print(f"\n[bold]Recent Activity ({len(activity)} most recent)[/bold]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Type", style="cyan", width=10)
    table.add_column("Repository", style="green", width=25)
    table.add_column("Action", style="white", width=50)
    table.add_column("Date", style="dim", width=12)
    
    for item in activity:
        activity_type = item['type']
        repo = item['repo']
        message = item['message'][:47] + "..." if len(item['message']) > 47 else item['message']
        date = dateparser.parse(item['date']).strftime("%m/%d/%Y") if item['date'] else "Unknown"
        
        # Color code the activity type
        if activity_type == 'commit':
            type_display = "[green]commit[/green]"
        elif activity_type in ['createevent', 'forkevent']:
            type_display = "[blue]create[/blue]"
        elif activity_type == 'watchevent':
            type_display = "[yellow]star[/yellow]"
        elif activity_type in ['issuesevent', 'pullrequestevent']:
            type_display = "[magenta]pr/issue[/magenta]"
        else:
            type_display = f"[white]{activity_type}[/white]"
        
        table.add_row(type_display, repo, message, date)
    
    console.print(table)


def fetch_user_repos(username, count=30, sort="updated"):
    if not TOKEN:
        return None, "GITHUB_TOKEN not set; needed for repositories."
    
    url = f"https://api.github.com/users/{username}/repos?sort={sort}&per_page={count}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "ghpeek/1.0"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"API error {r.status_code}: {r.text[:200]}"
            
        repos = r.json()
        if not repos:
            return None, "No repositories found."
            
        return repos, None
        
    except Exception as e:
        return None, f"Error fetching repositories: {e}"


def display_user_repos(username, count=10):
    repos, err = fetch_user_repos(username, count)
    if err:
        console.print(f"[yellow]Repositories: {err}[/yellow]")
        return
    
    if not repos:
        console.print("[dim]No repositories found.[/dim]")
        return
    
    console.print(f"\n[bold]Repositories ({len(repos)} most recent)[/bold]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Repository", style="cyan", width=30)
    table.add_column("Description", style="white", width=50)
    table.add_column("Stars", style="yellow", width=8)
    table.add_column("Forks", style="green", width=8)
    table.add_column("Language", style="blue", width=15)
    table.add_column("Updated", style="dim", width=12)
    
    for repo in repos:
        name = repo.get('name', '')
        description = repo.get('description', '') or 'No description'
        stars = repo.get('stargazers_count', 0)
        forks = repo.get('forks_count', 0)
        language = repo.get('language', '')
        updated = repo.get('updated_at', '')
        url = repo.get('html_url', '')
        
        # Truncate description if too long
        desc_display = description[:47] + "..." if len(description) > 47 else description
        
        # Format updated date
        updated_display = dateparser.parse(updated).strftime("%m/%d/%Y") if updated else "Unknown"
        
        # Make repository name clickable, currently not working.
        name_display = f"[link={url}]{name}[/link]"
        
        table.add_row(
            name_display,
            desc_display,
            str(stars),
            str(forks),
            language,
            updated_display
        )
    
    console.print(table)
    
    # Show additional repo stats
    total_stars = sum(repo.get('stargazers_count', 0) for repo in repos)
    total_forks = sum(repo.get('forks_count', 0) for repo in repos)
    languages = [repo.get('language') for repo in repos if repo.get('language')]
    top_language = max(set(languages), key=languages.count) if languages else "None"
    
    console.print(f"\n[dim]Stats: {total_stars} total stars • {total_forks} total forks • Top language: {top_language}[/dim]")


def fetch_pinned_repos(username):
    """Fetch user's pinned repositories."""
    # GraphQL query for pinned repositories
    query = """
    query($login: String!) {
      user(login: $login) {
        pinnedItems(first: 6, types: REPOSITORY) {
          nodes {
            ... on Repository {
              name
              description
              url
              stargazerCount
              forkCount
              primaryLanguage {
                name
                color
              }
            }
          }
        }
      }
    }
    """
    
    if not TOKEN:
        return None, "GITHUB_TOKEN not set; needed for pinned repos."
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "ghpeek/1.0"
    }
    
    try:
        r = requests.post(GRAPHQL_ENDPOINT,
                         json={"query": query, "variables": {"login": username}},
                         headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"GraphQL error {r.status_code}"
            
        data = r.json()
        if "errors" in data:
            return None, f"GraphQL errors: {data['errors']}"
            
        user_data = data.get("data", {}).get("user")
        if not user_data:
            return None, "User not found or access denied."
            
        pinned_items = user_data.get("pinnedItems", {}).get("nodes", [])
        return pinned_items, None
        
    except Exception as e:
        return None, f"Error fetching pinned repos: {e}"

def render_repo_box(repo, use_nerd=False):
    name = repo.get('name', '')
    description = repo.get('description', '') or 'No description'
    url = repo.get('url', '')
    stars = repo.get('stargazerCount', 0)
    forks = repo.get('forkCount', 0)
    language = repo.get('primaryLanguage', {})
    lang_name = language.get('name', '') if language else ''
    lang_color = language.get('color', '#ffffff') if language else '#ffffff'
    
    if use_nerd:
        top_left = ""
        top_right = ""
        bottom_left = ""
        bottom_right = ""
        horizontal = "─"
        vertical = "│"
    else:
        # Sharp edges
        # top_left = "┌"
        # top_right = "┐"
        # bottom_left = "└"
        # bottom_right = "┘"
        # horizontal = "─"
        # vertical = "│"
        top_left = "╭"
        top_right = "╮"
        bottom_left = "╰"
        bottom_right = "╯"
        horizontal = "─"
        vertical = "│"
    # Fixed width for consistent layout
    box_width = 38
    
    # Truncate repo name if too long for title
    max_name_length = box_width - 6
    display_name = name[:max_name_length] + "..." if len(name) > max_name_length else name
    title = f" {display_name} "
    
    # Center the title
    title_padding = box_width - len(title) - 2
    left_padding = title_padding // 2
    right_padding = title_padding - left_padding
    
    title_line = f"{top_left}{horizontal * left_padding}{title}{horizontal * right_padding}{top_right}"
    
    # Description line
    max_desc_chars = box_width - 4
    desc_text = description.strip()
    if len(desc_text) > max_desc_chars:
        truncated = desc_text[:max_desc_chars - 3]
        last_space = truncated.rfind(' ')
        if last_space > max_desc_chars - 10:
            desc_display = truncated[:last_space] + "..."
        else:
            desc_display = truncated + "..."
    else:
        desc_display = desc_text
    
    desc_padding = box_width - len(desc_display) - 3
    desc_line = f"{vertical} {desc_display}{' ' * desc_padding}{vertical}"
    
    stats_parts = []
    visible_stats_parts = []
    
    if stars > 0:
        stats_parts.append(f"⭐ {stars}")
        visible_stats_parts.append(f"⭐ {stars}")
    if forks > 0:
        stats_parts.append(f" {forks}")
        visible_stats_parts.append(f" {forks}")
    if lang_name:
        short_lang = lang_name[:8] + "..." if len(lang_name) > 11 else lang_name
        stats_parts.append(f"[{lang_color}]●[/] {short_lang}")
        visible_stats_parts.append(f"● {short_lang}")  
    visible_stats_text = " · ".join(visible_stats_parts)
    max_stats_chars = box_width - 4
    
    # Truncate if too long (using visible length)
    if len(visible_stats_text) > max_stats_chars:
        while len(visible_stats_text) > max_stats_chars and len(stats_parts) > 1:
            stats_parts.pop()
            visible_stats_parts.pop()
            visible_stats_text = " · ".join(visible_stats_parts)
        if len(visible_stats_text) > max_stats_chars:
            visible_stats_text = visible_stats_text[:max_stats_chars - 1] + "…"
            stats_parts = [visible_stats_text]
    
    stats_text = " · ".join(stats_parts)
    stats_padding = box_width - len(visible_stats_text) - 4
    stats_line = f"{vertical} {stats_text}{' ' * stats_padding}{vertical}"
    empty_line = f"{vertical}{' ' * (box_width - 2)}{vertical}"
    bottom_line = f"{bottom_left}{horizontal * (box_width - 2)}{bottom_right}"
    box_content = f"{title_line}\n{desc_line}\n{empty_line}\n{stats_line}\n{bottom_line}"

    return box_content


def fetch_contributions_graphql(username):
    """
    Fetch contributions via GitHub's GraphQL API.
    Requires GITHUB_TOKEN set (TOKEN variable).
    Returns (OrderedDict(date->int), None) or (None, error_message).
    """
    if not TOKEN:
        return None, "GITHUB_TOKEN not set; GraphQL requires an auth token."

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "ghpeek/1.0"
    }

    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                color
              }
            }
          }
        }
      }
    }
    """

    try:
        r = requests.post(GRAPHQL_ENDPOINT, 
                         json={"query": query, "variables": {"login": username}}, 
                         headers=headers, timeout=15)
    except Exception as e:
        return None, f"Network/GraphQL request error: {e}"

    if r.status_code != 200:
        return None, f"GraphQL error {r.status_code}: {r.text[:200]}"

    try:
        data = r.json()
    except Exception as e:
        return None, f"Failed to decode GraphQL JSON: {e}"

    if "errors" in data:
        return None, f"GraphQL errors: {data['errors']}"

    user_data = data.get("data", {}).get("user")
    if not user_data:
        return None, "GraphQL: user not found or access denied."

    try:
        weeks = user_data["contributionsCollection"]["contributionCalendar"]["weeks"]
        total_contributions = user_data["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    except Exception:
        return None, "GraphQL: unexpected response structure."

    flat = {}
    for w in weeks:
        for day in w.get("contributionDays", []):
            try:
                d = dateparser.parse(day["date"]).date()
                flat[d] = int(day.get("contributionCount", 0))
            except Exception:
                continue

    ordered = OrderedDict(sorted(flat.items()))
    if not ordered:
        return None, "GraphQL: no contribution days parsed."
    
    console.print(f"[dim]Total contributions: {total_contributions}[/dim]")
    return ordered, None


def fetch_contributions_from_profile(username):
    """
    Extract contribution data from the GitHub profile page.
    This method looks for the JavaScript data in the page.
    """
    url = PROFILE_BASE.format(username)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
    except Exception as e:
        return None, f"Network error fetching profile: {e}"

    if r.status_code == 404:
        return None, f"Profile for '{username}' not found (404)."
    if r.status_code != 200:
        return None, f"Failed to fetch profile ({r.status_code})."

    return extract_contributions_from_html(r.text)


def extract_contributions_from_html(html):
    """
    Extract contribution data from HTML using multiple methods.
    """
    # Method 1: Look for react data
    contributions = extract_from_react_data(html)
    if contributions:
        return contributions, None

    # Method 2: Look for JSON in script tags
    contributions = extract_from_script_tags(html)
    if contributions:
        return contributions, None

    # Method 3: Try to parse from SVG rectangles (legacy method)
    contributions = extract_from_svg_rects(html)
    if contributions:
        return contributions, None

    return None, "Could not extract contribution data using any method"


def extract_from_react_data(html):
    """Extract data from react-app data attribute."""
    try:
        # Look for the react data div
        soup = BeautifulSoup(html, 'html.parser')
        react_div = soup.find('div', {'data-target': 'react-app.data'})
        if react_div and react_div.string:
            json_data = json.loads(react_div.string)
            return parse_contributions_from_json_data(json_data)
    except Exception as e:
        pass
    return None


def extract_from_script_tags(html):
    """Extract data from JavaScript in script tags."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        scripts = soup.find_all('script')
        
        for script in scripts:
            if script.string:
                content = script.string
                
                # Look for JSON data with contribution information
                json_matches = re.findall(r'(\{.*?"contributionCalendar".*?\})', content, re.DOTALL)
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        contributions = parse_contributions_from_json_data(data)
                        if contributions:
                            return contributions
                    except:
                        continue
                        
                # Look for specific GraphQL data
                if 'contributionsCollection' in content:
                    # Try to extract the data from various patterns
                    patterns = [
                        r'{"data":\s*(\{.*?"contributionsCollection".*?\})',
                        r'var\s+data\s*=\s*(\{.*?"contributionsCollection".*?\})',
                        r'JSON\.parse\s*\(\s*[\'"](.*?)[\'"]\s*\)',
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, content, re.DOTALL)
                        for match in matches:
                            try:
                                # Handle escaped JSON
                                json_str = match.replace('\\"', '"').replace('\\/', '/')
                                data = json.loads(json_str)
                                contributions = parse_contributions_from_json_data(data)
                                if contributions:
                                    return contributions
                            except:
                                continue
    except Exception as e:
        pass
        
    return None


def extract_from_svg_rects(html):
    """Extract data from SVG rectangles (legacy fallback)."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        rects = soup.find_all('rect', {
            'data-date': True,
            'data-level': True
        })
        
        if not rects:
            # Try alternative selectors
            rects = soup.find_all('rect', {'data-date': True})
        
        flat = {}
        for rect in rects:
            try:
                date_str = rect.get('data-date')
                count_str = rect.get('data-count') or '0'
                
                # If no data-count, try to infer from data-level
                if count_str == '0':
                    level = rect.get('data-level', '0')
                    # Convert level to approximate count
                    level_map = {'1': 1, '2': 5, '3': 10, '4': 20}
                    count_str = str(level_map.get(level, '0'))
                
                date_obj = dateparser.parse(date_str).date()
                flat[date_obj] = int(count_str)
            except Exception:
                continue
        
        ordered = OrderedDict(sorted(flat.items()))
        return ordered if ordered else None
    except Exception as e:
        return None


def parse_contributions_from_json_data(data):
    """Parse contributions from various JSON structures."""
    try:
        # Try different JSON structures
        user_data = None
        
        # Structure 1: Direct user data
        if 'user' in data:
            user_data = data['user']
        # Structure 2: Nested in props
        elif 'props' in data and 'user' in data['props']:
            user_data = data['props']['user']
        # Structure 3: Nested in payload
        elif 'payload' in data and 'user' in data['payload']:
            user_data = data['payload']['user']
        # Structure 4: Direct contributions collection
        elif 'contributionsCollection' in data:
            user_data = data
        
        if not user_data:
            return None
            
        contributions_data = user_data.get('contributionsCollection', {})
        calendar = contributions_data.get('contributionCalendar', {})
        weeks = calendar.get('weeks', [])
        
        flat = {}
        total_contributions = 0
        
        for week in weeks:
            for day in week.get('contributionDays', []):
                date_str = day.get('date')
                count = day.get('contributionCount', 0)
                if date_str:
                    try:
                        date_obj = dateparser.parse(date_str).date()
                        flat[date_obj] = count
                        total_contributions += count
                    except Exception:
                        continue
        
        ordered = OrderedDict(sorted(flat.items()))
        if ordered:
            console.print(f"[dim]Total contributions: {total_contributions}[/dim]")
            return ordered
    except Exception as e:
        pass
        
    return None


def build_weeks_matrix(date_to_count, weeks=53):
    if not date_to_count:
        return []

    all_dates = list(date_to_count.keys())
    if not all_dates:
        return []
        
    start = all_dates[0]
    end = all_dates[-1]

    # Create a complete date range
    total_days = (end - start).days + 1
    full_map = {}
    for i in range(total_days):
        d = start + timedelta(days=i)
        full_map[d] = date_to_count.get(d, 0)

    # Find the first Sunday
    first_sunday = start
    while first_sunday.weekday() != 6:  # Sunday=6
        first_sunday -= timedelta(days=1)

    columns = []
    cur = first_sunday
    while cur <= end:
        col = []
        for dow in range(7):  # Sunday to Saturday
            day = cur + timedelta(days=dow)
            col.append(full_map.get(day, 0))
        columns.append(col)
        cur += timedelta(days=7)

    # Trim to requested number of weeks
    if len(columns) > weeks:
        columns = columns[-weeks:]
    elif len(columns) < weeks:
        # Pad with empty weeks at the beginning
        pad = weeks - len(columns)
        columns = [[0]*7 for _ in range(pad)] + columns

    return columns


def choose_shade(count, max_count):
    """Choose intensity based on count."""
    if count == 0:
        return 0
    if max_count == 0:
        return 1
    
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4

def render_contrib_graph(columns, use_nerd=False):
    if not columns:
        console.print("[yellow]No contribution data to display.[/yellow]")
        return

    all_counts = [count for week in columns for count in week]
    max_count = max(all_counts) if all_counts else 1

    dot = "" if use_nerd else ""
    shades = {
        # 0: ("·", "bright_black"),
        0: ("", "#2a313c"),
        1: (dot, "#9be9a8"),
        2: (dot, "#40c463"),
        3: (dot, "#30a14e"),
        4: (dot, "#216e39"),
    }

    rows = []
    for day in range(7):
        row = []
        for week in columns:
            count = week[day]
            shade = choose_shade(count, max_count)
            char, color = shades[shade]
            row.append(f"[{color}]{char}[/]")
        rows.append(" ".join(row))

    console.print("\n[bold]Contribution Graph[/bold]")
    console.print("[dim](Most recent on the right)[/dim]\n")
    
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for i, (name, row) in enumerate(zip(day_names, rows)):
        console.print(f"[dim]{name:>3}[/dim]  {row}")
    
    # Legend
    console.print("\n[dim]Less[/dim] " + " ".join([f"[{shades[i][1]}]{shades[i][0]}[/]" for i in range(0, 5)]) + " [dim]More[/dim]")

def print_profile_card(user_json, args):
    # Display profile picture first if available and not disabled
    avatar_url = user_json.get("avatar_url")
    if avatar_url and not args.no_picture:
        display_profile_picture(avatar_url, user_json.get("login", ""))

    table = Table.grid(expand=False)
    table.add_column(style="bold cyan", justify="right")
    table.add_column()

    name = user_json.get("name") or ""
    login = user_json.get("login") or ""
    bio = user_json.get("bio") or ""
    location = user_json.get("location") or ""
    url = user_json.get("html_url") or ""
    repos = user_json.get("public_repos", 0)
    followers = user_json.get("followers", 0)
    following = user_json.get("following", 0)
    created_at = user_json.get("created_at")
    
    if created_at:
        try:
            created = dateparser.parse(created_at).strftime("%b %d, %Y")
        except Exception:
            created = created_at
    else:
        created = "Unknown"

    table.add_row("Profile:", f"{name} ([link={url}]@{login}[/link])")
    if bio:
        table.add_row("Bio:", bio)
    if location:
        table.add_row("Location:", location)
    table.add_row("Repositories:", str(repos))
    table.add_row("Followers:", str(followers))
    table.add_row("Following:", str(following))
    table.add_row("Joined:", created)

    console.print(Padding(table, (0, 0, 1, 0)))

def display_pinned_repos(username, use_nerd=False):
    pinned_repos, err = fetch_pinned_repos(username)
    if err:
        console.print(f"[yellow]Pinned repos: {err}[/yellow]")
        return
    
    if not pinned_repos:
        console.print("[dim]No pinned repositories found.[/dim]")
        return
    
    console.print("\n[bold]Pinned Repositories[/bold]\n")
    
    # Create repo boxes
    repo_boxes = []
    for repo in pinned_repos:
        box = render_repo_box(repo, use_nerd=use_nerd)
        repo_boxes.append(box)
    
    # Use a simple 2-column layout with equal spacing
    from rich.columns import Columns
    columns = Columns(repo_boxes, equal=True, column_first=True, expand=True)
    console.print(columns)


def show_interactive_menu(username, use_nerd=False):
    console.print("\n[bold cyan]Additional Options:[/bold cyan]")
    # console.print("[dim]1.[/dim] View recent commits")
    console.print("[dim]1.[/dim] View recent activities")
    console.print("[dim]2.[/dim] View pinned repositories") 
    console.print("[dim]3.[/dim] View all repositories")
    console.print("[dim]4.[/dim] View contribution graph again")
    console.print("[dim]5.[/dim] Exit")
    
    while True:
        try:
            choice = IntPrompt.ask("\n[bold]Enter your choice[/bold]", choices=["1", "2", "3", "4", "5"], default=5)
            
            if choice == 1:
                count = IntPrompt.ask("How many recent commits to show?", default=10)
                display_recent_commits(username, count)
            elif choice == 2:
                display_pinned_repos(username, use_nerd)
            elif choice == 3:
                count = IntPrompt.ask("How many repositories to show?", default=10)
                display_user_repos(username, count)
            elif choice == 4:

                # Re-fetch and display contributions
                date_to_count, err = fetch_contributions_graphql(username)
                if not date_to_count:
                    date_to_count, err = fetch_contributions_from_profile(username)
                if date_to_count:
                    columns = build_weeks_matrix(date_to_count)
                    render_contrib_graph(columns, use_nerd=use_nerd)
                else:
                    console.print(f"[red]Failed to fetch contributions: {err}[/red]")
            elif choice == 5:
                console.print("[green]Goodbye! 👋[/green]")
                break
                
        except KeyboardInterrupt:
            console.print("\n[green]Goodbye! 👋[/green]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

def display_achievement_badges(username):
    # GitHub Achievements badge URLs
    achievements = [
        {
            "name": "Quickdraw",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/quickdraw-default.png"
        },
        {
            "name": "Starstruck", 
            "url": "https://github.githubassets.com/images/modules/profile/achievements/starstruck-default.png"
        },
        {
            "name": "Pair Extraordinaire",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/pair-extraordinaire-default.png"
        },
        {
            "name": "Pull Shark",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/pull-shark-default.png"
        },
        {
            "name": "Galaxy Brain",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/galaxy-brain-default.png"
        },
        {
            "name": "YOLO",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/yolo-default.png"
        },
        {
            "name": "Arctic Code Vault",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/arctic-code-vault-contributor-default.png"
        },
        {
            "name": "Public Donation",
            "url": "https://github.githubassets.com/images/modules/profile/achievements/public-sponsor-default.png"
        }
    ]
    
    console.print("\n[bold]GitHub Achievements[/bold]\n")
    
    successful_badges = 0
    temp_files = []
    
    try:
        # download all badges
        for achievement in achievements:
            try:
                response = requests.get(achievement["url"], timeout=10)
                if response.status_code == 200:
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                        tmp_file.write(response.content)
                        temp_files.append(tmp_file.name)
                    successful_badges += 1
            except Exception:
                continue
        
        if successful_badges == 0:
            console.print("[dim]No achievement badges could be loaded[/dim]")
            return
        
        # Calculate positions for horizontal layout
        badge_width = 6  # characters wide
        badge_height = 6  # characters tall
        spacing = 1      # 1 character spacing between badges
        
        # Get current cursor position by printing some invisible text and getting position
        # Then calculate Y position to be below the current content
        console.print()  # Add some spacing first
        
        # Display badges in a horizontal row
        for i, temp_filename in enumerate(temp_files):
            x_position = i * (badge_width + spacing)
            # Whatever whatever
            y_position = 40  # Start 10 lines down from current position
            result = subprocess.run([
                'kitty', '+kitten', 'icat',
                '--place', f'{badge_width}x{badge_height}@{x_position}x{y_position}',
                temp_filename
            ])
        
    except Exception as e:
        console.print(f"[yellow]Error displaying badges: {e}[/yellow]")
    
    finally:
        # Clean up all temporary files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:
                pass
    
    # Add more spacing after badges to ensure pinned repos appear below them
    console.print("\n\n")
    console.print(f"[dim]Displayed {successful_badges} achievement badges[/dim]")

def main():
    parser = argparse.ArgumentParser(description="Preview GitHub profile with contributions")
    parser.add_argument("username", help="GitHub username")
    parser.add_argument("--weeks", "-w", type=int, default=53, help="Weeks to display (default: 53)")
    parser.add_argument("--nerd", action="store_true", help="Use Nerd Font glyphs")
    parser.add_argument("--no-graphql", action="store_true", help="Skip GraphQL API")
    parser.add_argument("--no-picture", action="store_true", help="Skip profile picture display")
    parser.add_argument("--no-pinned", action="store_true", help="Skip pinned repositories")
    parser.add_argument("--no-interactive", action="store_true", help="Skip interactive menu")
    parser.add_argument("--no-badges", action="store_true", help="Skip achievement badges")
    parser.add_argument("--commits", "-c", type=int, help="Show N recent commits and exit")
    parser.add_argument("--repos", "-r", type=int, help="Show N repositories and exit")
    
    args = parser.parse_args()
    username = args.username.strip()

    console.print(f"[bold]GitHub Profile Preview[/bold] — [green]{username}[/green]\n")

    # Fetch basic profile info
    user_json, err = fetch_user_api(username)
    if err:
        console.print(f"[yellow]API warning:[/yellow] {err}")
        user_json = {"login": username, "html_url": f"https://github.com/{username}"}

    print_profile_card(user_json, args)

    # Show recent commits if requested
    if args.commits:
        display_recent_commits(username, args.commits)
        return

    # Show repositories if requested
    if args.repos:
        display_user_repos(username, args.repos)
        return

    # Try different methods to get contribution data
    date_to_count = None
    method_used = ""
    
    # Method 1: GraphQL
    if TOKEN and not args.no_graphql:
        # console.print("[dim]Trying GraphQL API...[/dim]")
        date_to_count, err = fetch_contributions_graphql(username)
        if date_to_count:
            method_used = "GraphQL API"
            console.print("[green]✓[/green] Successfully fetched via GraphQL")

    # Method 2: Profile page data extraction
    if not date_to_count:
        console.print("[dim]Trying profile data extraction...[/dim]")
        date_to_count, err = fetch_contributions_from_profile(username)
        if date_to_count:
            method_used = "profile data extraction"
            console.print("[green]✓[/green] Successfully extracted from profile")

    # Display results
    if date_to_count:
        columns = build_weeks_matrix(date_to_count, weeks=args.weeks)
        render_contrib_graph(columns, use_nerd=args.nerd)
        if method_used:
            console.print(f"[dim]Data fetched via: {method_used}[/dim]")
        
        if not args.no_badges:
            display_achievement_badges(username)
    else:
        console.print(f"[red]Failed to fetch contribution data:[/red] {err}")
        console.print("\n[dim]Tips:[/dim]")
        console.print("[dim]• Set GITHUB_TOKEN environment variable for GraphQL access[/dim]")
        console.print("[dim]• The user might have no public contributions[/dim]")
        console.print("[dim]• GitHub might have changed their data structure again[/dim]")

    if not args.no_pinned:
        display_pinned_repos(username, use_nerd=args.nerd)

    if not args.no_interactive:
        show_interactive_menu(username, use_nerd=args.nerd)

if __name__ == "__main__":
    main()
