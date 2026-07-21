# SPDX-License-Identifier: AGPL-3.0-or-later
"""YuJa transcript client for a school's YuJa instance (set YUJA_BASE env).

What this gives you:
    - list_channel_videos(channel_node_pid): all videos in a channel with their videoPIDs
    - get_video(video_pid): full video metadata incl. `transcriptText`
    - get_transcript(video_pid): just the cleaned transcript string (no <br>, no JSON wrapper)
    - refresh_transcript_library(catalog, out_dir): batch-refresh all cached transcripts

Auth:
    Reads cookie from .yuja_cookies.json (JSESSIONID). Session TTL ~30min-4h idle.
    When it expires, re-export cookie from browser devtools.

Discovery procedure (for a NEW channel/course):
    1. Open the channel in browser, note URL like /MediaChannel/<X>/... — X is the
       "routing ID" but it is NOT the internal videoListNodePID.
    2. Click any video in that channel, URL becomes /WatchVideo/<nodeFromURL>.
    3. Call VideoListNodeAncestorsJSON?videoListNodePID=<nodeFromURL> — the LAST
       entry in the returned ancestors is the real channel videoListNodePID.
    4. Call list_channel_videos(realChannelPID) to get all videos + their videoPIDs.
    5. For each videoPID, call get_transcript(videoPID).

Why one at a time for transcripts:
    `POST /P/Data/VideoListJSON` with multiple videoID[] items DOES return all videos,
    BUT the `transcriptText` field is OMITTED in batch responses to keep payloads small.
    Single-video requests include the full transcript.
"""

from __future__ import annotations
import json, re, html, time, sys, os
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
COOKIE_FILE = ROOT / '.yuja_cookies.json'
BASE = os.environ.get('YUJA_BASE', '').rstrip('/')
if not BASE:
    raise RuntimeError("YUJA_BASE env var required (e.g. https://<your-school>.yuja.com)")


def _session() -> requests.Session:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f'{COOKIE_FILE} missing — export JSESSIONID from browser devtools')
    cookies = json.loads(COOKIE_FILE.read_text(encoding='utf-8'))
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        'User-Agent': 'Mozilla/5.0',
        'Referer': BASE + '/',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, */*; q=0.01',
    })
    return s


def discover_channel_root_pid(node_pid_from_url: str | int, s: requests.Session | None = None) -> str:
    """Given any videoListNodePID from a WatchVideo URL, return the real channel's
    videoListNodePID (the immediate parent of the video node)."""
    s = s or _session()
    r = s.get(f'{BASE}/P/Data/VideoListNodeAncestorsJSON',
              params={'videoListNodePID': str(node_pid_from_url)}, timeout=20)
    r.raise_for_status()
    ancestors = r.json().get('data') or []
    if not ancestors:
        raise RuntimeError(f'no ancestors for node {node_pid_from_url}')
    return str(ancestors[-1]['videoListNodePID'])


def list_channel_videos(channel_node_pid: str | int, s: requests.Session | None = None) -> list[dict]:
    """Return all videos in a channel — each dict has videoListNodePID, videoPID, title."""
    s = s or _session()
    params = {
        'videoListNodePID': str(channel_node_pid),
        'getUserInfoJSON': 'false',
        'videoListNodePIDMaximumCutoff': '',
        'searchTerm': '',
        'lastVideoListNodeTitle': '',
        'lastVideoListNodePID': '',
        'limitResults': '500',
        'offset': '0',
        'quickLoad': 'false',
        'sortType': '',
        'count': '',
        'getOnlyFolders': 'false',
        'enableDeepSearch': 'false',
    }
    r = s.get(f'{BASE}/P/Data/VideoListNodeChildrenJSON', params=params, timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get('success'):
        raise RuntimeError(f'VideoListNodeChildrenJSON failed for channel {channel_node_pid}: {j}')
    return j.get('data') or []


def get_video(video_pid: str | int, s: requests.Session | None = None) -> dict:
    """Return full video metadata for one video (includes transcriptText if captioned)."""
    s = s or _session()
    r = s.post(f'{BASE}/P/Data/VideoListJSON',
               data=[('videoID[]', str(video_pid)),
                     ('getUserInfoJSON', 'false'),
                     ('getUserWatchTime', 'false')],
               timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get('success'):
        raise RuntimeError(f'VideoListJSON failed for video {video_pid}: {j.get("reason")}')
    videos = j.get('data') or []
    if not videos:
        raise RuntimeError(f'video {video_pid} not found (may be deleted or no permission)')
    return videos[0]


def clean_transcript(raw: str | None) -> str:
    """YuJa returns transcriptText as a JSON-wrapped string with <br> tags. Unwrap."""
    if not raw:
        return ''
    if raw.lstrip().startswith('{'):
        try:
            raw = json.loads(raw).get('transcript', '') or raw
        except Exception:
            pass
    t = html.unescape(raw)
    t = re.sub(r'<br\s*/?>\s*<br\s*/?>', '\n\n', t)
    t = re.sub(r'<br\s*/?>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r' +', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def get_transcript(video_pid: str | int, s: requests.Session | None = None) -> str:
    """Just the transcript string, cleaned. Empty string if video has no caption."""
    return clean_transcript(get_video(video_pid, s).get('transcriptText'))


def refresh_transcript_library(
    catalog: list[tuple[str, str, int, str]],
    out_dir: Path = ROOT / 'yuja_transcripts',
    channel_url_id: str = '2251841',
) -> None:
    """Batch-refresh cached transcripts.

    catalog entries: (slug, node_pid_in_url, video_pid, title)
    Writes one .txt per video + updates _INDEX.json.
    """
    s = _session()
    out_dir.mkdir(exist_ok=True)
    index_entries = []
    for slug, node_pid, vid_pid, title in catalog:
        try:
            v = get_video(vid_pid, s)
        except Exception as e:
            print(f'  FAIL {slug}: {e}')
            continue
        transcript = clean_transcript(v.get('transcriptText') or '')
        duration = int(v.get('duration') or 0)
        owner = v.get('ownerFullName') or '?'
        path = out_dir / f'{slug}.txt'
        hdr = (f"# {title}\n"
               f"# YuJa videoPID: {vid_pid}\n"
               f"# URL nodePID: {node_pid}\n"
               f"# Duration: {duration}s ({duration//60}:{duration%60:02d})\n"
               f"# Owner: {owner}\n"
               f"# Source URL: {BASE}/P/VideoManagement/MediaLibrary/MediaChannel/{channel_url_id}/WatchVideo/{node_pid}\n"
               f"# Transcript length: {len(transcript)} chars\n"
               f"# ============================================================\n\n")
        path.write_text(hdr + (transcript or '[NO TRANSCRIPT AVAILABLE ON YUJA]'),
                        encoding='utf-8')
        index_entries.append({
            'slug': slug, 'title': title, 'videoPID': vid_pid, 'nodePID': node_pid,
            'duration_sec': duration, 'duration_mmss': f'{duration//60}:{duration%60:02d}',
            'transcript_path': str(path.relative_to(ROOT)).replace('\\', '/'),
            'transcript_chars': len(transcript),
            'has_transcript': bool(transcript), 'owner': owner,
        })
        print(f'  {path.name:<50} {len(transcript):>6} chars  {duration//60}:{duration%60:02d}')
        time.sleep(0.3)
    (out_dir / '_INDEX.json').write_text(json.dumps({
        'channel_id_in_url': channel_url_id,
        'channel_title': '<writing-course channel title>',
        'fetched_at': time.strftime('%Y-%m-%d'),
        'videos': index_entries,
    }, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    # Refresh the writing-course transcript library
    CATALOG = [
        ("Response_Writing",                 "67577736", 2175010, "Week 2: Response Writing"),
        ("Academic_Verbs",                   "67577758", 2149525, "Academic Verbs"),
        ("Summary_Writing",                  "67577945", 2012753, "Summary Writing"),
        ("Qualities_Academic_Writing",       "67577808", 1129689, "Week 7 The Qualities of Academic Writing"),
        ("Thesis_Statements",                "67577800", 1148731, "Week 8 Thesis Statements"),
        ("Introductions_Conclusions",        "67577698", 3840840, "Week 8: Introductions & Conclusions"),
        ("Revising_Editing_Proofreading",    "67577680", 3936275, "Week 9: Revising Editing Proofreading"),
        ("Complexity_Academic_Writing",      "67577727", 2211441, "Complexity in Academic Writing edited for 20A"),
        ("Accessing_Electronic_Feedback",    "67577822",  817263, "Week 3: Accessing Electronic Feedback"),
    ]
    refresh_transcript_library(CATALOG)
