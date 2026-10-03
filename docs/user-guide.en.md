# Using OpenBlindySir — V0.5 — development

[Guide français](guide-utilisateur.md). One server hosts one game at a time, on a
LAN, private VPN or the Internet. Players use a browser without creating an account.
See [hosting](deployment.md) or [Docker](docker.md). Update server, Bridge and web
UI together: **protocol 5**. [Install the Bridge](bridge-installation.en.md).

## Join, audio and recovery

The host shares the game URL and game password, keeping the host password private.
Each Bridge owner receives a separate
[private identity file](bridge-installation.en.md#uvx-and-guided-setup) to keep on
their device; do not share it with players. On a private network, trust the configured certificate first.
Enter a nickname (24 characters maximum), the game password, and **Join**. Test
your sound, confirm the beep, set the volume and keep the browser active.

French/English and audio preferences are saved locally. **Audio correction (ms)**
ranges from −500 to +500: positive values advance the next playback to compensate
for a delayed output; negative values delay it. For example, try +150 ms for a
Bluetooth output delayed by 150 ms. Changes apply to the next playback and never
change official answer timing or award points. Start at zero and test your output.

Create a private **Recovery code** before switching devices. On the entry screen,
**Restore my place** asks for that six-character code and the game password. It
keeps your identity and answers, revokes previous connections, and grants only
player access. Hosts must elevate again. Codes are single use; creating another
invalidates the previous one. Recovery and existing-cookie reconnection still
work while new registrations are locked. Removed players cannot recover their seat.

## Play rounds

Wait for preparation, loading and countdown. Type a free-text answer and choose
**SUBMIT**, or Enter. Submission is final for that round: wait for the saved
acknowledgement. Unsubmitted text is a synchronized draft. When answers close,
the latest received draft becomes **Captured draft**, without official rank or
submission elapsed time. It earns no automatic points.

Audio ending does not necessarily close answers. The host can pause audio and
answers, resume together, replay, add time or close. Paused time is excluded from
answer elapsed time. After each round, answers are saved and the host moves on.
**Tracks, answers from others and points are revealed only after final validation.**
The anonymous answered counter is hidden when fewer than three players are expected.

## Host setup

Open `/host` or Host access and enter the host password. **Host player** participates
with the same anti-spoiler rules; **MC** does not play and can see upcoming tracks
and live answers. Switching to MC is allowed between rounds; switching back to
player waits for the next game. Spectators listen and see results without answers,
scores or readiness requirements.

Select folders, round count, clip duration, answer grace period, instructions and
scoring expectations. Parent/child selections do not double-count tracks. **Save
and start** applies settings atomically. If there are too few fresh tracks, reduce
rounds or allow repeats. Favorites are saved in this browser. Advanced options
include volume normalization, silence avoidance and folder balancing. Balancing
rotates shuffled folder groups without duplicating tracks; selecting the root uses
each track's containing folder. In MC mode, choose a track for a numbered,
unprepared round and confirm the choice; its launch stays explicit even with auto-start.

Assign teams and spectators in the lobby. Team totals sum individual points.
**Close registrations** blocks new identities, while reconnection/recovery remains
possible. The host can reopen registrations in any phase. Invitations contain the
URL only: share the game password separately.

## Sources, search and metadata

Three distinct choices: the locally authorized root or Docker mount, subfolders
scanned by a Bridge, and folders selected for a game. **Library sources and search**
adds/removes relative subfolders and requests a rescan. An empty root path includes
everything; remove that root before limiting the scan to individual subfolders.
Changes are asynchronous: folder controls remain disabled until the Bridge's
completed scan is received. Counts and folders update automatically. If the scan
is not confirmed within 75 seconds, refresh the library and retry. Up to eight
different Bridges can stay connected, with persistent, distinct UUIDs.

An outside directory requires a local root choice or a read-only Docker mount.
Recreate only the Bridge after changing its mounts; retain the server/session
volume. Adding files under an existing mount only needs a rescan. Symlinks,
junctions, absolute paths and traversal are refused. Inaccessible scans keep the
previous catalogue and display instructions. See [Docker source management](docker.md#sources-dynamiques-et-réécoute).

Search filename, imported/corrected title or artist. Filter Bridge, relative
folder, extension, availability and fresh tracks; pages contain at most 100
matches. Folder search preserves ancestors for navigation. This data is host-only
in lobby/final review/results, or available to MC during play.

MP4/MOV/MKV/AVI and other whitelisted containers provide **only their first audio
stream**, regardless of default-stream flags. Video, subtitles, data, artwork and
musical tags never enter clips. Missing audio gives a private `NO_AUDIO` diagnostic
and the game tries another track. Production output remains AAC/M4A 128 kbit/s,
48 kHz stereo: roughly 320/400/480 kB for 20/25/30 seconds plus container overhead.
Opus/WebM is configurable. DRM files and codecs missing from FFmpeg are unavailable.

Optional metadata is UTF-8 JSON `{version:1,rows:[...]}`, keyed by Bridge UUID
and exact NFC POSIX relative path including extension. Title, artist, featuring,
album and year are optional. Export a template first. Imports are limited to
1 MiB/10,000 rows; invalid, duplicate, unknown and ambiguous rows are reported
individually while valid rows are accepted. Non-empty manual corrections take
priority per field over imports, then title/artist tags or a cleaned filename.
Clearing a manual field restores its fallback. Corrections/imports persist in
the private snapshot; exports merge them for still-known files. Detailed format:
[technical notes](v0.2.en.md) and [source reference](media-and-metadata.md).

## End-of-game review

The last round or **Stop the game** opens **END OF GAME REVIEW**. Choose any played
round through the track list, search, or previous/next controls. Players wait.
The review shows track context, each participant's answer/status, official time
and rank when present, server reception time, and known late audio. Missing data
shows “—”. Removed players who participated remain reviewable.

Use 0/+1/+2/+3 shortcuts or a signed integer between −1000 and +1000. Explicit
zero marks a checked decision; default zero stays unchecked. Enter/blur sends
the value: wait for **Saved**. Navigation and final validation wait for the server.
Saved points survive refresh/reconnection and snapshots; unsent local text can be lost.
Correct title, artist, featuring, album and year before publication.

Provisional totals combine all included rounds and optional final corrections.
Team totals sum individual totals. Captured-draft policy is either manual scoring
or mandatory zero, checked explicitly. Resetting final corrections preserves round
points. Final validation asks for confirmation with totals and unchecked count;
confirming unchecked rows keeps their current values, initially zero.
Correction shortcuts and resets also wait for the server's saved values before
another edit or final publication is allowed.

**VALIDATE SCORES AND SHOW RESULTS** publishes once and freezes the journal.
Everyone sees standings, shared ranks for ties, tracks, answers, timing and recap.
CSV/JSON exports use those published results; CSV cells are protected from formulas.

## Private listening

**Play** fetches the exact game clip on demand. Pause, progress, duration, seeking
and volume belong to a separate host player and never control other players.
**Listen to full track** requires the Bridge owner's local opt-in:
`--allow-full-review` or `OPENBLINDYSIR_BRIDGE_ALLOW_FULL_REVIEW=true`.

Full mode is labelled clearly and can return to the game excerpt. Audio is
reencoded on demand in segments of at most 30 seconds; seeking requests a short
segment. Loading may interrupt between segments. The full source stays on the
Bridge, and segments are not stored durably on the server. Changing rounds cancels
the request and releases the previous Blob. An offline Bridge, changed source or
an exact clip no longer reproducible after restart displays a retryable error;
retry keeps the requested listening position. A lost Bridge or rejected upload
ends the pending transfer promptly. Scoring remains available.

## Stop and restore

Stop is available before the first round, during preparation/loading/countdown,
playback, pause, closed rounds and global review. Confirmation explains what stays.
Before official playback, the current round is cancelled and excluded. During an
open round, audio stops and answers/drafts are kept for global scoring. The secondary
“end without scoring this round” option retains the played round and its answers,
with zero points and excluded status. A repeated stop during review preserves drafts.
No stop publishes results automatically. Played cancelled rounds remain in the recap.

**New game** keeps players still registered, metadata, catalogue and tracks already
heard during the evening. Removed identities are discarded while their archived
results remain readable. **End session** revokes sessions/codes and resets players/current game,
while saved archives and library metadata remain. Keep private snapshot backups.

Snapshots restore answers, points, configuration, sources, metadata and the last
50 completed games. RAM audio is lost. An interrupted open round closes/captures
answers and displays a warning; a future countdown returns to preparation.
Bridge reconnection regenerates required clips. Snapshot-write failures alert hosts.

## Troubleshooting and limits

Joins are limited to 60/IP/minute and 600/server/minute, including correct passwords:
wait a minute after `rate_limited`. `MAX_PLAYERS` still caps simultaneous players.
State retains at most 1,000 identities, including removed players needed for current
results. At that cap, `game_full` refuses new joins; New game after archiving or End
session frees previous identities.

In MC mode, **Library sources and search → Choose tracks (MC)** lets the host
choose a numbered round before preparation. Search/filter results show source,
folder, filename, available title/artist, format, measured duration, availability,
played/reserved state. Select a round, choose a track, and wait for server
confirmation before starting. Pending edits disable launch; concurrent revisions
are rejected. The chosen source must belong to the game's selected folders.

Manual choices obey repeat rules, bypass random folder balancing, and cannot
duplicate another round's reservation. Preloading one/two rounds locks choices
as soon as preparation is requested; plan in the lobby or choose a later free
round. A manual ready round waits for explicit launch even with auto-start on.
If the source/Bridge fails, replace it, return to random, skip or end; no silent
substitution. Players and a playing host never receive future choice details.
See [troubleshooting and recovery](operations.en.md).

Retry audio, check volume/output, reactivate after autoplay suspension, and keep
the tab active. Reconnection restores only server-received drafts. “Open elsewhere”
allows taking over the current tab. If a folder is missing, check the mount rather
than entering an absolute path. Review skipped-file diagnostics and codec/audio
availability. Preserve TLS verification and prepare certificate trust correctly.

The project is still in development. Synthetic headless tests do not validate
physical sound or acoustic synchronization. Try actual Safari/iPhone/Android
devices before a game night. See [test records](DEVLOG.md) and [manual checks](testing.md).

## Private Bridges and V0.5 history

Each Bridge has a stable UUID, a name and a distinct secret. The host issues a
private identity file; the owner keeps control of the music root and full-listening
opt-in. See the [V0.5 commands](v0.5.en.md). The Bridges panel shows per-owner
connection, capabilities and errors, and can revoke one identity with confirmation.
During play, host players cannot access source names, the library or archives;
the MC retains private access. An unprepared random pick waits at most 45 seconds
for its owner, then tries another available source. Manual picks offer explicit
replacement, random fallback, skip or end. A prepared excerpt can keep playing.

After final validation, **History** loads retained games on demand, including the
original names and teams, settings, answers, timings, reveals and corrected scores.
Later library changes and games do not modify these records. Hosts can inspect,
export, delete one or purge all with confirmation. Retention: 50 games, 90 days,
16 MiB, without audio. A save warning identifies unavailable durable storage.
Deletion removes the archive from both managed snapshots; exported files and
external backups need separate cleanup. Current final results remain visible until
New game or End session.

Skip links, keyboard controls, Escape/cancel with focus restoration and labelled
audio controls are available. Automated checks cover 320 px and text at 200%.
NVDA/VoiceOver and physical devices still require manual acceptance; this is not
an accessibility certification.
