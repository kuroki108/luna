from __future__ import annotations

import html
from datetime import datetime, timezone

import discord

_CSS = """
:root {
  --bg: #313338;
  --bg-alt: #2b2d31;
  --text: #dbdee1;
  --muted: #949ba4;
  --accent: #5865f2;
  --divider: #3f4147;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: "gg sans", "Noto Sans", Helvetica, Arial, sans-serif;
}
header {
  background: var(--bg-alt);
  padding: 20px 28px;
  border-bottom: 1px solid var(--divider);
  position: sticky;
  top: 0;
}
header h1 { margin: 0 0 4px 0; font-size: 20px; }
header p { margin: 0; color: var(--muted); font-size: 13px; }
.messages { padding: 16px 28px 60px 28px; max-width: 900px; margin: 0 auto; }
.msg {
  display: flex;
  gap: 14px;
  padding: 8px 4px;
  border-radius: 6px;
}
.msg:hover { background: rgba(255,255,255,0.02); }
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--accent);
}
.body { min-width: 0; }
.meta { display: flex; align-items: baseline; gap: 8px; }
.author { font-weight: 600; color: #f2f3f5; }
.timestamp { font-size: 12px; color: var(--muted); }
.content { white-space: pre-wrap; word-wrap: break-word; line-height: 1.4; }
.attachment {
  display: block;
  margin-top: 6px;
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}
.attachment img { max-width: 400px; max-height: 300px; border-radius: 6px; display: block; margin-top: 4px; }
.embed {
  margin-top: 6px;
  padding: 10px 12px;
  border-left: 4px solid var(--accent);
  background: var(--bg-alt);
  border-radius: 4px;
  max-width: 520px;
}
.embed .embed-title { font-weight: 600; margin-bottom: 4px; }
.embed .embed-desc { font-size: 14px; color: var(--text); white-space: pre-wrap; }
.system { color: var(--muted); font-style: italic; font-size: 13px; padding: 4px 4px; }
footer { text-align: center; color: var(--muted); font-size: 12px; padding: 20px; }
"""


def _fmt_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def _render_message(message: discord.Message) -> str:
    if message.type != discord.MessageType.default and message.type != discord.MessageType.reply:
        # System-Nachrichten (z. B. "X hat Y hinzugefügt") kompakt darstellen
        return f'<div class="system">{html.escape(message.system_content or message.content)}</div>'

    author = message.author
    avatar_url = str(author.display_avatar.url) if author.display_avatar else ""
    name = html.escape(str(author.display_name))
    content = html.escape(message.content) if message.content else ""

    attachments_html = ""
    for att in message.attachments:
        url = html.escape(att.url)
        filename = html.escape(att.filename)
        if att.content_type and att.content_type.startswith("image/"):
            attachments_html += f'<a class="attachment" href="{url}" target="_blank">{filename}<img src="{url}"></a>'
        else:
            attachments_html += f'<a class="attachment" href="{url}" target="_blank">📎 {filename}</a>'

    embeds_html = ""
    for embed in message.embeds:
        title = html.escape(embed.title) if embed.title else ""
        desc = html.escape(embed.description) if embed.description else ""
        embeds_html += (
            '<div class="embed">'
            + (f'<div class="embed-title">{title}</div>' if title else "")
            + (f'<div class="embed-desc">{desc}</div>' if desc else "")
            + "</div>"
        )

    return f"""
    <div class="msg">
      <img class="avatar" src="{avatar_url}" alt="">
      <div class="body">
        <div class="meta">
          <span class="author">{name}</span>
          <span class="timestamp">{_fmt_time(message.created_at)}</span>
        </div>
        <div class="content">{content}</div>
        {attachments_html}
        {embeds_html}
      </div>
    </div>
    """


async def build_transcript(channel: discord.TextChannel) -> str:
    """Lädt den kompletten Verlauf eines Kanals und gibt ein HTML-Dokument als String zurück."""
    messages = [m async for m in channel.history(limit=None, oldest_first=True)]
    rendered = "\n".join(_render_message(m) for m in messages)
    generated_at = _fmt_time(datetime.now(timezone.utc))

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Transcript - #{html.escape(channel.name)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1># {html.escape(channel.name)}</h1>
  <p>{len(messages)} Nachrichten &middot; erstellt am {generated_at}</p>
</header>
<div class="messages">
{rendered}
</div>
<footer>luna Ticketsystem &middot; automatisch generiertes Transcript</footer>
</body>
</html>"""
